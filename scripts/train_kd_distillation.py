"""
Knowledge Distillation: CatBoost teacher → Keras MLP student → TFLite

Отдельный пайплайн, не трогает train_ru_metadata_models.py.
Конечная цель: компактный TFLite [1, 32] -> [1, 3] (ALLOW/WARN/BLOCK), совместимый
с существующим Android SpamModel.kt (FloatArray вход, 3 Float выхода).

Решения по результатам ревью плана:
  - Без feature embeddings: большинство COMPACT_FEATURES бинарные.
  - Без Platt/Isotonic-калибровки teacher: T-scaling уже даёт smoothing.
  - Soft targets берутся ТОЛЬКО с реальных train-точек (не с SMOTE-синтетики),
    чтобы student не учился на интерполированных predictions.
  - Hyperparam search в два этапа: (a) grid (T, alpha) — 9 trials,
    (b) Optuna (lr, dropout, hidden) на лучших T, alpha.
  - Sanity check: |p_keras - p_tflite| < 1e-4 на 200 семплах.
  - Пороги BLOCK / WARN тюнятся на val, пишутся в model_card.json
    в стандартную секцию `thresholds` (поле уже читается ModelCard.kt).
  - Бэкап старого .tflite и model_card.json в reports/<run>/before/.

Sample sizes (по умолчанию):
  --teacher-train-per-class 6000  (6k legit + 6k spam = 12k для обучения teacher)
  --student-train-per-class 4000  (4k legit + 4k spam = 8k подвыборка teacher train)
  Если в данных меньше указанного — печатается warning и берётся реальный максимум,
  если не передан --pad-with-smote.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import shutil
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from ru_metadata_features import COMPACT_FEATURES, FIELD_TO_RU, ID_TO_LABEL, LABEL_TO_ID

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'ru')
PROCESSED_DIR = os.path.join(BASE_DIR, 'processed')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
DEFAULT_DATA = os.path.join(PROCESSED_DIR, 'ru_tflite_features.csv')
ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'app', 'src', 'main', 'assets')
DEFAULT_TFLITE = os.path.join(ASSETS_DIR, 'spam_model.tflite')
DEFAULT_MODEL_CARD = os.path.join(ASSETS_DIR, 'model_card.json')

LEGIT_LABELS = (LABEL_TO_ID['ALLOW'],)
SPAM_LABELS = (LABEL_TO_ID['WARN'], LABEL_TO_ID['BLOCK'])
NUM_CLASSES = 3


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def set_global_seed(seed: int) -> None:
    """Pin seed for numpy / random / torch (if loaded) / tf (if loaded) / sklearn."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    try:
        import tensorflow as tf
        tf.random.set_seed(seed)
        tf.keras.utils.set_random_seed(seed)
    except Exception:
        pass


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Load CSV with COMPACT_FEATURES + label.

    Принимает оба варианта заголовков:
      - английские: 'isContact', ..., 'label'
      - русские:    'в_контактах', ..., 'метка' (формат builder-а)
    """
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise SystemExit(f'No rows in {path}')

    headers = list(rows[0].keys())
    has_english = all(name in headers for name in COMPACT_FEATURES)
    if has_english:
        feature_keys = {name: name for name in COMPACT_FEATURES}
        label_key = 'label' if 'label' in headers else 'метка'
    else:
        # russian headers — translate via FIELD_TO_RU
        feature_keys = {name: FIELD_TO_RU.get(name, name) for name in COMPACT_FEATURES}
        label_key = FIELD_TO_RU.get('label', 'метка')

    missing = [eng for eng, ru in feature_keys.items() if ru not in headers]
    if missing:
        raise SystemExit(
            f'CSV missing features ({len(missing)}): {missing[:5]}{"..." if len(missing) > 5 else ""}'
            f'\nHeaders sample: {headers[:5]}'
        )
    if label_key not in headers:
        raise SystemExit(f"CSV missing label column ('label' or 'метка'). Headers: {headers[:8]}...")

    X = np.array(
        [[float(row[feature_keys[name]]) for name in COMPACT_FEATURES] for row in rows],
        dtype=np.float32,
    )
    raw_labels = [row[label_key] for row in rows]
    # label may be int code (0/1/2) or string ('ALLOW'/'WARN'/'BLOCK')
    y_list: List[int] = []
    for v in raw_labels:
        s = str(v).strip()
        if s in LABEL_TO_ID:
            y_list.append(LABEL_TO_ID[s])
        else:
            y_list.append(int(float(s)))
    y = np.array(y_list, dtype=np.int64)
    return X, y


def class_counts(y: np.ndarray) -> Dict[str, int]:
    return {ID_TO_LABEL.get(i, str(i)): int(np.sum(y == i)) for i in range(NUM_CLASSES)}


# ---------------------------------------------------------------------------
# Sampling: stratified pools + teacher/student train subsets
# ---------------------------------------------------------------------------

def stratified_split(
    X: np.ndarray, y: np.ndarray, sizes: Tuple[float, float, float], seed: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return three np.ndarray index arrays (train, val, test) preserving per-class ratios."""
    assert abs(sum(sizes) - 1.0) < 1e-6, sizes
    rng = np.random.default_rng(seed)
    train_idx, val_idx, test_idx = [], [], []
    for cls in range(NUM_CLASSES):
        cls_idx = np.where(y == cls)[0]
        rng.shuffle(cls_idx)
        n = len(cls_idx)
        n_train = int(round(n * sizes[0]))
        n_val = int(round(n * sizes[1]))
        train_idx.extend(cls_idx[:n_train].tolist())
        val_idx.extend(cls_idx[n_train:n_train + n_val].tolist())
        test_idx.extend(cls_idx[n_train + n_val:].tolist())
    return (
        np.array(sorted(train_idx), dtype=np.int64),
        np.array(sorted(val_idx), dtype=np.int64),
        np.array(sorted(test_idx), dtype=np.int64),
    )


