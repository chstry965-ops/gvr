param(
    [Parameter(Position=0)]
    [ValidateSet('doctor','status','build-dataset','train','kd-train','export','drift','quality','validate','android-build','collect')]
    [string]$Command = 'doctor',

    [int]$SmokeSynthetic = 0,
    [switch]$ExportTflite,
    [switch]$AllowUnsafeExport,
    [double]$MinBlockPrecision = 0.90,
    [switch]$NoSmote,
    [int]$OptunaTrials = 0,
    [string]$DriftReference = '',
    [switch]$Plots,
    [int]$TeacherTrainPerClass = 6000,
    [int]$StudentTrainPerClass = 4000,
    [switch]$PadWithSmote,
    [int]$Seed = 42
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\Redmi\AppData\Local\Programs\Python\Python312\python.exe'
if (!(Test-Path $Python)) { $Python = 'python' }

$argsList = @('tools/spam_cli.py', $Command)
if ($Command -eq 'build-dataset' -and $SmokeSynthetic -gt 0) {
    $argsList += @('--smoke-synthetic', $SmokeSynthetic)
}
if ($Command -in @('train','export')) {
    if ($ExportTflite -or $Command -eq 'export') { $argsList += '--export-tflite' }
    if ($AllowUnsafeExport) { $argsList += '--allow-unsafe-export' }
    $argsList += @('--min-block-precision', $MinBlockPrecision)
    if ($NoSmote) { $argsList += '--no-smote' }
    if ($OptunaTrials -gt 0) { $argsList += @('--optuna-trials', $OptunaTrials) }
    if ($DriftReference) { $argsList += @('--drift-reference', $DriftReference) }
    if ($Plots) { $argsList += '--plots' }
}
if ($Command -eq 'drift') {
    if ($DriftReference) { $argsList += @('--reference', $DriftReference) }
    if ($Plots) { $argsList += '--plots' }
}
if ($Command -eq 'kd-train') {
    $argsList += @('--teacher-train-per-class', $TeacherTrainPerClass)
    $argsList += @('--student-train-per-class', $StudentTrainPerClass)
    if ($PSBoundParameters.ContainsKey('OptunaTrials')) { $argsList += @('--optuna-trials', $OptunaTrials) }
    if ($PSBoundParameters.ContainsKey('MinBlockPrecision')) { $argsList += @('--min-block-precision', $MinBlockPrecision) }
    if ($PadWithSmote) { $argsList += '--pad-with-smote' }
    if ($AllowUnsafeExport) { $argsList += '--allow-unsafe-export' }
    $argsList += @('--seed', $Seed)
}

& $Python @argsList
exit $LASTEXITCODE
