"""
Feature engineering для РФ metadata-pipeline.

Содержит единый порядок компактных признаков для TFLite/Android.
"""

import math
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from ru_number_normalizer import (
    normalize_ru_phone,
    is_russian_number,
    is_mobile_ru,
    is_landline_ru,
    is_tollfree_ru,
    is_short_code,
)

FEATURES_VERSION = 2

# Перевод заголовков CSV: английский → русский
FIELD_TO_RU = {
    'normalized_number': 'номер',
    'source': 'источник',
    'label': 'метка',
    'label_id': 'id_метки',
    'weight': 'вес',
    'label_hint': 'подсказка_метки',
    'evidence_type': 'тип_доказательства',
    'evidence_text': 'текст_доказательства',
    'full_text': 'полный_текст',
    'page_title': 'заголовок_страницы',
    'negative_count': 'негативных',
    'positive_count': 'позитивных',
    'neutral_count': 'нейтральных',
    'review_count': 'отзывов',
    'view_count': 'просмотров',
    'related_count': 'связанных',
    'categories': 'категории',
    'source_confidence': 'уверенность_источника',
    'source_reliability': 'надёжность_источника',
    'detail_date': 'дата_детали',
    'fraud_hits': 'мошеннических_совпадений',
    'warn_hits': 'предупреждений',
    'url': 'ссылка',
    'collected_at': 'собрано',
    'search_volume': 'объём_поиска',
    'search_volume_log': 'лог_объёма_поиска',
    'last_review_at': 'последний_отзыв',
    'first_seen_at': 'первое_появление',
    'negative_ratio': 'доля_негативных',
    'positive_ratio': 'доля_позитивных',
    'review_velocity_48h': 'скорость_отзывов_48ч',
    'review_velocity_7d': 'скорость_отзывов_7д',
    'has_fraud_category': 'есть_мошенничество',
    'has_telemarketing_category': 'есть_телемаркетинг',
    'has_finance_category': 'есть_финансы',
    'number_type': 'тип_номера',
    'def_code': 'деф_код',
    'operator': 'оператор',
    'region': 'регион',
    'timezone_offset': 'смещение_часового_пояса',
    'is_mvno': 'мвно',
    'view_count_log': 'лог_просмотров',
    'isContact': 'в_контактах',
    'isRussianNumber': 'российский_номер',
    'isForeignNumber': 'иностранный_номер',
    'isShortCode': 'короткий_номер',
    'isStandardLen': 'стандартная_длина',
    'isTollFree8800': 'бесплатный_8800',
    'isGeographical': 'географический',
    'isMobileRu': 'мобильный_рф',
    'isValidRuRange': 'валидный_диапазон_рф',
    'spoofingPrefixFlag': 'флаг_подмены_префикса',
    'digitEntropy': 'энтропия_цифр',
    'repeatDigitRatio': 'доля_повторов_цифр',
    'maxSameDigitRun': 'макс_повтор_цифры',
    'beautifulNumberFlag': 'красивый_номер',
    'prefixRisk': 'риск_префикса',
    'callFrequency': 'частота_звонков',
    'isNightTime': 'ночное_время',
    'recentBankApp': 'недавнее_приложение_банка',
    'recentGovApp': 'недавнее_приложение_госуслуг',
    'recentMarketplaceApp': 'недавнее_приложение_маркетплейса',
    'recentMessengerApp': 'недавнее_приложение_мессенджера',
    'previouslyRejected': 'ранее_отклонён',
    'inBlacklist': 'в_чёрном_списке',
    'inAllowlist': 'в_белом_списке',
    'hiddenNumber': 'скрытый_номер',
    'callerVerifyFailed': 'проверка_звонящего_не_пройдена',
    'userVulnerability': 'уязвимость_пользователя',
    'userBusinessActivity': 'деловая_активность',
    'contactsAvailable': 'контакты_доступны',
    'usageAccessAvailable': 'доступ_к_использованию',
    'reputationScore': 'рейтинг_репутации',
    'sourceConfidence': 'уверенность_источника_компакт',
}
RU_TO_FIELD = {v: k for k, v in FIELD_TO_RU.items()}


def translate_headers(fields: Sequence[str], to_ru: bool = True) -> List[str]:
    """Перевести список заголовков: en→ru (to_ru=True) или ru→en (to_ru=False)."""
    mapping = FIELD_TO_RU if to_ru else RU_TO_FIELD
    return [mapping.get(f, f) for f in fields]


def translate_row(row: Dict, to_ru: bool = True) -> Dict:
    """Перевести ключи словаря строки: en→ru или ru→en."""
    mapping = FIELD_TO_RU if to_ru else RU_TO_FIELD
    return {mapping.get(k, k): v for k, v in row.items()}

