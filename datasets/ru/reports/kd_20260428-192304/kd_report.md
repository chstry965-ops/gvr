# Knowledge Distillation report

- **Created**: 2026-04-28T19:23:04.944298
- **Dataset**: C:\Users\Redmi\CascadeProjects\windsurf-project\scripts\..\datasets\ru\processed\ru_tflite_features.csv (sha256=5ace4b937fed…)
- **Rows**: 20364
- **Class counts**: {'ALLOW': 10234, 'WARN': 2230, 'BLOCK': 7900}
- **Teacher train/class**: 6000
- **Student train/class**: 4000
- **Best T**: 2.0, α: 0.3

## Comparison (test set)

| Model | macro F1 | BLOCK P | BLOCK R | BLOCK F1 | WARN F1 | ROC-AUC OVR |
|---|---|---|---|---|---|---|
| catboost_teacher | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0 |
| plain_mlp | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0 |
| kd_student_argmax | 0.9991 | 1.0000 | 1.0000 | 1.0000 | 0.9978 | 1.0 |
| kd_student_thresholded | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0 |
| kd_student_tflite | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0 |

## Export
- **TFLite path**: C:\Users\Redmi\CascadeProjects\windsurf-project\scripts\..\app\src\main\assets\spam_model.tflite
- **TFLite bytes**: 27684
- **Sanity max|p_keras - p_tflite|**: 1.1920928955078125e-07
- **Sanity passed**: True

## Thresholds (val-tuned, written to model_card.json)
- block_threshold = 0.33
- warn_threshold  = 0.27

## Warnings
- (none)