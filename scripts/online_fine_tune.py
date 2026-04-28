"""
Online learning: fine-tune models from user feedback.

Reads feedback records from exported CSV, re-trains the best model
with weighted samples (more weight on feedback-corrected labels),
and exports updated TFLite + model card.
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from typing import Dict, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from ru_metadata_features import COMPACT_FEATURES, ID_TO_LABEL, LABEL_TO_ID

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'ru')
PROCESSED_DIR = os.path.join(BASE_DIR, 'processed')
DEFAULT_DATA = os.path.join(PROCESSED_DIR, 'ru_tflite_features.csv')
DEFAULT_TFLITE = os.path.join(os.path.dirname(__file__), '..', 'app', 'src', 'main', 'assets', 'spam_model.tflite')
DEFAULT_MODEL_CARD = os.path.join(os.path.dirname(__file__), '..', 'app', 'src', 'main', 'assets', 'model_card.json')


def load_csv(path: str) -> Tuple[np.ndarray, np.ndarray]:
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f'No rows in {path}')
    features = []
    labels = []
    for row in rows:
        features.append([float(row[name]) for name in COMPACT_FEATURES])
        labels.append(int(float(row['label'])))
    return np.array(features, dtype=np.float32), np.array(labels, dtype=np.int32)


def load_feedback_csv(path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return np.empty((0, len(COMPACT_FEATURES)), dtype=np.float32), np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float32)

    features = []
    corrected_labels = []
    weights = []
    for row in rows:
        feat_vec = [float(row.get(name, 0.0)) for name in COMPACT_FEATURES]
        original_verdict = row.get('verdict', 'ALLOW').upper()
        user_action = row.get('user_action', '').lower()

        if user_action == 'not_spam' and original_verdict == 'BLOCK':
            corrected = LABEL_TO_ID.get('ALLOW', 0)
            weight = 3.0
        elif user_action == 'not_spam' and original_verdict == 'WARN':
            corrected = LABEL_TO_ID.get('ALLOW', 0)
            weight = 2.0
        elif user_action == 'fraud' and original_verdict == 'ALLOW':
            corrected = LABEL_TO_ID.get('BLOCK', 2)
            weight = 3.0
        elif user_action == 'fraud' and original_verdict == 'WARN':
            corrected = LABEL_TO_ID.get('BLOCK', 2)
            weight = 2.0
        elif user_action == 'dismiss' and original_verdict == 'BLOCK':
            corrected = LABEL_TO_ID.get('WARN', 1)
            weight = 1.5
        elif user_action == 'dismiss' and original_verdict == 'WARN':
            corrected = LABEL_TO_ID.get('ALLOW', 0)
            weight = 1.5
        else:
            corrected = LABEL_TO_ID.get(original_verdict, 0)
            weight = 1.0

        features.append(feat_vec)
        corrected_labels.append(corrected)
        weights.append(weight)

    return np.array(features, dtype=np.float32), np.array(corrected_labels, dtype=np.int32), np.array(weights, dtype=np.float32)


def fine_tune(X_base: np.ndarray, y_base: np.ndarray,
              X_fb: np.ndarray, y_fb: np.ndarray, w_fb: np.ndarray,
              alpha: float = 0.3) -> Dict:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, confusion_matrix, precision_recall_fscore_support, roc_auc_score

    if len(X_fb) == 0:
        return {'status': 'no_feedback', 'message': 'No feedback data to fine-tune from'}

    X_combined = np.vstack([X_base, X_fb])
    y_combined = np.concatenate([y_base, y_fb])

    sample_weight = np.ones(len(y_combined), dtype=np.float32)
    sample_weight[len(y_base):] = w_fb * alpha + (1 - alpha)

    stratify = y_combined if len(set(y_combined.tolist())) > 1 and min(np.bincount(y_combined, minlength=3)) > 1 else None
    X_train, X_test, y_train, y_test, sw_train, _ = train_test_split(
        X_combined, y_combined, sample_weight, test_size=0.2, random_state=42, stratify=stratify
    )

    rf = RandomForestClassifier(
        n_estimators=250, max_depth=12, random_state=42,
        class_weight='balanced_subsample', n_jobs=-1
    )
    rf.fit(X_train, y_train, sample_weight=sw_train)
    pred_rf = rf.predict(X_test)
    proba_rf = rf.predict_proba(X_test)

    precision, recall, f1, _ = precision_recall_fscore_support(y_test, pred_rf, labels=[0, 1, 2], zero_division=0)
    result = {
        'status': 'ok',
        'feedback_samples': len(X_fb),
        'total_samples': len(X_combined),
        'alpha': alpha,
        'random_forest': {
            'per_class': {
                ID_TO_LABEL[i]: {'precision': float(precision[i]), 'recall': float(recall[i]), 'f1': float(f1[i])}
                for i in range(3)
            },
            'block_precision': float(precision[2]),
            'block_recall': float(recall[2]),
            'confusion_matrix': confusion_matrix(y_test, pred_rf, labels=[0, 1, 2]).tolist(),
        }
    }
    try:
        result['random_forest']['roc_auc_ovr'] = float(roc_auc_score(y_test, proba_rf, multi_class='ovr', labels=[0, 1, 2]))
    except Exception:
        pass

    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced'))
    lr.fit(X_train, y_train, logisticregression__sample_weight=sw_train)
    pred_lr = lr.predict(X_test)
    precision_lr, recall_lr, f1_lr, _ = precision_recall_fscore_support(y_test, pred_lr, labels=[0, 1, 2], zero_division=0)
    result['logistic_regression'] = {
        'per_class': {
            ID_TO_LABEL[i]: {'precision': float(precision_lr[i]), 'recall': float(recall_lr[i]), 'f1': float(f1_lr[i])}
            for i in range(3)
        },
        'block_precision': float(precision_lr[2]),
        'block_recall': float(recall_lr[2]),
    }

    return result


def main():
    parser = argparse.ArgumentParser(description='Fine-tune models from user feedback')
    parser.add_argument('--base-data', type=str, default=DEFAULT_DATA, help='Base training CSV')
    parser.add_argument('--feedback', type=str, required=True, help='Feedback CSV with user_action column')
    parser.add_argument('--alpha', type=float, default=0.3, help='Feedback weight coefficient (0=ignore, 1=full)')
    parser.add_argument('--export-tflite', action='store_true', help='Export fine-tuned TFLite')
    parser.add_argument('--tflite-output', type=str, default=DEFAULT_TFLITE)
    parser.add_argument('--model-card-output', type=str, default=DEFAULT_MODEL_CARD)
    args = parser.parse_args()

    X_base, y_base = load_csv(args.base_data)
    X_fb, y_fb, w_fb = load_feedback_csv(args.feedback)

    print(f'Base data: {len(y_base)} samples, Feedback: {len(y_fb)} samples (alpha={args.alpha})')
    result = fine_tune(X_base, y_base, X_fb, y_fb, w_fb, alpha=args.alpha)

    if result['status'] != 'ok':
        print(f'Fine-tune skipped: {result["message"]}')
        return

    for model_name in ('random_forest', 'logistic_regression'):
        m = result.get(model_name, {})
        bp = m.get('block_precision', 0)
        br = m.get('block_recall', 0)
        print(f'  {model_name}: BLOCK P={bp:.3f}, R={br:.3f}')

    if args.export_tflite:
        try:
            import tensorflow as tf
        except ImportError:
            print('TensorFlow not installed, cannot export TFLite')
            return

        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split

        X_combined = np.vstack([X_base, X_fb])
        y_combined = np.concatenate([y_base, y_fb])
        sw = np.ones(len(y_combined), dtype=np.float32)
        sw[len(y_base):] = w_fb * args.alpha + (1 - args.alpha)

        stratify = y_combined if len(set(y_combined.tolist())) > 1 else None
        X_train, X_test, y_train, y_test, sw_train, _ = train_test_split(
            X_combined, y_combined, sw, test_size=0.2, random_state=42, stratify=stratify
        )

        counts = np.bincount(y_train.astype(int), minlength=3)
        total = len(y_train)
        class_weight = {i: float(total / (3 * counts[i])) if counts[i] > 0 else 1.0 for i in range(3)}

        model = tf.keras.Sequential([
            tf.keras.layers.Input(shape=(len(COMPACT_FEATURES),)),
            tf.keras.layers.Dense(48, activation='relu'),
            tf.keras.layers.Dropout(0.15),
            tf.keras.layers.Dense(24, activation='relu'),
            tf.keras.layers.Dropout(0.10),
            tf.keras.layers.Dense(12, activation='relu'),
            tf.keras.layers.Dense(3, activation='softmax'),
        ])
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            loss='sparse_categorical_crossentropy',
            metrics=['accuracy'],
        )
        model.fit(X_train, y_train, validation_data=(X_test, y_test), epochs=35, batch_size=32,
                  class_weight=class_weight, sample_weight=sw_train, verbose=0)

        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_model = converter.convert()
        os.makedirs(os.path.dirname(args.tflite_output), exist_ok=True)
        with open(args.tflite_output, 'wb') as f:
            f.write(tflite_model)
        print(f'Exported TFLite: {len(tflite_model):,} bytes → {args.tflite_output}')

        card = {
            'version': f"feedback-tuned-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            'created_at': datetime.now().isoformat(),
            'feature_count': len(COMPACT_FEATURES),
            'features': COMPACT_FEATURES,
            'rows': len(y_combined),
            'feedback_samples': len(X_fb),
            'alpha': args.alpha,
            'class_counts': {ID_TO_LABEL.get(i, str(i)): int(np.sum(y_combined == i)) for i in range(3)},
            'best_model': 'tflite_mlp_feedback_tuned',
            'block_precision': result['random_forest']['block_precision'],
            'block_recall': result['random_forest']['block_recall'],
            'notes': 'Fine-tuned with user feedback via scripts/online_fine_tune.py',
        }
        with open(args.model_card_output, 'w', encoding='utf-8') as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
        print(f'Model card saved: {args.model_card_output}')


if __name__ == '__main__':
    main()