COMPACT_FEATURES = [
    'isContact',
    'isRussianNumber',
    'isForeignNumber',
    'isShortCode',
    'isStandardLen',
    'isTollFree8800',
    'isGeographical',
    'isMobileRu',
    'isValidRuRange',
    'spoofingPrefixFlag',
    'digitEntropy',
    'repeatDigitRatio',
    'maxSameDigitRun',
    'beautifulNumberFlag',
    'prefixRisk',
    'callFrequency',
    'isNightTime',
    'recentBankApp',
    'recentGovApp',
    'recentMarketplaceApp',
    'recentMessengerApp',
    'previouslyRejected',
    'inBlacklist',
    'inAllowlist',
    'hiddenNumber',
    'callerVerifyFailed',
    'userVulnerability',
    'userBusinessActivity',
    'contactsAvailable',
    'usageAccessAvailable',
    'reputationScore',
    'sourceConfidence',
]

FULL_METADATA_FIELDS = [
    'normalized_number',
    'label',
    'label_id',
    'weight',
    'source',
    'source_confidence',
    'negative_count',
    'positive_count',
    'neutral_count',
    'review_count',
    'negative_ratio',
    'positive_ratio',
    'search_volume',
    'search_volume_log',
    'review_velocity_48h',
    'review_velocity_7d',
    'has_fraud_category',
    'has_telemarketing_category',
    'has_finance_category',
    'number_type',
    'def_code',
    'operator',
    'region',
    'timezone_offset',
    'is_mvno',
    'source_reliability',
    'view_count',
    'view_count_log',
    'related_count',
    'detail_date',
] + COMPACT_FEATURES

LABEL_TO_ID = {
    'ALLOW': 0,
    'WARN': 1,
    'BLOCK': 2,
}

ID_TO_LABEL = {v: k for k, v in LABEL_TO_ID.items()}

FRAUD_KEYWORDS = {
    'мошен', 'фрод', 'scam', 'fraud', 'фишинг', 'вымог', 'служба безопасности',
    'подозр', 'обман', 'карта', 'банк мошен', 'безопасности банка',
}

TELEMARKETING_KEYWORDS = {
    'спам', 'реклама', 'телемаркетинг', 'колл', 'опрос', 'робот', 'робозвон',
    'навязы', 'займ', 'кредит', 'мфо', 'коллектор', 'продажи',
}

FINANCE_KEYWORDS = {
    'банк', 'кредит', 'займ', 'мфо', 'карта', 'финанс', 'страхов',
}

MVNO_HINTS = {
    'tinkoff', 'тинькофф мобайл', 'yota', 'йота', 'сбермобайл', 'ростелеком',
    'газпромбанк мобайл', 'втб мобайл', 'алло инкогнито',
}


def digits_only(value: Optional[str]) -> str:
    return ''.join(ch for ch in (value or '') if ch.isdigit())


def clamp01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def safe_int(value, default: int = 0) -> int:
    try:
        if value is None or value == '':
            return default
        return int(float(str(value).replace(',', '.')))
    except Exception:
        return default


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(str(value).replace(',', '.'))
    except Exception:
        return default


def shannon_entropy(digits: str) -> float:
    if not digits:
        return 0.0
    counts = {d: digits.count(d) for d in set(digits)}
    entropy = 0.0
    for count in counts.values():
        p = count / len(digits)
        entropy -= p * math.log2(p)
    return entropy / math.log2(10)  # normalize roughly to 0..1


def repeat_digit_ratio(digits: str) -> float:
    if len(digits) <= 1:
        return 0.0
    repeats = sum(1 for i in range(1, len(digits)) if digits[i] == digits[i - 1])
    return repeats / (len(digits) - 1)


def max_same_digit_run(digits: str) -> float:
    if not digits:
        return 0.0
    best = 1
    current = 1
    for i in range(1, len(digits)):
        if digits[i] == digits[i - 1]:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return min(best / max(len(digits), 1), 1.0)


def has_monotonic_run(digits: str, min_run: int = 4) -> bool:
    if len(digits) < min_run:
        return False
    for i in range(0, len(digits) - min_run + 1):
        chunk = digits[i:i + min_run]
        asc = all(int(chunk[j]) == (int(chunk[j - 1]) + 1) % 10 for j in range(1, len(chunk)))
        desc = all(int(chunk[j]) == (int(chunk[j - 1]) - 1) % 10 for j in range(1, len(chunk)))
        if asc or desc:
            return True
    return False


