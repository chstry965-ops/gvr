"""
RF metadata dataset builder.

Builds:
  - processed/ru_reputation_raw.csv
  - processed/ru_numbers_labeled.csv
  - processed/ru_metadata_features.csv
  - processed/ru_tflite_features.csv

Synthetic rows are disabled by default and available only for smoke tests.
"""

import argparse
import csv
import math
import os
import random
import sys
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))

from ru_metadata_features import (
    COMPACT_FEATURES, FULL_METADATA_FIELDS, LABEL_TO_ID,
    RU_TO_FIELD,
    category_flags, compact_feature_vector, compact_row,
    compute_reputation_score,
    infer_prefix_risk, number_type, operator_bucket, parse_date,
    review_velocity, safe_float, safe_int, stable_bucket,
    translate_headers, translate_row,
)
from ru_number_normalizer import get_def_code, normalize_ru_phone
from ru_numbering_plan import NumberingPlan, load_existing_csv as load_numbering_csv

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'ru')
RAW_DIR = os.path.join(BASE_DIR, 'raw')
PROCESSED_DIR = os.path.join(BASE_DIR, 'processed')

RAW_REPUTATION_FILES = [
    'ru_reputation_raw.csv',
    'reviews_neberitrubku.csv',
    'reviews_zvonili.csv',
]

BLACKLIST_FILES = [
    ('blacklist_moshelovka.csv', 'moshelovka'),
    ('blacklist_spravportal.csv', 'spravportal'),
]

RAW_REPUTATION_SCHEMA = [
    'normalized_number',
    'source',
    'negative_count',
    'positive_count',
    'neutral_count',
    'review_count',
    'search_volume',
    'categories',
    'last_review_at',
    'first_seen_at',
    'source_confidence',
    'source_reliability',
    'view_count',
    'related_count',
    'detail_date',
    'page_title',
    'url',
]


