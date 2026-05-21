# init_pipeline.ps1 — Run this from E:\4DGS_Project
# Usage: cd E:\4DGS_Project; .\init_pipeline.ps1 -Dataset coffee_martini
param(
    [string]$Dataset = "coffee_martini",
    [string]$Port = "7860"
)

Set-Location $PSScriptRoot 2>$null  # fallback: run from project root

# ── 1. Detect what's already done ──────────────────────────────────────────
$isDyNeRF = $Dataset -in @("coffee_martini","cook_spinach","cut_roasted_beef","flame_salmon_1","flame_steak","sear_steak")
$prefix   = if ($isDyNeRF) { "dynerf" } else { "dnerf" }

$colmapDone   = (Test-Path "colmap_coffee\dense\fused.ply") -or
                (Test-Path "4DGS_TrainData\$Dataset\points3D_downsample2.ply")
$trainDone    = Test-Path "output\$prefix\$Dataset\point_cloud"
$exportDone   = (Get-ChildItem "output\$prefix\$Dataset\gaussian_pertimestamp\point_cloud_*.ply" -ErrorAction SilentlyContinue).Count -gt 0
$compressDone = Test-Path "GSplatTest\Assets\DynGsplatData\$Dataset\$Dataset.dgs"

function Status([bool]$done) { if ($done) { "done" } else { "pending" } }

Write-Host ""
Write-Host "=== Pipeline status for: $Dataset ===" -ForegroundColor Cyan
Write-Host "  COLMAP:     $(Status $colmapDone)"
Write-Host "  Training:   $(Status $trainDone)"
Write-Host "  PLY export: $(Status $exportDone)"
Write-Host "  Compress:   $(Status $compressDone)"

# ── 2. Build state.json ─────────────────────────────────────────────────────
$expectedPly    = if ($isDyNeRF) { 300 } else { 20 }
$expectedBlocks = if ($isDyNeRF) { 15 }  else { 1 }
$totalIters     = if ($isDyNeRF) { 17000 } else { 23000 }

$steps = @(
    @{ id="env";        label="Environment Setup";      status="done" }
)
if ($isDyNeRF) {
    $steps += @{ id="colmap"; label="COLMAP Point Cloud"; status=(Status $colmapDone) }
}
$steps += @(
    @{ id="train";      label="4DGS Training";           status=(Status $trainDone);
       log="logs/train.log"; total_iters=$totalIters }
    @{ id="export_ply"; label="Export Per-Frame PLY";    status=(Status $exportDone);
       output_dir="output/$prefix/$Dataset/gaussian_pertimestamp";
       expected_files=$expectedPly }
    @{ id="compress";   label="Compress to .dgs";        status=(Status $compressDone);
       output_dir="GSplatTest/Assets/DynGsplatData/$Dataset/Data";
       expected_files=$expectedBlocks; log="logs/compress.log" }
    @{ id="unity";      label="Unity Import & Playback"; status="pending" }
)

$state = @{
    project    = "4DGS-Unity-VR"
    dataset    = $Dataset
    started_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    steps      = $steps
}
$state | ConvertTo-Json -Depth 5 | Set-Content "pipeline_state.json" -Encoding utf8
Write-Host "`n✓ pipeline_state.json written" -ForegroundColor Green

# ── 3. Copy dashboard if needed ──────────────────────────────────────────────
$dashSrc = "C:\Users\10451\skills\project-doc-generator\skills\4dgs-pipeline\scripts\pipeline_dashboard.py"
if (-not (Test-Path "pipeline_dashboard.py")) {
    if (Test-Path $dashSrc) {
        Copy-Item $dashSrc "pipeline_dashboard.py"
        Write-Host "✓ pipeline_dashboard.py copied" -ForegroundColor Green
    } else {
        Write-Host "⚠ Could not find dashboard script at: $dashSrc" -ForegroundColor Yellow
    }
}

# ── 4. Create logs directory ─────────────────────────────────────────────────
New-Item -ItemType Directory -Force "logs" | Out-Null

# ── 5. Check Flask ───────────────────────────────────────────────────────────
$flaskOk = $false
foreach ($env in @("Gaussians4D", "compress", "base")) {
    $result = & conda run -n $env python -c "import flask" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Flask found in conda env: $env" -ForegroundColor Green
        $flaskOk = $true
        $script:flaskEnv = $env
        break
    }
}
if (-not $flaskOk) {
    Write-Host "⚠ Flask not found. Install with:" -ForegroundColor Yellow
    Write-Host "  conda activate Gaussians4D && pip install flask" -ForegroundColor Yellow
}

# ── 6. Start dashboard ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting dashboard on http://localhost:$Port ..." -ForegroundColor Cyan

if ($flaskOk) {
    $job = Start-Job {
        param($env, $dir, $port)
        Set-Location $dir
        & conda run -n $env python pipeline_dashboard.py
    } -ArgumentList $script:flaskEnv, (Get-Location).Path, $Port

    Start-Sleep 3
    Write-Host "✓ Dashboard started (Job ID: $($job.Id))" -ForegroundColor Green
    Write-Host "  Open: http://localhost:$Port" -ForegroundColor Cyan
    Write-Host "  Stop: Stop-Job $($job.Id); Remove-Job $($job.Id)"
} else {
    Write-Host "  Please install Flask first, then run:" -ForegroundColor Yellow
    Write-Host "  conda activate Gaussians4D" -ForegroundColor Yellow
    Write-Host "  python pipeline_dashboard.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Next steps ===" -ForegroundColor Cyan
if (-not $colmapDone -and $isDyNeRF) { Write-Host "  1. Run COLMAP (see CLAUDE.md §3)" }
if (-not $trainDone)    { Write-Host "  → Train: see CLAUDE.md §4" }
elseif (-not $exportDone)   { Write-Host "  → Export PLY: see CLAUDE.md §5" }
elseif (-not $compressDone) { Write-Host "  → Compress: see CLAUDE.md §6" }
else { Write-Host "  → All ML steps done! Import into Unity (CLAUDE.md §7)" -ForegroundColor Green }