def beautiful_number_flag(digits: str) -> bool:
    if not digits:
        return False
    tail = digits[-7:]
    return (
        repeat_digit_ratio(tail) >= 0.45
        or max_same_digit_run(tail) >= 4 / max(len(tail), 1)
        or bool(re.search(r'(\d{2,3})\1+', tail))
        or has_monotonic_run(tail)
    )


def spoofing_prefix_flag(raw_number: Optional[str], normalized_number: Optional[str]) -> bool:
    raw = (raw_number or normalized_number or '').strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    digits = digits_only(raw)
    if raw.startswith('+84') and digits.startswith('8495'):
        return True
    if raw.startswith('0084') and digits.startswith('008495'):
        return True
    if normalized_number and normalized_number.startswith('+84') and digits_only(normalized_number).startswith('8495'):
        return True
    return False


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d.%m.%Y', '%d.%m.%Y %H:%M'):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def review_velocity(last_review_at: Optional[str], first_seen_at: Optional[str], review_count: int, window_days: int) -> float:
    last_dt = parse_date(last_review_at)
    first_dt = parse_date(first_seen_at)
    if not last_dt or not first_dt or review_count <= 0:
        return 0.0
    age_days = max((last_dt - first_dt).total_seconds() / 86400.0, 1.0)
    return clamp01((review_count / age_days) / max(window_days, 1))


def category_flags(categories: Optional[str]) -> Dict[str, float]:
    text = (categories or '').lower()
    return {
        'has_fraud_category': 1.0 if any(k in text for k in FRAUD_KEYWORDS) else 0.0,
        'has_telemarketing_category': 1.0 if any(k in text for k in TELEMARKETING_KEYWORDS) else 0.0,
        'has_finance_category': 1.0 if any(k in text for k in FINANCE_KEYWORDS) else 0.0,
    }


def operator_bucket(operator: Optional[str]) -> str:
    text = (operator or '').strip().lower()
    if not text:
        return 'unknown'
    if 'мтс' in text or 'mts' in text:
        return 'mts'
    if 'мегафон' in text or 'megafon' in text:
        return 'megafon'
    if 'билайн' in text or 'beeline' in text or 'вымпел' in text:
        return 'beeline'
    if 'tele2' in text or 'теле2' in text or 't2' in text:
        return 'tele2'
    if any(h in text for h in MVNO_HINTS):
        return 'mvno'
    return 'other'


def stable_bucket(value: Optional[str], buckets: int = 16) -> int:
    text = (value or '').lower().strip()
    if not text:
        return 0
    acc = 0
    for ch in text:
        acc = (acc * 31 + ord(ch)) % 1000003
    return acc % buckets


def number_type(normalized_number: Optional[str]) -> str:
    if not normalized_number:
        return 'unknown'
    if is_short_code(normalized_number):
        return 'short'
    if is_tollfree_ru(normalized_number):
        return 'tollfree'
    if is_mobile_ru(normalized_number):
        return 'mobile'
    if is_landline_ru(normalized_number):
        return 'landline'
    if normalized_number.startswith('+7'):
        return 'ru_other'
    return 'foreign'


def infer_prefix_risk(normalized_number: Optional[str], metadata: Dict) -> float:
    if not normalized_number:
        return 0.0
    if metadata.get('inAllowlist') or metadata.get('label') == 'ALLOW':
        return 0.0
    digits = digits_only(normalized_number)
    if normalized_number.startswith('+7800'):
        return 0.25
    if normalized_number.startswith('+7495') or normalized_number.startswith('+7499'):
        return 0.35
    if len(digits) >= 4 and digits.startswith('79'):
        def_code = safe_int(digits[1:4], 0)
        if def_code in {900, 901, 902, 903, 904, 905, 906, 908, 909, 950, 951, 952, 953, 958, 966, 969}:
            return 0.65
        return 0.3
    if normalized_number.startswith('+84'):
        return 0.8
    return 0.1


def compute_reputation_score(negative_ratio: float, review_count: int, search_volume: int, flags: Dict[str, float]) -> float:
    review_component = clamp01(math.log1p(review_count) / math.log1p(100))
    search_component = clamp01(math.log1p(search_volume) / math.log1p(10000))
    fraud_boost = 0.25 if flags.get('has_fraud_category', 0.0) else 0.0
    telemarketing_boost = 0.12 if flags.get('has_telemarketing_category', 0.0) else 0.0
    return clamp01(negative_ratio * 0.55 + review_component * 0.15 + search_component * 0.15 + fraud_boost + telemarketing_boost)


