param(
    [int]$Trials = 3000,
    [int]$Jobs = 4,
    [string]$LogFile = "logs\tuner_overnight.log",
    [string[]]$TrainSeasons = @("2021-22", "2022-23"),
    [string]$TestSeason = "2023-24",
    [string]$StudyName = "rubies_rangers_moneyball"
)

# -------------------------------------------------------------------
# 1. Prevent Windows System Sleep (SetThreadExecutionState API)
# -------------------------------------------------------------------
$signature = @'
[DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$powerType = Add-Type -MemberDefinition $signature -Name "PowerKeeper" -Namespace "WinPower" -PassThru

# ES_CONTINUOUS (0x80000000) | ES_SYSTEM_REQUIRED (0x00000001) | ES_AWAYMODE_REQUIRED (0x00000040)
$ES_CONTINUOUS = 0x80000000
$ES_SYSTEM_REQUIRED = 0x00000001
$ES_AWAYMODE_REQUIRED = 0x00000040

$prevSleepState = [WinPower.PowerKeeper]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED)
Write-Host "[POWER] Windows system sleep prevention activated for overnight execution." -ForegroundColor Green

# Ensure logs folder exists
$logDir = [System.IO.Path]::GetDirectoryName($LogFile)
if (-not [string]::IsNullOrEmpty($logDir) -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

try {
    & {
        $startTime = Get-Date
        Write-Host "====================================================================" -ForegroundColor Cyan
        Write-Host "   Rubies Rangers -- Overnight Hyperparameter Auto-Tuner Run        " -ForegroundColor Cyan
        Write-Host "====================================================================" -ForegroundColor Cyan
        Write-Host "Start Time:     $startTime"
        Write-Host "Target Trials:  $Trials"
        Write-Host "Worker Cores:   $Jobs"
        Write-Host "Train Seasons:  $($TrainSeasons -join ', ')"
        Write-Host "Test Season:    $TestSeason (Strict Out-of-Sample)"
        Write-Host "Study Name:     $StudyName"
        Write-Host "Dashboard:      http://localhost:8502"
        Write-Host "Log Destination: $LogFile"
        Write-Host "--------------------------------------------------------------------" -ForegroundColor Gray

        # -------------------------------------------------------------------
        # 2. Pre-fetch and cache historical datasets
        # -------------------------------------------------------------------
        Write-Host "`n[STEP 1/3] Verifying and pre-caching historical datasets..." -ForegroundColor Yellow
        python -m tuner.cli fetch-data

        # -------------------------------------------------------------------
        # 3. Execute Optuna Hyperparameter Optimization Run
        # -------------------------------------------------------------------
        Write-Host "`n[STEP 2/3] Starting Optuna TPESampler Optimization ($Trials trials, $Jobs workers)..." -ForegroundColor Yellow
        $trainArgs = $TrainSeasons -join " "
        $runCmd = "python -m tuner.cli run --trials $Trials --n-jobs $Jobs --train-seasons $trainArgs --test-season $TestSeason --study-name $StudyName"
        Invoke-Expression $runCmd

        # -------------------------------------------------------------------
        # 4. Post-Optimization Baseline Audit & Comparison
        # -------------------------------------------------------------------
        Write-Host "`n[STEP 3/3] Running post-optimization performance audits..." -ForegroundColor Yellow
        Write-Host "`n--- A. Heuristic Baseline Profile Evaluation ($TestSeason) ---" -ForegroundColor Cyan
        python -m tuner.cli evaluate --profile heuristic --season $TestSeason

        Write-Host "`n--- B. Tuned Winning Profile Evaluation ($TestSeason) ---" -ForegroundColor Green
        python -m tuner.cli evaluate --profile tuned --season $TestSeason

        $endTime = Get-Date
        $duration = $endTime - $startTime
        Write-Host "`n====================================================================" -ForegroundColor Green
        Write-Host "   Overnight Tuning Run Finished Successfully!                      " -ForegroundColor Green
        Write-Host "====================================================================" -ForegroundColor Green
        Write-Host "Total Elapsed Time: $($duration.Hours)h $($duration.Minutes)m $($duration.Seconds)s"
        Write-Host "Config Updated:     config.yaml ('tuned:' section)"
        Write-Host "Audit Log Saved:    $LogFile"
        Write-Host "Dashboard Active:   http://localhost:8502"
    } 2>&1 | Tee-Object -FilePath $LogFile
}
finally {
    # Restore normal Windows sleep behavior
    [WinPower.PowerKeeper]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    Write-Host "[POWER] Restored normal Windows sleep state." -ForegroundColor Gray
}