def read_csv(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    # Перевести русские заголовки обратно в английские для внутренней обработки
    if rows:
        first_key = next(iter(rows[0].keys()), '')
        if first_key in RU_TO_FIELD or any(k in RU_TO_FIELD for k in rows[0].keys()):
            rows = [translate_row(r, to_ru=False) for r in rows]
    return rows


def write_dict_csv(path: str, rows: Iterable[Dict], fieldnames: List[str]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Пишем с русскими заголовками
    ru_fieldnames = translate_headers(fieldnames, to_ru=True)
    ru_rows = [translate_row(r, to_ru=True) for r in rows]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=ru_fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(ru_rows)


def write_rows_csv(path: str, header: List[str], rows: Iterable[List[float]]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Пишем с русскими заголовками
    ru_header = translate_headers(header, to_ru=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(ru_header)
        writer.writerows(rows)


def load_whitelist() -> Dict[str, Dict]:
    result = {}
    # Official whitelist
    for row in read_csv(os.path.join(RAW_DIR, 'whitelist_official_ru.csv')):
        number = normalize_ru_phone(row.get('normalized_number') or row.get('phone') or row.get('number') or '')
        if not number:
            continue
        result[number] = {
            'normalized_number': number,
            'name': row.get('name', ''),
            'category': row.get('category', 'official'),
            'source': 'whitelist_official',
            'source_confidence': 0.95,
        }
    # Legitimate numbers from scraper (organizations, freelancers, etc.)
    for row in read_csv(os.path.join(RAW_DIR, 'legitimate_numbers.csv')):
        number = normalize_ru_phone(row.get('normalized_number') or row.get('phone') or row.get('number') or '')
        if not number:
            continue
        if number in result:
            continue  # don't overwrite official whitelist
        source = row.get('source', 'legitimate')
        cat = row.get('category', '')
        source_conf = safe_float(row.get('source_confidence'), 0.0)
        if source_conf <= 0:
            if source in {'official_whitelist', 'official_hotline'}:
                source_conf = 0.95
            elif cat in {'personal_mobile'} or source.startswith('numbering_plan'):
                source_conf = 0.25
            elif cat in {'freelancer', 'private_seller', 'realestate_owner'}:
                source_conf = 0.55
            elif cat in {'delivery', 'government', 'bank', 'medical'}:
                source_conf = 0.85
            else:
                source_conf = 0.70
        result[number] = {
            'normalized_number': number,
            'name': row.get('name', ''),
            'category': cat,
            'source': f'legitimate_{source}',
            'source_confidence': source_conf,
        }
    return result


def normalize_reputation_row(row: Dict, source_hint: str = '') -> Optional[Dict]:
    raw_number = row.get('normalized_number') or row.get('phone') or row.get('number') or ''
    number = normalize_ru_phone(raw_number, reject_non_ru=False)
    if not number:
        return None

    negative = safe_int(row.get('negative_count') or row.get('negative') or row.get('bad') or 0)
    positive = safe_int(row.get('positive_count') or row.get('positive') or row.get('good') or 0)
    neutral = safe_int(row.get('neutral_count') or row.get('neutral') or 0)
    review_count = safe_int(row.get('review_count') or row.get('reviews') or row.get('overall') or 0)
    if review_count <= 0:
        review_count = negative + positive + neutral

    categories = row.get('categories') or row.get('category') or row.get('rating') or ''
    source = row.get('source') or source_hint or 'unknown'
    confidence = safe_float(row.get('source_confidence') or row.get('confidence') or 0.5)

    # Prefer view_count as search_volume when available (crawler stores views there)
    view_count = safe_int(row.get('view_count') or row.get('views') or 0)
    search_volume = safe_int(row.get('search_volume') or 0)
    # If search_volume is 0 but view_count > 0, use view_count as proxy
    if search_volume <= 0 and view_count > 0:
        search_volume = view_count

    return {
        'normalized_number': number,
        'source': source,
        'negative_count': negative,
        'positive_count': positive,
        'neutral_count': neutral,
        'review_count': review_count,
        'search_volume': search_volume,
        'categories': categories,
        'last_review_at': row.get('last_review_at', '') or row.get('detail_date', ''),
        'first_seen_at': row.get('first_seen_at', ''),
        'source_confidence': confidence,
        'source_reliability': safe_float(row.get('source_reliability') or 0.5),
        'view_count': view_count,
        'related_count': safe_int(row.get('related_count') or 0),
        'detail_date': row.get('detail_date', ''),
        'page_title': row.get('page_title', ''),
        'url': row.get('url', ''),
    }


def load_reputation_rows() -> List[Dict]:
    rows = []
    for filename in RAW_REPUTATION_FILES:
        source_hint = filename.replace('reviews_', '').replace('.csv', '')
        for row in read_csv(os.path.join(RAW_DIR, filename)):
            normalized = normalize_reputation_row(row, source_hint)
            if normalized:
                rows.append(normalized)
    return rows


def load_blacklist_rows() -> List[Dict]:
    rows = []
    for filename, source in BLACKLIST_FILES:
        for row in read_csv(os.path.join(RAW_DIR, filename)):
            number = normalize_ru_phone(row.get('normalized_number') or row.get('phone') or row.get('number') or '')
            if not number:
                continue
            category = row.get('category') or 'мошенничество'
            confidence = safe_float(row.get('confidence') or row.get('source_confidence') or 0.85)
            rows.append({
                'normalized_number': number,
                'source': source,
                'negative_count': 1,
                'positive_count': 0,
                'neutral_count': 0,
                'review_count': 1,
                'search_volume': 0,
                'categories': category,
                'last_review_at': '',
                'first_seen_at': '',
                'source_confidence': confidence,
                'source_reliability': 0.85,
                'view_count': 0,
                'related_count': 0,
                'detail_date': '',
                'page_title': '',
                'url': row.get('url', ''),
            })
    return rows


def aggregate_reputation(rows: List[Dict]) -> Dict[str, Dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['normalized_number']].append(row)

    result = {}
    for number, items in grouped.items():
        negative = sum(safe_int(i.get('negative_count')) for i in items)
        positive = sum(safe_int(i.get('positive_count')) for i in items)
        neutral = sum(safe_int(i.get('neutral_count')) for i in items)
        review_count = sum(max(safe_int(i.get('review_count')), 0) for i in items)
        search_volume = max(safe_int(i.get('search_volume')) for i in items) if items else 0
        categories = ';'.join(sorted({c.strip() for i in items for c in str(i.get('categories', '')).split(';') if c.strip()}))
        source = '+'.join(sorted({i.get('source', 'unknown') for i in items}))
        confidence = max(safe_float(i.get('source_confidence'), 0.5) for i in items)
        reliability = max(safe_float(i.get('source_reliability'), 0.5) for i in items)
        view_count = max(safe_int(i.get('view_count')) for i in items) if items else 0
        related_count = max(safe_int(i.get('related_count')) for i in items) if items else 0
        last_review_at = max((i.get('last_review_at', '') for i in items), default='')
        first_seen_values = [i.get('first_seen_at', '') for i in items if i.get('first_seen_at')]
        first_seen_at = min(first_seen_values) if first_seen_values else ''
        detail_dates = [i.get('detail_date', '') for i in items if i.get('detail_date')]
        detail_date = max(detail_dates) if detail_dates else ''
        page_titles = [i.get('page_title', '') for i in items if i.get('page_title')]
        page_title = page_titles[0] if page_titles else ''
        result[number] = {
            'normalized_number': number,
            'source': source,
            'negative_count': negative,
            'positive_count': positive,
            'neutral_count': neutral,
            'review_count': max(review_count, negative + positive + neutral),
            'search_volume': search_volume,
            'categories': categories,
            'last_review_at': last_review_at,
            'first_seen_at': first_seen_at,
            'source_confidence': confidence,
            'source_reliability': reliability,
            'view_count': view_count,
            'related_count': related_count,
            'detail_date': detail_date,
            'page_title': page_title,
            'url': ';'.join(i.get('url', '') for i in items if i.get('url')),
        }
    return result


def determine_label(number: str, reputation: Optional[Dict], whitelist_info: Optional[Dict], in_public_blacklist: bool) -> Tuple[str, float, str]:
    if whitelist_info:
        confidence = safe_float(whitelist_info.get('source_confidence'), 0.7)
        source = whitelist_info.get('source', 'whitelist_official')
        weight = 0.25 if confidence < 0.35 else round(max(0.5, min(2.0, confidence * 2.0)), 2)
        return 'ALLOW', weight, source

    if in_public_blacklist:
        return 'BLOCK', 2.0, reputation.get('source', 'blacklist') if reputation else 'blacklist'

    if not reputation:
        return 'WARN', 0.25, 'unknown'

    negative = safe_int(reputation.get('negative_count'))
    positive = safe_int(reputation.get('positive_count'))
    neutral = safe_int(reputation.get('neutral_count'))
    review_count = max(safe_int(reputation.get('review_count')), negative + positive + neutral)
    search_volume = safe_int(reputation.get('search_volume'))
    view_count = safe_int(reputation.get('view_count'))
    # view_count can substitute for search_volume as a popularity proxy
    if search_volume <= 0 and view_count > 0:
        search_volume = view_count
    total = max(negative + positive + neutral, review_count, 1)
    negative_ratio = negative / total
    positive_ratio = positive / total
    flags = category_flags(reputation.get('categories', ''))
    confidence = safe_float(reputation.get('source_confidence'), 0.5)
    reliability = safe_float(reputation.get('source_reliability'), 0.5)

    # reliability boosts weight: high-reliability sources get stronger signals
    rel_boost = 1.0 + (reliability - 0.5) * 0.4  # range ~0.8..1.2

    if flags['has_fraud_category'] and (negative_ratio >= 0.5 or negative >= 2 or confidence >= 0.8):
        return 'BLOCK', round(1.7 * rel_boost, 2), reputation.get('source', 'reviews')

    if negative_ratio >= 0.75 and review_count >= 3:
        return 'BLOCK', round(1.5 * rel_boost, 2), reputation.get('source', 'reviews')

    if flags['has_telemarketing_category'] or negative_ratio >= 0.35:
        return 'WARN', round(1.0 * rel_boost, 2), reputation.get('source', 'reviews')

    if search_volume >= 500 and review_count <= 2:
        return 'WARN', round(0.8 * rel_boost, 2), reputation.get('source', 'search_volume')

    if positive_ratio >= 0.75 and review_count >= 3:
        return 'ALLOW', 0.9, reputation.get('source', 'reviews')

    return 'WARN', 0.5, reputation.get('source', 'reviews')


def infer_timezone_offset(region: str) -> int:
    text = (region or '').lower()
    if any(k in text for k in ['камчат', 'чукот']):
        return 12
    if any(k in text for k in ['магадан', 'сахалин']):
        return 11
    if any(k in text for k in ['якут', 'примор', 'хабаров']):
        return 10
    if any(k in text for k in ['иркут', 'бурят']):
        return 8
    if any(k in text for k in ['краснояр', 'кемеров', 'томск', 'новосибир']):
        return 7
    if 'омск' in text:
        return 6
    if any(k in text for k in ['екатерин', 'свердлов', 'челябин', 'перм', 'тюмень']):
        return 5
    if any(k in text for k in ['самар', 'саратов', 'удмурт']):
        return 4
    if 'калининград' in text:
        return 2
    return 3


def enrich_numbering(number: str, numbering_plan: Optional[NumberingPlan]) -> Dict:
    match = numbering_plan.lookup(number) if numbering_plan else None
    operator = match.get('operator', '') if match else ''
    region = match.get('region', '') if match else ''
    n_type = match.get('number_type') if match else number_type(number)
    op_bucket = operator_bucket(operator)
    return {
        'numbering_match': match is not None,
        'is_valid_ru_range': match is not None,
        'operator': operator,
        'region': region,
        'number_type': n_type,
        'def_code': get_def_code(number) or '',
        'operator_bucket': op_bucket,
        'region_bucket': stable_bucket(region),
        'timezone_offset': infer_timezone_offset(region),
        'is_mvno': 1 if op_bucket == 'mvno' else 0,
    }


def build_feature_record(number: str, label: str, weight: float, source: str, reputation: Optional[Dict], numbering: Dict) -> Dict:
    reputation = reputation or {}
    negative = safe_int(reputation.get('negative_count'))
    positive = safe_int(reputation.get('positive_count'))
    neutral = safe_int(reputation.get('neutral_count'))
    review_count = max(safe_int(reputation.get('review_count')), negative + positive + neutral)
    total_votes = max(negative + positive + neutral, review_count, 1)
    search_volume = safe_int(reputation.get('search_volume'))
    flags = category_flags(reputation.get('categories', ''))
    compact_meta = {
        **reputation,
        **numbering,
        'source_confidence': safe_float(reputation.get('source_confidence'), 0.95 if source == 'whitelist_official' else 0.5),
        'source_reliability': safe_float(reputation.get('source_reliability'), 0.5),
        'inAllowlist': label == 'ALLOW',
        'inBlacklist': label == 'BLOCK',
        'contactsAvailable': True,
    }
    compact = compact_feature_vector(number, label, compact_meta)
    view_count = safe_int(reputation.get('view_count'))
    related_count = safe_int(reputation.get('related_count'))
    row = {
        'normalized_number': number,
        'label': label,
        'label_id': LABEL_TO_ID[label],
        'weight': weight,
        'source': source,
        'source_confidence': compact['sourceConfidence'],
        'negative_count': negative,
        'positive_count': positive,
        'neutral_count': neutral,
        'review_count': review_count,
        'negative_ratio': negative / total_votes,
        'positive_ratio': positive / total_votes,
        'search_volume': search_volume,
        'search_volume_log': math.log1p(search_volume),
        'review_velocity_48h': review_velocity(reputation.get('last_review_at'), reputation.get('first_seen_at'), review_count, 2),
        'review_velocity_7d': review_velocity(reputation.get('last_review_at'), reputation.get('first_seen_at'), review_count, 7),
        'has_fraud_category': flags['has_fraud_category'],
        'has_telemarketing_category': flags['has_telemarketing_category'],
        'has_finance_category': flags['has_finance_category'],
        'number_type': numbering.get('number_type', number_type(number)),
        'def_code': numbering.get('def_code', ''),
        'operator': numbering.get('operator', ''),
        'region': numbering.get('region', ''),
        'timezone_offset': numbering.get('timezone_offset', 3),
        'is_mvno': numbering.get('is_mvno', 0),
        'source_reliability': safe_float(reputation.get('source_reliability'), 0.5),
        'view_count': view_count,
        'view_count_log': math.log1p(view_count),
        'related_count': related_count,
        'detail_date': reputation.get('detail_date', ''),
    }
    row.update(compact)
    return row


def generate_smoke_rows(count: int) -> List[Dict]:
    rows = []
    for _ in range(count):
        label = random.choice(['ALLOW', 'WARN', 'BLOCK'])
        if label == 'ALLOW':
            number = f'+7800{random.randint(0, 9999999):07d}'
            negative, positive, category = 0, random.randint(3, 12), ''
        elif label == 'WARN':
            number = f'+7495{random.randint(0, 9999999):07d}'
            negative, positive, category = random.randint(2, 8), random.randint(0, 2), 'спам;телемаркетинг'
        else:
            number = f'+79{random.randint(0, 999999999):09d}'[:12]
            negative, positive, category = random.randint(5, 25), random.randint(0, 1), 'мошенничество'
        rows.append({
            'normalized_number': number,
            'source': 'smoke_synthetic',
            'negative_count': negative,
            'positive_count': positive,
            'neutral_count': 0,
            'review_count': negative + positive,
            'search_volume': random.randint(0, 5000),
            'categories': category,
            'last_review_at': '',
            'first_seen_at': '',
            'source_confidence': 0.5,
            'source_reliability': 0.5,
            'view_count': random.randint(0, 500),
            'related_count': random.randint(0, 10),
            'detail_date': '',
            'page_title': '',
            'url': '',
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description='Build RF metadata dataset')
    parser.add_argument('--smoke-synthetic', type=int, default=0, help='Add synthetic rows only for pipeline smoke tests')
    parser.add_argument('--min-real-block', type=int, default=1, help='Warn if fewer real BLOCK rows exist')
    args = parser.parse_args()

    os.makedirs(PROCESSED_DIR, exist_ok=True)

    numbering_records = load_numbering_csv(os.path.join(RAW_DIR, 'ru_numbering_plan.csv'))
    numbering_plan = NumberingPlan(numbering_records) if numbering_records else None
    print(f'Numbering ranges: {len(numbering_records)}')

    whitelist = load_whitelist()
    reputation_rows = load_reputation_rows() + load_blacklist_rows()
    if args.smoke_synthetic > 0:
        reputation_rows.extend(generate_smoke_rows(args.smoke_synthetic))

    aggregated = aggregate_reputation(reputation_rows)
    all_numbers = sorted(set(whitelist.keys()) | set(aggregated.keys()))

    write_dict_csv(os.path.join(PROCESSED_DIR, 'ru_reputation_raw.csv'), list(aggregated.values()), RAW_REPUTATION_SCHEMA)

    labeled_rows = []
    metadata_rows = []
    tflite_rows = []
    real_block_count = 0

    for number in all_numbers:
        reputation = aggregated.get(number)
        whitelist_info = whitelist.get(number)
        in_public_blacklist = bool(reputation and any(s in reputation.get('source', '') for s in ['moshelovka']))
        label, weight, source = determine_label(number, reputation, whitelist_info, in_public_blacklist)
        if label == 'BLOCK' and source != 'smoke_synthetic':
            real_block_count += 1

        numbering = enrich_numbering(number, numbering_plan)
        signal_meta = {**(reputation or {})}
        if whitelist_info:
            signal_meta['source_confidence'] = whitelist_info.get('source_confidence', signal_meta.get('source_confidence', 0.7))
        feature_record = build_feature_record(number, label, weight, source, signal_meta, numbering)
        metadata_rows.append(feature_record)
        tflite_rows.append(compact_row(number, label, {
            **signal_meta,
            **numbering,
            'source_confidence': feature_record['source_confidence'],
            'inAllowlist': label == 'ALLOW',
            'inBlacklist': label == 'BLOCK',
        }) + [LABEL_TO_ID[label]])
        labeled_rows.append({
            'normalized_number': number,
            'label': label,
            'label_id': LABEL_TO_ID[label],
            'weight': weight,
            'source': source,
            'source_confidence': feature_record['source_confidence'],
        })

    write_dict_csv(os.path.join(PROCESSED_DIR, 'ru_numbers_labeled.csv'), labeled_rows, ['normalized_number', 'label', 'label_id', 'weight', 'source', 'source_confidence'])
    write_dict_csv(os.path.join(PROCESSED_DIR, 'ru_metadata_features.csv'), metadata_rows, FULL_METADATA_FIELDS)
    write_rows_csv(os.path.join(PROCESSED_DIR, 'ru_tflite_features.csv'), COMPACT_FEATURES + ['label'], tflite_rows)

    counts = defaultdict(int)
    for row in labeled_rows:
        counts[row['label']] += 1

    print(f'Total numbers: {len(all_numbers)}')
    print(f'ALLOW={counts["ALLOW"]} WARN={counts["WARN"]} BLOCK={counts["BLOCK"]}')
    print(f'Files written to {PROCESSED_DIR}')

    if real_block_count < args.min_real_block:
        print('WARNING: real BLOCK rows are too few for final training. Use collector/API/manual CSV before export.')


if __name__ == '__main__':
    main()
