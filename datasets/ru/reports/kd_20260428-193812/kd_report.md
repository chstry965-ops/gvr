# Knowledge Distillation report

- **Created**: 2026-04-28T19:38:12.822418
- **Dataset**: C:\Users\Redmi\CascadeProjects\windsurf-project\scripts\..\datasets\ru\processed\ru_tflite_features.csv (sha256=3e915b8155b1…)
- **Rows**: 20364
- **Class counts**: {'ALLOW': 10234, 'WARN': 2230, 'BLOCK': 7900}
- **Teacher train/class**: 6000
- **Student train/class**: 4000
- **Best T**: 4.0, α: 0.5

## Comparison (test set)

| Model | macro F1 | BLOCK P | BLOCK R | BLOCK F1 | WARN F1 | ROC-AUC OVR |
|---|---|---|---|---|---|---|
| catboost_teacher | 0.9777 | 0.9974 | 0.9734 | 0.9853 | 0.9483 | 0.9987961219012288 |
| plain_mlp | 0.9322 | 0.9877 | 0.9152 | 0.9501 | 0.8469 | 0.9937947556758822 |
| kd_student_argmax | 0.9794 | 0.9961 | 0.9772 | 0.9866 | 0.9522 | 0.9973621278470196 |
| kd_student_thresholded | 0.9813 | 0.9961 | 0.9785 | 0.9872 | 0.9565 | 0.9973621278470196 |
| kd_student_tflite | 0.9813 | 0.9961 | 0.9785 | 0.9872 | 0.9565 | 0.9973621278470196 |

## Export
- **TFLite path**: C:\Users\Redmi\CascadeProjects\windsurf-project\scripts\..\app\src\main\assets\spam_model.tflite
- **TFLite bytes**: 48484
- **Sanity max|p_keras - p_tflite|**: 1.7881393432617188e-07
- **Sanity passed**: True

## Thresholds (val-tuned, written to model_card.json)
- block_threshold = 0.43000000000000005
- warn_threshold  = 0.1

## Warnings
- (none)