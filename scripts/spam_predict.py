"""Predict ALLOW/WARN/BLOCK для одного телефонного номера через TFLite-модель.

Usage:
    python scripts/spam_predict.py +79991234567
    python scripts/spam_predict.py +79991234567 +74957754747 +78005553535
    python scripts/spam_predict.py --features-csv my_features.csv +79991234567

Алгоритм:
    1. Нормализуем входной номер (+7XXXXXXXXXX).
    2. Если в processed/ru_metadata_features.csv (русские заголовки) находим строку с тем же
       номером — берём готовый компакт-вектор оттуда. Это «реалистичный» сценарий: номер уже
       видели в датасете, есть репутация, источник, in/black/whitelist.
    3. Иначе считаем фичи с нуля через compact_feature_vector + пустую metadata. Это
       «холодный старт» — что приложение знает о номере на момент звонка, если его нет
       ни в одном бандл-списке.
    4. Прогоняем через TFLite (FP32, [1, 32] -> [1, 3] softmax).
    5. Применяем thresholds из model_card.json (block_threshold, warn_threshold) если они есть,
       иначе argmax.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from ru_metadata_features import (
    COMPACT_FEATURES,
    FIELD_TO_RU,
    ID_TO_LABEL,
    compact_feature_vector,
)
from ru_number_normalizer import normalize_ru_phone

BASE_DIR = os.path.join(os.path.dirname(__file__), '..')
DEFAULT_MODEL = os.path.join(BASE_DIR, 'app', 'src', 'main', 'assets', 'spam_model.tflite')
DEFAULT_CARD = os.path.join(BASE_DIR, 'app', 'src', 'main', 'assets', 'model_card.json')
DEFAULT_FEATURES_CSV = os.path.join(BASE_DIR, 'datasets', 'ru', 'processed', 'ru_metadata_features.csv')


def load_thresholds(card_path: str) -> Optional[Tuple[float, float]]:
    if not os.path.isfile(card_path):
        return None
    try:
        with open(card_path, 'r', encoding='utf-8') as f:
            card = json.load(f)
    except Exception:
        return None
    thr = card.get('thresholds') or {}
    bt = thr.get('block_threshold')
    wt = thr.get('warn_threshold')
    if bt is None or wt is None:
        return None
    return float(bt), float(wt)


def lookup_features_for(number: str, features_csv: str) -> Optional[Dict[str, float]]:
    """Найти готовый компакт-вектор для номера в processed/ru_metadata_features.csv."""
    if not os.path.isfile(features_csv):
        return None
    ru_to_eng = {v: k for k, v in FIELD_TO_RU.items()}
    with open(features_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            num = row.get('номер') or row.get('normalized_number') or row.get('number')
            if num != number:
                continue
            features: Dict[str, float] = {}
            for eng in COMPACT_FEATURES:
                ru = FIELD_TO_RU.get(eng, eng)
                raw = row.get(ru)
                if raw is None or raw == '':
                    raw = row.get(eng)
                if raw is None or raw == '':
                    return None
                features[eng] = float(raw)
            return features
    return None


def features_from_scratch(number: str) -> Dict[str, float]:
    """Холодный старт: метадата = {}, isContact / inBlacklist / inAllowlist = 0."""
    return compact_feature_vector(number, label='UNKNOWN', metadata={})


def run_tflite(model_path: str, x: List[float]):
    import numpy as np
    import tensorflow as tf
    interp = tf.lite.Interpreter(model_path=model_path)
    interp.allocate_tensors()
    in_d = interp.get_input_details()[0]
    out_d = interp.get_output_details()[0]
    arr = np.asarray(x, dtype=np.float32).reshape(1, -1)
    interp.set_tensor(in_d['index'], arr)
    interp.invoke()
    return interp.get_tensor(out_d['index']).reshape(-1).tolist()


def verdict_from(probs: List[float], thresholds: Optional[Tuple[float, float]]) -> str:
    allow_p, warn_p, block_p = probs
    if thresholds is not None:
        block_t, warn_t = thresholds
        if block_p >= block_t:
            return 'BLOCK'
        if warn_p >= warn_t:
            return 'WARN'
        return 'ALLOW'
    # argmax fallback
    idx = max(range(3), key=lambda i: probs[i])
    return ID_TO_LABEL.get(idx, 'ALLOW')


def predict_one(number_in: str, model_path: str, thresholds: Optional[Tuple[float, float]],
                features_csv: str, force_cold: bool = False) -> Dict:
    norm = normalize_ru_phone(number_in)
    if not norm:
        return {'input': number_in, 'error': 'invalid_number'}
    features = None if force_cold else lookup_features_for(norm, features_csv)
    source = 'dataset' if features is not None else 'cold'
    if features is None:
        features = features_from_scratch(norm)
    vec = [features[name] for name in COMPACT_FEATURES]
    probs = run_tflite(model_path, vec)
    verdict = verdict_from(probs, thresholds)
    return {
        'input': number_in,
        'normalized': norm,
        'feature_source': source,
        'probs': {'ALLOW': probs[0], 'WARN': probs[1], 'BLOCK': probs[2]},
        'verdict': verdict,
        'risk_score': int(round(probs[2] * 100)),
        'features': features,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('numbers', nargs='+', help='Один или несколько телефонных номеров.')
    ap.add_argument('--model', default=DEFAULT_MODEL, help=f'Путь к .tflite (default: {DEFAULT_MODEL}).')
    ap.add_argument('--card', default=DEFAULT_CARD, help=f'Путь к model_card.json (default: {DEFAULT_CARD}).')
    ap.add_argument('--features-csv', default=DEFAULT_FEATURES_CSV,
                    help='Lookup CSV с метадатой по номерам (default: ru_metadata_features.csv).')
    ap.add_argument('--cold', action='store_true',
                    help='Игнорировать lookup CSV; считать фичи с нуля (как «неизвестный номер»).')
    ap.add_argument('--show-features', action='store_true', help='Распечатать все 32 фичи.')
    ap.add_argument('--json', action='store_true', help='Вывести результат как JSON.')
    args = ap.parse_args()

    if not os.path.isfile(args.model):
        print(f'ERROR: model not found: {args.model}', file=sys.stderr)
        return 2

    thresholds = load_thresholds(args.card)
    if thresholds:
        print(f'  thresholds from model_card.json: block={thresholds[0]:.3f} warn={thresholds[1]:.3f}')
    else:
        print('  no thresholds in model_card.json — falling back to argmax')

    results = [predict_one(n, args.model, thresholds, args.features_csv, force_cold=args.cold)
               for n in args.numbers]

    if args.json:
        for r in results:
            r.pop('features', None) if not args.show_features else None
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    for r in results:
        if 'error' in r:
            print(f'\n{r["input"]:20s} → ERROR: {r["error"]}')
            continue
        p = r['probs']
        print(f'\n{r["input"]:20s} → {r["normalized"]:15s} [{r["feature_source"]}]')
        print(f'  probs:    ALLOW={p["ALLOW"]:.4f}  WARN={p["WARN"]:.4f}  BLOCK={p["BLOCK"]:.4f}')
        print(f'  verdict:  {r["verdict"]}     risk_score={r["risk_score"]}')
        if args.show_features:
            for k, v in r['features'].items():
                print(f'    {k:24s} = {v:.4f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