def sample_teacher_train(
    train_idx: np.ndarray,
    y: np.ndarray,
    legit_target: int,
    spam_target: int,
    seed: int,
) -> Tuple[np.ndarray, Dict[str, int], List[str]]:
    """Sample N legit (ALLOW) + N spam (WARN+BLOCK) from train pool.

    Spam sampling preserves WARN/BLOCK ratio inside the train pool.
    Returns (sampled_indices, actual_counts, warnings_list).
    """
    rng = np.random.default_rng(seed)
    warnings: List[str] = []

    # Legit bucket
    legit_pool = train_idx[np.isin(y[train_idx], LEGIT_LABELS)]
    if len(legit_pool) < legit_target:
        warnings.append(
            f'requested {legit_target} legit (ALLOW), only {len(legit_pool)} available in train pool — using all'
        )
        legit_pick = legit_pool.copy()
    else:
        legit_pick = rng.choice(legit_pool, size=legit_target, replace=False)

    # Spam bucket — keep WARN/BLOCK ratio
    spam_pool = train_idx[np.isin(y[train_idx], SPAM_LABELS)]
    if len(spam_pool) < spam_target:
        warnings.append(
            f'requested {spam_target} spam (WARN+BLOCK), only {len(spam_pool)} available in train pool — using all'
        )
        spam_pick = spam_pool.copy()
    else:
        warn_pool = train_idx[y[train_idx] == LABEL_TO_ID['WARN']]
        block_pool = train_idx[y[train_idx] == LABEL_TO_ID['BLOCK']]
        total_spam = len(warn_pool) + len(block_pool)
        warn_share = len(warn_pool) / max(total_spam, 1)
        n_warn = min(int(round(spam_target * warn_share)), len(warn_pool))
        n_block = min(spam_target - n_warn, len(block_pool))
        spam_pick = np.concatenate([
            rng.choice(warn_pool, size=n_warn, replace=False) if n_warn else np.array([], dtype=np.int64),
            rng.choice(block_pool, size=n_block, replace=False) if n_block else np.array([], dtype=np.int64),
        ])

    sampled = np.concatenate([legit_pick, spam_pick]).astype(np.int64)
    sampled.sort()
    return sampled, class_counts(y[sampled]), warnings


def sample_student_train_subset(
    teacher_idx: np.ndarray,
    y: np.ndarray,
    legit_target: int,
    spam_target: int,
    seed: int,
) -> Tuple[np.ndarray, Dict[str, int], List[str]]:
    """Sample student train as a subset of teacher train (smaller distillation set)."""
    rng = np.random.default_rng(seed + 1)
    warnings: List[str] = []

    legit_pool = teacher_idx[np.isin(y[teacher_idx], LEGIT_LABELS)]
    spam_pool = teacher_idx[np.isin(y[teacher_idx], SPAM_LABELS)]

    if len(legit_pool) < legit_target:
        warnings.append(
            f'student: requested {legit_target} legit, only {len(legit_pool)} in teacher train — using all'
        )
        legit_pick = legit_pool.copy()
    else:
        legit_pick = rng.choice(legit_pool, size=legit_target, replace=False)

    if len(spam_pool) < spam_target:
        warnings.append(
            f'student: requested {spam_target} spam, only {len(spam_pool)} in teacher train — using all'
        )
        spam_pick = spam_pool.copy()
    else:
        warn_pool = teacher_idx[y[teacher_idx] == LABEL_TO_ID['WARN']]
        block_pool = teacher_idx[y[teacher_idx] == LABEL_TO_ID['BLOCK']]
        total_spam = len(warn_pool) + len(block_pool)
        warn_share = len(warn_pool) / max(total_spam, 1)
        n_warn = min(int(round(spam_target * warn_share)), len(warn_pool))
        n_block = min(spam_target - n_warn, len(block_pool))
        spam_pick = np.concatenate([
            rng.choice(warn_pool, size=n_warn, replace=False) if n_warn else np.array([], dtype=np.int64),
            rng.choice(block_pool, size=n_block, replace=False) if n_block else np.array([], dtype=np.int64),
        ])

    sampled = np.concatenate([legit_pick, spam_pick]).astype(np.int64)
    sampled.sort()
    return sampled, class_counts(y[sampled]), warnings


