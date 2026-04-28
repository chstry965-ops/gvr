# Knowledge Distillation report

- **Created**: 2026-04-28T20:12:16.611771
- **Dataset**: C:\Users\Redmi\CascadeProjects\windsurf-project\scripts\..\datasets\ru\processed\ru_tflite_features.csv (sha256=bdca983e0563…)
- **Rows**: 20364
- **Class counts**: {'ALLOW': 10234, 'WARN': 2230, 'BLOCK': 7900}
- **Teacher train/class**: 6000
- **Student train/class**: 4000
- **Best T**: 8.0, α: 0.5

## Comparison (test set)

| Model | macro F1 | BLOCK P | BLOCK R | BLOCK F1 | WARN F1 | ROC-AUC OVR |
|---|---|---|---|---|---|---|
| catboost_teacher | 0.9778 | 0.9987 | 0.9709 | 0.9846 | 0.9487 | 0.9992027806695859 |
| plain_mlp | 0.9830 | 0.9949 | 0.9835 | 0.9892 | 0.9604 | 0.9990557153827101 |
| kd_student_argmax | 0.9756 | 0.9923 | 0.9759 | 0.9840 | 0.9432 | 0.9979045744255776 |
| kd_student_thresholded | 0.9766 | 0.9935 | 0.9747 | 0.9840 | 0.9458 | 0.9979045744255776 |
| kd_student_tflite | 0.9766 | 0.9935 | 0.9747 | 0.9840 | 0.9458 | 0.9979045744255776 |

## Export
- **TFLite path**: C:\Users\Redmi\CascadeProjects\windsurf-project\scripts\..\app\src\main\assets\spam_model.tflite
- **TFLite bytes**: 36900
- **Sanity max|p_keras - p_tflite|**: 5.364418029785156e-07
- **Sanity passed**: True

## Thresholds (val-tuned, written to model_card.json)
- block_threshold = 0.45000000000000007
- warn_threshold  = 0.1

## Warnings
- (none)