def compact_feature_vector(
    normalized_number: Optional[str],
    label: str,
    metadata: Dict,
    raw_number: Optional[str] = None,
) -> Dict[str, float]:
    digits = digits_only(normalized_number or raw_number)
    is_ru = bool(normalized_number and is_russian_number(normalized_number))
    is_foreign = bool(normalized_number and normalized_number.startswith('+') and not normalized_number.startswith('+7'))
    n_type = number_type(normalized_number)
    flags = category_flags(metadata.get('categories', ''))

    negative = safe_int(metadata.get('negative_count'))
    positive = safe_int(metadata.get('positive_count'))
    neutral = safe_int(metadata.get('neutral_count'))
    review_count = safe_int(metadata.get('review_count'), negative + positive + neutral)
    if review_count <= 0:
        review_count = negative + positive + neutral
    search_volume = safe_int(metadata.get('search_volume'))
    total_votes = max(negative + positive + neutral, review_count, 1)
    negative_ratio = negative / total_votes

    source_confidence = clamp01(safe_float(metadata.get('source_confidence'), safe_float(metadata.get('confidence'), 0.5)))
    reputation = compute_reputation_score(negative_ratio, review_count, search_volume, flags)

    operator = metadata.get('operator', '')
    is_valid_range = bool(metadata.get('is_valid_ru_range'))
    if metadata.get('numbering_match') is not None:
        is_valid_range = bool(metadata.get('numbering_match'))

    label_upper = (label or '').upper()

    values = {
        'isContact': 1.0 if metadata.get('isContact') else 0.0,
        'isRussianNumber': 1.0 if is_ru else 0.0,
        'isForeignNumber': 1.0 if is_foreign else 0.0,
        'isShortCode': 1.0 if n_type == 'short' else 0.0,
        'isStandardLen': 1.0 if len(digits) == 11 and digits.startswith(('7', '8')) else 0.0,
        'isTollFree8800': 1.0 if n_type == 'tollfree' else 0.0,
        'isGeographical': 1.0 if n_type == 'landline' else 0.0,
        'isMobileRu': 1.0 if n_type == 'mobile' else 0.0,
        'isValidRuRange': 1.0 if is_valid_range else 0.0,
        'spoofingPrefixFlag': 1.0 if spoofing_prefix_flag(raw_number, normalized_number) else 0.0,
        'digitEntropy': clamp01(shannon_entropy(digits)),
        'repeatDigitRatio': clamp01(repeat_digit_ratio(digits)),
        'maxSameDigitRun': clamp01(max_same_digit_run(digits)),
        'beautifulNumberFlag': 1.0 if beautiful_number_flag(digits) else 0.0,
        'prefixRisk': clamp01(infer_prefix_risk(normalized_number, {'label': label_upper, **metadata})),
        'callFrequency': clamp01(safe_float(metadata.get('callFrequency'), 0.0)),
        'isNightTime': 1.0 if metadata.get('isNightTime') else 0.0,
        'recentBankApp': 1.0 if metadata.get('recentBankApp') else 0.0,
        'recentGovApp': 1.0 if metadata.get('recentGovApp') else 0.0,
        'recentMarketplaceApp': 1.0 if metadata.get('recentMarketplaceApp') else 0.0,
        'recentMessengerApp': 1.0 if metadata.get('recentMessengerApp') else 0.0,
        'previouslyRejected': 1.0 if metadata.get('previouslyRejected') else 0.0,
        'inBlacklist': 1.0 if label_upper == 'BLOCK' or metadata.get('inBlacklist') else 0.0,
        'inAllowlist': 1.0 if label_upper == 'ALLOW' or metadata.get('inAllowlist') else 0.0,
        'hiddenNumber': 1.0 if metadata.get('hiddenNumber') else 0.0,
        'callerVerifyFailed': 1.0 if metadata.get('callerVerifyFailed') else 0.0,
        'userVulnerability': clamp01(safe_float(metadata.get('userVulnerability'), 0.35)),
        'userBusinessActivity': clamp01(safe_float(metadata.get('userBusinessActivity'), 0.45)),
        'contactsAvailable': 1.0 if metadata.get('contactsAvailable', True) else 0.0,
        'usageAccessAvailable': 1.0 if metadata.get('usageAccessAvailable') else 0.0,
        'reputationScore': reputation,
        'sourceConfidence': source_confidence,
    }
    return values


def compact_row(normalized_number: Optional[str], label: str, metadata: Dict, raw_number: Optional[str] = None) -> Sequence[float]:
    values = compact_feature_vector(normalized_number, label, metadata, raw_number)
    return [values[name] for name in COMPACT_FEATURES]