def maybe_pad_with_smote(
    X: np.ndarray, y: np.ndarray, target_per_class: Dict[int, int], seed: int,
) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Pad up to target counts using SMOTE. Returns padded X, y, and info dict."""
    info = {'before': class_counts(y), 'enabled': True}
    try:
        from imblearn.over_sampling import SMOTE
    except ImportError:
        info.update({'enabled': False, 'reason': 'imblearn not installed'})
        return X, y, info
    counts = np.bincount(y, minlength=NUM_CLASSES)
    sampling_strategy = {
        cls: max(int(counts[cls]), int(target_per_class.get(cls, 0)))
        for cls in range(NUM_CLASSES)
        if counts[cls] > 1
    }
    if all(v <= counts[k] for k, v in sampling_strategy.items()):
        info['after'] = info['before']
        info['noop'] = True
        return X, y, info
    min_class = min(int(counts[c]) for c in sampling_strategy if counts[c] > 1)
    k_neighbors = max(1, min(5, min_class - 1))
    try:
        sm = SMOTE(sampling_strategy=sampling_strategy, k_neighbors=k_neighbors, random_state=seed)
        X_res, y_res = sm.fit_resample(X, y)
    except Exception as e:
        info.update({'enabled': False, 'reason': f'SMOTE failed: {e}'})
        return X, y, info
    info['after'] = class_counts(y_res)
    return X_res.astype(np.float32), y_res.astype(np.int64), info


# ---------------------------------------------------------------------------
# CatBoost teacher
# ---------------------------------------------------------------------------

def train_catboost_teacher(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    seed: int,
    iterations: int = 500,
    depth: int = 6,
    learning_rate: float = 0.05,
):
    from catboost import CatBoostClassifier
    teacher = CatBoostClassifier(
        loss_function='MultiClass',
        iterations=iterations,
        depth=depth,
        learning_rate=learning_rate,
        auto_class_weights='Balanced',
        random_seed=seed,
        verbose=False,
        eval_metric='TotalF1',
        early_stopping_rounds=30,
    )
    teacher.fit(X_train, y_train, eval_set=(X_val, y_val), use_best_model=True, verbose=False)
    return teacher


def teacher_soft_targets(teacher, X: np.ndarray, T: float) -> np.ndarray:
    """Get teacher soft targets at temperature T.

    p_T = softmax(log(p) / T). For T=1 returns original probabilities.
    """
    proba = teacher.predict_proba(X).astype(np.float64)
    proba = np.clip(proba, 1e-9, 1.0)
    logits = np.log(proba)
    scaled = logits / max(T, 1e-6)
    # numerical-stable softmax
    scaled = scaled - scaled.max(axis=1, keepdims=True)
    e = np.exp(scaled)
    return (e / e.sum(axis=1, keepdims=True)).astype(np.float32)


# ---------------------------------------------------------------------------
# Keras student (subclass with KD train_step)
# ---------------------------------------------------------------------------

def build_student_model(hidden_sizes: Tuple[int, ...], dropout: float, T: float, alpha: float, lr: float):
    """Construct KD-Keras model (training mode produces logits + KL/CE loss).

    Architecture:
        Input(32) -> Linear(h0) -> ReLU -> Dropout
                  -> Linear(h1) -> ReLU -> Dropout
                  -> Linear(h2) -> ReLU
                  -> Linear(3 logits)

    No BatchNorm: avoids fold-time errors during TFLite export and is unnecessary
    at this scale.
    """
    import tensorflow as tf

    inputs = tf.keras.Input(shape=(len(COMPACT_FEATURES),), name='features')
    h = inputs
    for i, units in enumerate(hidden_sizes[:-1]):
        h = tf.keras.layers.Dense(units, activation='relu', name=f'dense_{i}')(h)
        h = tf.keras.layers.Dropout(dropout, name=f'drop_{i}')(h)
    h = tf.keras.layers.Dense(hidden_sizes[-1], activation='relu', name=f'dense_{len(hidden_sizes) - 1}')(h)
    logits = tf.keras.layers.Dense(NUM_CLASSES, activation=None, name='logits')(h)
    backbone = tf.keras.Model(inputs, logits, name='student_backbone')

    class KDModel(tf.keras.Model):
        def __init__(self, backbone, T, alpha):
            super().__init__()
            self.backbone = backbone
            self.T = float(T)
            self.alpha = float(alpha)
            self.ce_metric = tf.keras.metrics.Mean(name='ce')
            self.kd_metric = tf.keras.metrics.Mean(name='kd')
            self.acc_metric = tf.keras.metrics.SparseCategoricalAccuracy(name='acc')

        def call(self, x, training=False):
            return self.backbone(x, training=training)

        def train_step(self, data):
            (x, y_hard), soft = data
            with tf.GradientTape() as tape:
                student_logits = self.backbone(x, training=True)
                # Hard CE
                ce = tf.keras.losses.sparse_categorical_crossentropy(
                    y_hard, student_logits, from_logits=True,
                )
                ce = tf.reduce_mean(ce)
                # KD: KL(student/T || teacher_soft@T)
                T = self.T
                student_log_soft = tf.nn.log_softmax(student_logits / T, axis=-1)
                # KL(P || Q) = sum P (log P - log Q); here P=teacher_soft, Q=student
                teacher_soft = tf.cast(soft, tf.float32)
                eps = 1e-9
                teacher_log = tf.math.log(teacher_soft + eps)
                kl = tf.reduce_sum(teacher_soft * (teacher_log - student_log_soft), axis=-1)
                kl = tf.reduce_mean(kl)
                loss = self.alpha * ce + (1.0 - self.alpha) * (T * T) * kl
            grads = tape.gradient(loss, self.trainable_variables)
            self.optimizer.apply_gradients(zip(grads, self.trainable_variables))
            self.ce_metric.update_state(ce)
            self.kd_metric.update_state(kl)
            self.acc_metric.update_state(y_hard, student_logits)
            return {
                'loss': loss,
                'ce': self.ce_metric.result(),
                'kd': self.kd_metric.result(),
                'acc': self.acc_metric.result(),
            }

        def test_step(self, data):
            x, y_hard = data
            logits = self.backbone(x, training=False)
            ce = tf.reduce_mean(tf.keras.losses.sparse_categorical_crossentropy(
                y_hard, logits, from_logits=True,
            ))
            self.acc_metric.update_state(y_hard, logits)
            return {'loss': ce, 'acc': self.acc_metric.result()}

    model = KDModel(backbone, T=T, alpha=alpha)
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=lr))
    return model, backbone


def train_student(
    X_train: np.ndarray, y_train: np.ndarray, soft_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    *, T: float, alpha: float, hidden_sizes: Tuple[int, ...], dropout: float,
    lr: float, epochs: int, batch_size: int, patience: int, seed: int, verbose: int = 0,
):
    """Train one student with given hyperparams. Returns (backbone, history, best_val_acc)."""
    import tensorflow as tf
    set_global_seed(seed)
    model, backbone = build_student_model(hidden_sizes, dropout, T, alpha, lr)

    train_ds = tf.data.Dataset.from_tensor_slices(
        ((X_train.astype(np.float32), y_train.astype(np.int32)), soft_train.astype(np.float32))
    ).shuffle(buffer_size=min(len(X_train), 8192), seed=seed).batch(batch_size)
    val_ds = tf.data.Dataset.from_tensor_slices(
        (X_val.astype(np.float32), y_val.astype(np.int32))
    ).batch(batch_size)

    es = tf.keras.callbacks.EarlyStopping(
        monitor='val_acc', mode='max', patience=patience, restore_best_weights=True,
    )
    history = model.fit(
        train_ds, validation_data=val_ds, epochs=epochs, callbacks=[es], verbose=verbose,
    )
    best_val_acc = float(max(history.history.get('val_acc', [0.0])))
    return backbone, history.history, best_val_acc


# ---------------------------------------------------------------------------
# Metrics + threshold tuning
# ---------------------------------------------------------------------------

def proba_from_backbone(backbone, X: np.ndarray) -> np.ndarray:
    import tensorflow as tf
    logits = backbone.predict(X.astype(np.float32), verbose=0)
    e = np.exp(logits - logits.max(axis=1, keepdims=True))
    return (e / e.sum(axis=1, keepdims=True)).astype(np.float32)


def per_class_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
    from sklearn.metrics import precision_recall_fscore_support, confusion_matrix
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=[0, 1, 2], zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2]).tolist()
    out = {
        ID_TO_LABEL[i]: {'precision': float(p[i]), 'recall': float(r[i]), 'f1': float(f[i])}
        for i in range(NUM_CLASSES)
    }
    out['macro_f1'] = float(np.mean(f))
    out['confusion_matrix'] = cm
    return out


def evaluate_proba(y_true: np.ndarray, proba: np.ndarray, thresholds: Optional[Dict] = None) -> Dict:
    if thresholds:
        bt = float(thresholds.get('block_threshold', 0.5))
        wt = float(thresholds.get('warn_threshold', 0.3))
        pred = np.zeros(len(y_true), dtype=np.int64)
        block_mask = proba[:, 2] >= bt
        warn_mask = (~block_mask) & (proba[:, 1] >= wt)
        pred[block_mask] = 2
        pred[warn_mask] = 1
        # else stays ALLOW=0
    else:
        pred = np.argmax(proba, axis=1)
    metrics = per_class_metrics(y_true, pred)
    try:
        from sklearn.metrics import roc_auc_score
        metrics['roc_auc_ovr'] = float(roc_auc_score(y_true, proba, multi_class='ovr', labels=[0, 1, 2]))
    except Exception:
        metrics['roc_auc_ovr'] = None
    return metrics


def tune_thresholds(y_true: np.ndarray, proba: np.ndarray, min_block_precision: float) -> Dict:
    """Find block_threshold maximizing BLOCK F1 subject to BLOCK precision >= floor.

    Then find warn_threshold maximizing WARN F1 with the picked block threshold.
    """
    best = {
        'block_threshold': 0.50,
        'warn_threshold': 0.30,
        'block_precision': 0.0,
        'block_recall': 0.0,
        'block_f1': 0.0,
    }
    for bt in np.linspace(0.10, 0.95, 86):
        pred_block = proba[:, 2] >= bt
        tp = int(np.sum(pred_block & (y_true == 2)))
        fp = int(np.sum(pred_block & (y_true != 2)))
        fn = int(np.sum(~pred_block & (y_true == 2)))
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        if prec >= min_block_precision and f1 > best['block_f1']:
            best.update({
                'block_threshold': float(bt),
                'block_precision': float(prec),
                'block_recall': float(rec),
                'block_f1': float(f1),
            })

    bt = best['block_threshold']
    best_warn = {'warn_threshold': 0.30, 'warn_f1': 0.0}
    for wt in np.linspace(0.10, 0.85, 76):
        block_mask = proba[:, 2] >= bt
        warn_mask = (~block_mask) & (proba[:, 1] >= wt)
        tp = int(np.sum(warn_mask & (y_true == 1)))
        fp = int(np.sum(warn_mask & (y_true != 1)))
        fn = int(np.sum(~warn_mask & (y_true == 1)))
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        if f1 > best_warn['warn_f1']:
            best_warn = {'warn_threshold': float(wt), 'warn_f1': float(f1)}
    best['warn_threshold'] = best_warn['warn_threshold']
    best['warn_f1'] = best_warn['warn_f1']
    return best


# ---------------------------------------------------------------------------
# Hyperparameter search
# ---------------------------------------------------------------------------

def kd_objective_score(metrics: Dict, min_block_precision: float) -> float:
    """Macro F1 with soft penalty on BLOCK precision below floor."""
    macro = metrics.get('macro_f1', 0.0)
    block_p = metrics.get('BLOCK', {}).get('precision', 0.0)
    penalty = 0.3 * max(0.0, min_block_precision - block_p)
    return macro - penalty


def stage1_grid_search(
    teacher, X_st: np.ndarray, y_st: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    *, hidden_sizes: Tuple[int, ...], dropout: float, lr: float,
    epochs: int, batch_size: int, patience: int, seed: int,
    Ts: List[float], alphas: List[float], min_block_precision: float, verbose: int = 0,
) -> Dict:
    """Grid search over (T, alpha). Returns best config + all results."""
    results = []
    best_score = -1e9
    best_cfg = None
    print(f'  [stage1] grid: T={Ts} × alpha={alphas} = {len(Ts) * len(alphas)} runs')
    for T in Ts:
        soft = teacher_soft_targets(teacher, X_st, T)
        for alpha in alphas:
            t0 = time.time()
            backbone, _, val_acc = train_student(
                X_st, y_st, soft, X_val, y_val,
                T=T, alpha=alpha, hidden_sizes=hidden_sizes, dropout=dropout,
                lr=lr, epochs=epochs, batch_size=batch_size, patience=patience,
                seed=seed, verbose=verbose,
            )
            proba_val = proba_from_backbone(backbone, X_val)
            metrics = evaluate_proba(y_val, proba_val)
            score = kd_objective_score(metrics, min_block_precision)
            elapsed = time.time() - t0
            print(
                f'    T={T:>4.2f} alpha={alpha:>4.2f} | macroF1={metrics["macro_f1"]:.4f} '
                f'BLOCK_P={metrics["BLOCK"]["precision"]:.3f} score={score:.4f} ({elapsed:.1f}s)'
            )
            results.append({
                'T': float(T), 'alpha': float(alpha), 'val_acc': val_acc,
                'metrics': metrics, 'score': score, 'elapsed_s': elapsed,
            })
            if score > best_score:
                best_score = score
                best_cfg = {'T': float(T), 'alpha': float(alpha), 'score': score, 'metrics': metrics}
    return {'all': results, 'best': best_cfg}


def stage2_optuna_search(
    teacher, X_st: np.ndarray, y_st: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    *, T: float, alpha: float,
    n_trials: int, epochs: int, batch_size: int, patience: int, seed: int,
    min_block_precision: float, verbose: int = 0,
) -> Dict:
    """Optuna over (lr, dropout, hidden_sizes) at fixed T, alpha. Returns best config."""
    try:
        import optuna
        from optuna.pruners import MedianPruner
    except ImportError:
        return {'skipped': 'optuna not installed'}

    print(f'  [stage2] optuna: {n_trials} trials at T={T} alpha={alpha}')
    soft = teacher_soft_targets(teacher, X_st, T)
    trials_log = []

    def objective(trial: 'optuna.Trial') -> float:
        lr = trial.suggest_float('lr', 1e-4, 5e-3, log=True)
        dropout = trial.suggest_float('dropout', 0.05, 0.4)
        h0 = trial.suggest_categorical('h0', [48, 64, 96])
        h1 = trial.suggest_categorical('h1', [32, 48, 64])
        h2 = trial.suggest_categorical('h2', [16, 24, 32])
        hidden_sizes = (h0, h1, h2)
        backbone, _, val_acc = train_student(
            X_st, y_st, soft, X_val, y_val,
            T=T, alpha=alpha, hidden_sizes=hidden_sizes, dropout=dropout,
            lr=lr, epochs=epochs, batch_size=batch_size, patience=patience,
            seed=seed, verbose=verbose,
        )
        proba_val = proba_from_backbone(backbone, X_val)
        metrics = evaluate_proba(y_val, proba_val)
        score = kd_objective_score(metrics, min_block_precision)
        trials_log.append({
            'params': {'lr': lr, 'dropout': dropout, 'h0': h0, 'h1': h1, 'h2': h2},
            'val_acc': val_acc, 'macro_f1': metrics['macro_f1'],
            'block_precision': metrics['BLOCK']['precision'], 'score': score,
        })
        return score

    sampler = optuna.samplers.TPESampler(seed=seed)
    pruner = MedianPruner(n_startup_trials=5, n_warmup_steps=0)
    study = optuna.create_study(direction='maximize', sampler=sampler, pruner=pruner)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return {
        'best_params': study.best_params,
        'best_value': float(study.best_value),
        'trials': trials_log,
    }


# ---------------------------------------------------------------------------
# Plain MLP baseline (no KD) for comparison
# ---------------------------------------------------------------------------

def train_plain_mlp(
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    *, hidden_sizes: Tuple[int, ...], dropout: float, lr: float,
    epochs: int, batch_size: int, patience: int, seed: int, verbose: int = 0,
):
    import tensorflow as tf
    set_global_seed(seed)
    inputs = tf.keras.Input(shape=(len(COMPACT_FEATURES),), name='features')
    h = inputs
    for i, units in enumerate(hidden_sizes[:-1]):
        h = tf.keras.layers.Dense(units, activation='relu', name=f'dense_{i}')(h)
        h = tf.keras.layers.Dropout(dropout, name=f'drop_{i}')(h)
    h = tf.keras.layers.Dense(hidden_sizes[-1], activation='relu', name=f'dense_{len(hidden_sizes) - 1}')(h)
    logits = tf.keras.layers.Dense(NUM_CLASSES, activation=None, name='logits')(h)
    model = tf.keras.Model(inputs, logits)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
        metrics=[tf.keras.metrics.SparseCategoricalAccuracy(name='acc')],
    )
    es = tf.keras.callbacks.EarlyStopping(
        monitor='val_acc', mode='max', patience=patience, restore_best_weights=True,
    )
    model.fit(
        X_train.astype(np.float32), y_train.astype(np.int32),
        validation_data=(X_val.astype(np.float32), y_val.astype(np.int32)),
        epochs=epochs, batch_size=batch_size, callbacks=[es], verbose=verbose,
    )
    return model


# ---------------------------------------------------------------------------
# Export to TFLite + sanity check
# ---------------------------------------------------------------------------

def build_export_model(backbone) -> 'tf.keras.Model':
    """Wrap backbone with Softmax so Android receives probabilities directly."""
    import tensorflow as tf
    inputs = tf.keras.Input(shape=(len(COMPACT_FEATURES),), name='features')
    logits = backbone(inputs, training=False)
    probs = tf.keras.layers.Softmax(name='probabilities')(logits)
    return tf.keras.Model(inputs, probs, name='spam_model_export')


def _make_serving_fn(backbone):
    """tf.function with fixed [1, N] input signature returning softmax probs.

    Avoids the TFLiteConverter.from_keras_model bug under TF 2.16+/Keras 3
    ('NoneType is not callable' from tflite_keras_util._wrapped_model).
    """
    import tensorflow as tf
    n_features = len(COMPACT_FEATURES)

    @tf.function(input_signature=[tf.TensorSpec([1, n_features], tf.float32, name='features')])
    def serving_fn(x):
        logits = backbone(x, training=False)
        return tf.nn.softmax(logits, axis=-1)

    return serving_fn


def export_tflite(backbone, out_path: str, *, quantize: bool = False) -> Dict:
    """Export backbone to a TFLite file with [1, N] input and [1, 3] softmax output.

    Tries three converter paths in order — first that succeeds wins:
      1. from_concrete_functions(serving_fn) — most stable on Keras 3.
      2. from_keras_model(export_model)      — classic path.
      3. from_saved_model(SavedModel dir)    — last resort.

    By default produces a pure FP32 model (no optimizations). Pass quantize=True
    to enable dynamic-range quantization (weights -> int8, compute in float),
    which reduces .tflite size ~4x but introduces ~1e-3 numerical drift and
    will fail the FP32 sanity check.
    """
    import tensorflow as tf
    import tempfile

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    export_model = build_export_model(backbone)

    def apply_opts(conv):
        if quantize:
            conv.optimizations = [tf.lite.Optimize.DEFAULT]
        return conv

    errors: List[str] = []
    tflite_bytes: Optional[bytes] = None

    # Path 1: concrete-function signature
    try:
        serving_fn = _make_serving_fn(backbone)
        concrete = serving_fn.get_concrete_function()
        converter = apply_opts(tf.lite.TFLiteConverter.from_concrete_functions([concrete]))
        tflite_bytes = converter.convert()
    except Exception as e:
        errors.append(f'from_concrete_functions: {type(e).__name__}: {e}')

    # Path 2: keras model directly
    if tflite_bytes is None:
        try:
            converter = apply_opts(tf.lite.TFLiteConverter.from_keras_model(export_model))
            tflite_bytes = converter.convert()
        except Exception as e:
            errors.append(f'from_keras_model: {type(e).__name__}: {e}')

    # Path 3: SavedModel dir round-trip
    if tflite_bytes is None:
        try:
            with tempfile.TemporaryDirectory(prefix='kd_savedmodel_') as tmpdir:
                serving_fn = _make_serving_fn(backbone)
                tf.saved_model.save(
                    backbone, tmpdir,
                    signatures={'serving_default': serving_fn.get_concrete_function()},
                )
                converter = apply_opts(tf.lite.TFLiteConverter.from_saved_model(tmpdir))
                tflite_bytes = converter.convert()
        except Exception as e:
            errors.append(f'from_saved_model: {type(e).__name__}: {e}')

    if tflite_bytes is None:
        raise SystemExit('TFLite export failed via all paths:\n  - ' + '\n  - '.join(errors))

    with open(out_path, 'wb') as f:
        f.write(tflite_bytes)
    print(f'  TFLite converter path used: {"concrete_functions" if not errors else ("keras_model" if len(errors) == 1 else "saved_model")}')
    return {'path': out_path, 'bytes': len(tflite_bytes), 'export_model': export_model}


def tflite_predict(tflite_path: str, X: np.ndarray) -> np.ndarray:
    import tensorflow as tf
    interp = tf.lite.Interpreter(model_path=tflite_path)
    interp.allocate_tensors()
    in_d = interp.get_input_details()[0]
    out_d = interp.get_output_details()[0]
    out = np.zeros((len(X), NUM_CLASSES), dtype=np.float32)
    for i, row in enumerate(X.astype(np.float32)):
        interp.set_tensor(in_d['index'], row.reshape(1, -1))
        interp.invoke()
        out[i] = interp.get_tensor(out_d['index']).reshape(-1)
    return out


def sanity_check_export(export_model, tflite_path: str, X: np.ndarray, atol: float = 1e-4) -> Dict:
    import tensorflow as tf
    n = min(200, len(X))
    sample = X[:n].astype(np.float32)
    keras_p = export_model.predict(sample, verbose=0)
    tflite_p = tflite_predict(tflite_path, sample)
    diff = float(np.max(np.abs(keras_p - tflite_p)))
    return {
        'samples': n,
        'max_abs_diff': diff,
        'pass': bool(diff < atol),
        'atol': atol,
    }


# ---------------------------------------------------------------------------
# Backup + reports
# ---------------------------------------------------------------------------

def backup_existing_assets(run_dir: str, paths: List[str]) -> List[str]:
    backup_dir = os.path.join(run_dir, 'before')
    os.makedirs(backup_dir, exist_ok=True)
    saved = []
    for p in paths:
        if os.path.exists(p):
            dest = os.path.join(backup_dir, os.path.basename(p))
            shutil.copy2(p, dest)
            saved.append(dest)
    return saved


def write_kd_model_card(report: Dict, best_metrics: Dict, thresholds: Dict, out_path: str) -> None:
    card = {
        'version': f"kd-mlp-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        'created_at': report['created_at'],
        'feature_count': report['feature_count'],
        'features': report['features'],
        'rows': report['rows'],
        'class_counts': report['class_counts'],
        'dataset_hash': report['dataset_hash'],
        'best_model': 'kd_student',
        'block_precision': float(best_metrics.get('BLOCK', {}).get('precision', 0.0)),
        'block_recall': float(best_metrics.get('BLOCK', {}).get('recall', 0.0)),
        'roc_auc_ovr': best_metrics.get('roc_auc_ovr'),
        'thresholds': {
            'block_threshold': float(thresholds.get('block_threshold', 0.5)),
            'warn_threshold': float(thresholds.get('warn_threshold', 0.3)),
            'block_precision': float(thresholds.get('block_precision', 0.0)),
            'block_recall': float(thresholds.get('block_recall', 0.0)),
            'block_f1': float(thresholds.get('block_f1', 0.0)),
            'warn_f1': float(thresholds.get('warn_f1', 0.0)),
        },
        'smote_applied': report.get('smote_applied', False),
        'kd': {
            'T': float(report.get('kd', {}).get('T', 0.0)),
            'alpha': float(report.get('kd', {}).get('alpha', 0.0)),
            'teacher': 'catboost_multiclass',
            'teacher_train_per_class': report.get('teacher_train_per_class'),
            'student_train_per_class': report.get('student_train_per_class'),
        },
        'notes': 'Generated by scripts/train_kd_distillation.py',
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(card, f, ensure_ascii=False, indent=2)


def write_kd_report(report: Dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'kd_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    md_lines = [
        '# Knowledge Distillation report',
        '',
        f'- **Created**: {report["created_at"]}',
        f'- **Dataset**: {report["data"]} (sha256={report["dataset_hash"][:12]}…)',
        f'- **Rows**: {report["rows"]}',
        f'- **Class counts**: {report["class_counts"]}',
        f'- **Teacher train/class**: {report.get("teacher_train_per_class")}',
        f'- **Student train/class**: {report.get("student_train_per_class")}',
        f'- **Best T**: {report.get("kd", {}).get("T")}, α: {report.get("kd", {}).get("alpha")}',
        '',
        '## Comparison (test set)',
        '',
        '| Model | macro F1 | BLOCK P | BLOCK R | BLOCK F1 | WARN F1 | ROC-AUC OVR |',
        '|---|---|---|---|---|---|---|',
    ]
    for name, m in report.get('test_metrics', {}).items():
        md_lines.append(
            f'| {name} | {m.get("macro_f1", 0):.4f} '
            f'| {m.get("BLOCK", {}).get("precision", 0):.4f} '
            f'| {m.get("BLOCK", {}).get("recall", 0):.4f} '
            f'| {m.get("BLOCK", {}).get("f1", 0):.4f} '
            f'| {m.get("WARN", {}).get("f1", 0):.4f} '
            f'| {m.get("roc_auc_ovr") if m.get("roc_auc_ovr") is not None else "n/a"} |'
        )
    md_lines += [
        '',
        '## Export',
        f'- **TFLite path**: {report.get("tflite", {}).get("path")}',
        f'- **TFLite bytes**: {report.get("tflite", {}).get("bytes")}',
        f'- **Sanity max|p_keras - p_tflite|**: {report.get("sanity", {}).get("max_abs_diff")}',
        f'- **Sanity passed**: {report.get("sanity", {}).get("pass")}',
        '',
        '## Thresholds (val-tuned, written to model_card.json)',
        f'- block_threshold = {report.get("thresholds", {}).get("block_threshold")}',
        f'- warn_threshold  = {report.get("thresholds", {}).get("warn_threshold")}',
        '',
        '## Warnings',
    ]
    for w in report.get('warnings', []) or ['(none)']:
        md_lines.append(f'- {w}')
    with open(os.path.join(out_dir, 'kd_report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))

    html_rows = ''
    for name, m in report.get('test_metrics', {}).items():
        html_rows += (
            f'<tr><td>{name}</td>'
            f'<td>{m.get("macro_f1", 0):.4f}</td>'
            f'<td>{m.get("BLOCK", {}).get("precision", 0):.4f}</td>'
            f'<td>{m.get("BLOCK", {}).get("recall", 0):.4f}</td>'
            f'<td>{m.get("BLOCK", {}).get("f1", 0):.4f}</td>'
            f'<td>{m.get("WARN", {}).get("f1", 0):.4f}</td>'
            f'<td>{m.get("roc_auc_ovr") if m.get("roc_auc_ovr") is not None else "—"}</td></tr>'
        )
    with open(os.path.join(out_dir, 'kd_report.html'), 'w', encoding='utf-8') as f:
        f.write(
            '<!doctype html><html><head><meta charset="utf-8"><title>KD report</title>'
            '<style>body{font-family:system-ui;padding:24px;max-width:980px;margin:auto}'
            'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px 10px}'
            'th{background:#f3f3f3}</style></head><body>'
            f'<h1>Knowledge Distillation</h1>'
            f'<p><b>Created</b>: {report["created_at"]}</p>'
            f'<p><b>Dataset</b>: {report["data"]}</p>'
            f'<p><b>Rows</b>: {report["rows"]} | <b>Class counts</b>: {report["class_counts"]}</p>'
            f'<p><b>Best T</b>: {report.get("kd", {}).get("T")}, <b>α</b>: {report.get("kd", {}).get("alpha")}</p>'
            '<h2>Comparison (test set)</h2>'
            '<table><tr><th>Model</th><th>macro F1</th><th>BLOCK P</th><th>BLOCK R</th>'
            '<th>BLOCK F1</th><th>WARN F1</th><th>ROC-AUC OVR</th></tr>'
            f'{html_rows}</table>'
            f'<h2>Export</h2><p>TFLite: {report.get("tflite", {}).get("path")} '
            f'({report.get("tflite", {}).get("bytes")} bytes)</p>'
            f'<p>Sanity max|p_keras - p_tflite| = {report.get("sanity", {}).get("max_abs_diff")}'
            f' (pass={report.get("sanity", {}).get("pass")})</p>'
            '</body></html>'
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description='Knowledge Distillation: CatBoost → Keras MLP → TFLite')
    ap.add_argument('--data', default=DEFAULT_DATA)
    ap.add_argument('--tflite-output', default=DEFAULT_TFLITE)
    ap.add_argument('--model-card-output', default=DEFAULT_MODEL_CARD)
    ap.add_argument('--reports-dir', default=REPORTS_DIR)
    ap.add_argument('--seed', type=int, default=42)

    ap.add_argument('--teacher-train-per-class', type=int, default=6000,
                    help='Кол-во примеров на класс для teacher (CatBoost): 6k legit + 6k spam.')
    ap.add_argument('--student-train-per-class', type=int, default=4000,
                    help='Кол-во примеров на класс для student (KD-MLP): 4k legit + 4k spam (subset of teacher train).')
    ap.add_argument('--val-frac', type=float, default=0.10, help='Доля данных в val (стратифицированно).')
    ap.add_argument('--test-frac', type=float, default=0.10, help='Доля данных в test (стратифицированно).')
    ap.add_argument('--pad-with-smote', action='store_true',
                    help='Добивать teacher train SMOTE-ом до целевых цифр, если данных не хватает.')

    ap.add_argument('--teacher-iterations', type=int, default=500)
    ap.add_argument('--teacher-depth', type=int, default=6)
    ap.add_argument('--teacher-lr', type=float, default=0.05)

    ap.add_argument('--student-epochs', type=int, default=80)
    ap.add_argument('--student-batch', type=int, default=64)
    ap.add_argument('--student-patience', type=int, default=10)

    ap.add_argument('--T-grid', type=float, nargs='+', default=[2.0, 4.0, 8.0],
                    help='Сетка температур для stage1.')
    ap.add_argument('--alpha-grid', type=float, nargs='+', default=[0.3, 0.5, 0.7],
                    help='Сетка alpha для stage1.')
    ap.add_argument('--optuna-trials', type=int, default=20,
                    help='Кол-во Optuna trials в stage2 (lr/dropout/hidden). 0=пропустить.')

    ap.add_argument('--min-block-precision', type=float, default=0.85,
                    help='Минимально допустимая BLOCK precision при threshold tuning.')
    ap.add_argument('--allow-unsafe-export', action='store_true',
                    help='Экспортировать .tflite даже если sanity check проваливается.')
    ap.add_argument('--quantize', action='store_true',
                    help='Dynamic-range int8 quantization для весов (~4x меньше .tflite, ~1e-3 numerical drift). По умолчанию выключено: Android ждёт чистый FP32.')
    ap.add_argument('--sanity-atol', type=float, default=1e-4,
                    help='Допустимое расхождение между Keras FP32 и TFLite. Для quantize=True имеет смысл 5e-3.')
    ap.add_argument('--verbose', type=int, default=0, help='Keras verbose (0/1/2).')

    args = ap.parse_args()

    set_global_seed(args.seed)

    # --- Data ---
    print(f'Loading {args.data}...')
    X, y = load_csv(args.data)
    if X.shape[1] != len(COMPACT_FEATURES):
        raise SystemExit(f'Feature mismatch: {X.shape[1]} vs {len(COMPACT_FEATURES)}')
    counts = class_counts(y)
    print(f'  rows={len(y)}, class counts: {counts}')

    train_size = 1.0 - args.val_frac - args.test_frac
    if train_size <= 0:
        raise SystemExit('val_frac + test_frac must be < 1.0')
    train_idx, val_idx, test_idx = stratified_split(
        X, y, sizes=(train_size, args.val_frac, args.test_frac), seed=args.seed,
    )
    print(f'  split: train={len(train_idx)}, val={len(val_idx)}, test={len(test_idx)}')

    # --- Teacher train sampling ---
    teacher_idx, teacher_counts, warns_t = sample_teacher_train(
        train_idx, y,
        legit_target=args.teacher_train_per_class,
        spam_target=args.teacher_train_per_class,
        seed=args.seed,
    )
    print(f'  teacher train sample: {len(teacher_idx)} rows {teacher_counts}')
    for w in warns_t:
        print(f'    WARN: {w}')

    # --- Student train (subset of teacher train) ---
    student_idx, student_counts, warns_s = sample_student_train_subset(
        teacher_idx, y,
        legit_target=args.student_train_per_class,
        spam_target=args.student_train_per_class,
        seed=args.seed,
    )
    print(f'  student train sample: {len(student_idx)} rows {student_counts}')
    for w in warns_s:
        print(f'    WARN: {w}')

    X_teacher, y_teacher = X[teacher_idx], y[teacher_idx]
    X_student, y_student = X[student_idx], y[student_idx]
    X_val, y_val = X[val_idx], y[val_idx]
    X_test, y_test = X[test_idx], y[test_idx]

    smote_info: Dict = {}
    if args.pad_with_smote:
        target = {
            LABEL_TO_ID['ALLOW']: args.teacher_train_per_class,
            LABEL_TO_ID['WARN']: int(round(args.teacher_train_per_class * 0.22)),
            LABEL_TO_ID['BLOCK']: int(round(args.teacher_train_per_class * 0.78)),
        }
        X_teacher, y_teacher, smote_info = maybe_pad_with_smote(
            X_teacher, y_teacher, target, seed=args.seed,
        )
        print(f'  SMOTE: {smote_info}')

    # --- Teacher ---
    print('\n[1/5] Training CatBoost teacher...')
    t0 = time.time()
    teacher = train_catboost_teacher(
        X_teacher, y_teacher, X_val, y_val, seed=args.seed,
        iterations=args.teacher_iterations, depth=args.teacher_depth,
        learning_rate=args.teacher_lr,
    )
    print(f'  done in {time.time() - t0:.1f}s')
    teacher_proba_test = teacher.predict_proba(X_test)
    teacher_proba_val = teacher.predict_proba(X_val)
    teacher_metrics_test = evaluate_proba(y_test, teacher_proba_test)
    teacher_metrics_val = evaluate_proba(y_val, teacher_proba_val)
    print(f'  teacher val macroF1={teacher_metrics_val["macro_f1"]:.4f} '
          f'BLOCK_P={teacher_metrics_val["BLOCK"]["precision"]:.3f}')

    # --- Plain MLP baseline (no KD) ---
    print('\n[2/5] Training plain MLP baseline (no KD)...')
    t0 = time.time()
    plain = train_plain_mlp(
        X_student, y_student, X_val, y_val,
        hidden_sizes=(64, 48, 24), dropout=0.2, lr=1e-3,
        epochs=args.student_epochs, batch_size=args.student_batch,
        patience=args.student_patience, seed=args.seed, verbose=args.verbose,
    )
    print(f'  done in {time.time() - t0:.1f}s')

    def plain_proba(X):
        import tensorflow as tf
        logits = plain.predict(X.astype(np.float32), verbose=0)
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        return (e / e.sum(axis=1, keepdims=True)).astype(np.float32)

    plain_metrics_test = evaluate_proba(y_test, plain_proba(X_test))
    plain_metrics_val = evaluate_proba(y_val, plain_proba(X_val))
    print(f'  plain MLP val macroF1={plain_metrics_val["macro_f1"]:.4f} '
          f'BLOCK_P={plain_metrics_val["BLOCK"]["precision"]:.3f}')

    # --- Stage 1: grid (T, alpha) ---
    print('\n[3/5] KD stage1 grid search (T, alpha)...')
    t0 = time.time()
    stage1 = stage1_grid_search(
        teacher, X_student, y_student, X_val, y_val,
        hidden_sizes=(64, 48, 24), dropout=0.2, lr=1e-3,
        epochs=args.student_epochs, batch_size=args.student_batch,
        patience=args.student_patience, seed=args.seed,
        Ts=args.T_grid, alphas=args.alpha_grid,
        min_block_precision=args.min_block_precision, verbose=args.verbose,
    )
    best_T = stage1['best']['T']
    best_alpha = stage1['best']['alpha']
    print(f'  stage1 best T={best_T} α={best_alpha} in {time.time() - t0:.1f}s')

    # --- Stage 2: Optuna over lr/dropout/hidden ---
    stage2 = {}
    best_lr = 1e-3
    best_dropout = 0.2
    best_hidden = (64, 48, 24)
    if args.optuna_trials > 0:
        print('\n[4/5] KD stage2 Optuna (lr, dropout, hidden)...')
        t0 = time.time()
        stage2 = stage2_optuna_search(
            teacher, X_student, y_student, X_val, y_val,
            T=best_T, alpha=best_alpha,
            n_trials=args.optuna_trials,
            epochs=args.student_epochs, batch_size=args.student_batch,
            patience=args.student_patience, seed=args.seed,
            min_block_precision=args.min_block_precision, verbose=args.verbose,
        )
        bp = stage2.get('best_params', {})
        if bp:
            best_lr = float(bp['lr'])
            best_dropout = float(bp['dropout'])
            best_hidden = (int(bp['h0']), int(bp['h1']), int(bp['h2']))
        print(f'  stage2 done in {time.time() - t0:.1f}s, best_params={bp}')
    else:
        print('\n[4/5] Optuna stage2 disabled (--optuna-trials 0)')

    # --- Final student with best config ---
    print('\n[5/5] Training final student with best config...')
    soft_final = teacher_soft_targets(teacher, X_student, best_T)
    final_backbone, _, _ = train_student(
        X_student, y_student, soft_final, X_val, y_val,
        T=best_T, alpha=best_alpha, hidden_sizes=best_hidden, dropout=best_dropout,
        lr=best_lr, epochs=args.student_epochs, batch_size=args.student_batch,
        patience=args.student_patience, seed=args.seed, verbose=args.verbose,
    )
    proba_val = proba_from_backbone(final_backbone, X_val)
    proba_test = proba_from_backbone(final_backbone, X_test)
    student_metrics_test_argmax = evaluate_proba(y_test, proba_test)

    # --- Threshold tuning on val ---
    thresholds = tune_thresholds(y_val, proba_val, min_block_precision=args.min_block_precision)
    print(f'  thresholds: block={thresholds["block_threshold"]:.3f} '
          f'warn={thresholds["warn_threshold"]:.3f} '
          f'(BLOCK_P={thresholds["block_precision"]:.3f}, '
          f'BLOCK_F1={thresholds["block_f1"]:.3f})')
    student_metrics_test = evaluate_proba(y_test, proba_test, thresholds=thresholds)

    # --- Run dir + backup ---
    run_id = datetime.now().strftime('%Y%m%d-%H%M%S')
    run_dir = os.path.join(args.reports_dir, f'kd_{run_id}')
    os.makedirs(run_dir, exist_ok=True)
    backed = backup_existing_assets(run_dir, [args.tflite_output, args.model_card_output])
    if backed:
        print(f'  backed up old assets: {backed}')

    # --- Export TFLite ---
    print('\nExporting TFLite...')
    export_info = export_tflite(final_backbone, args.tflite_output, quantize=args.quantize)
    print(f'  wrote {export_info["bytes"]} bytes -> {export_info["path"]}')

    # --- Sanity check ---
    sanity = sanity_check_export(
        export_info['export_model'], args.tflite_output, X_test, atol=args.sanity_atol,
    )
    print(f'  sanity: max_abs_diff={sanity["max_abs_diff"]:.6f} pass={sanity["pass"]}')
    if not sanity['pass'] and not args.allow_unsafe_export:
        print('  !! sanity check FAILED — restoring backup and exiting non-zero')
        for src in backed:
            dst = os.path.join(ASSETS_DIR, os.path.basename(src))
            shutil.copy2(src, dst)
        return 2

    # --- TFLite test metrics ---
    tflite_proba_test = tflite_predict(args.tflite_output, X_test)
    tflite_metrics_test = evaluate_proba(y_test, tflite_proba_test, thresholds=thresholds)

    # --- Compose final report ---
    report = {
        'created_at': datetime.now().isoformat(),
        'data': args.data,
        'dataset_hash': file_sha256(args.data),
        'rows': int(len(y)),
        'feature_count': int(X.shape[1]),
        'features': COMPACT_FEATURES,
        'class_counts': counts,
        'split': {
            'train': int(len(train_idx)),
            'val': int(len(val_idx)),
            'test': int(len(test_idx)),
        },
        'teacher_train_per_class': args.teacher_train_per_class,
        'student_train_per_class': args.student_train_per_class,
        'teacher_counts_actual': teacher_counts,
        'student_counts_actual': student_counts,
        'smote_applied': bool(smote_info),
        'smote_info': smote_info,
        'kd': {'T': best_T, 'alpha': best_alpha,
               'lr': best_lr, 'dropout': best_dropout, 'hidden': list(best_hidden)},
        'stage1_grid': stage1,
        'stage2_optuna': stage2,
        'thresholds': thresholds,
        'val_metrics': {
            'catboost_teacher': teacher_metrics_val,
            'plain_mlp': plain_metrics_val,
            'kd_student_argmax': evaluate_proba(y_val, proba_val),
            'kd_student_thresholded': evaluate_proba(y_val, proba_val, thresholds=thresholds),
        },
        'test_metrics': {
            'catboost_teacher': teacher_metrics_test,
            'plain_mlp': plain_metrics_test,
            'kd_student_argmax': student_metrics_test_argmax,
            'kd_student_thresholded': student_metrics_test,
            'kd_student_tflite': tflite_metrics_test,
        },
        'tflite': {'path': args.tflite_output, 'bytes': export_info['bytes']},
        'sanity': sanity,
        'warnings': warns_t + warns_s + ([smote_info.get('reason')] if smote_info.get('reason') else []),
        'run_dir': run_dir,
    }

    write_kd_report(report, run_dir)
    write_kd_model_card(report, student_metrics_test, thresholds, args.model_card_output)
    print(f'\n[done] reports: {run_dir}')
    print(f'       tflite:  {args.tflite_output}')
    print(f'       card:    {args.model_card_output}')

    print('\n=== Test metrics summary ===')
    for name, m in report['test_metrics'].items():
        print(
            f'  {name:<28s} macroF1={m["macro_f1"]:.4f} '
            f'BLOCK P={m["BLOCK"]["precision"]:.3f} '
            f'R={m["BLOCK"]["recall"]:.3f} '
            f'F1={m["BLOCK"]["f1"]:.3f} '
            f'WARN F1={m["WARN"]["f1"]:.3f}'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())
