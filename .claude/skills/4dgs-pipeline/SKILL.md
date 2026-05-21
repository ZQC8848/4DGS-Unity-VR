---
name: 4dgs-pipeline
description: Run the full 4D Gaussian Splatting to Unity pipeline. Use when
  the user says "run the pipeline", "train the 4DGS model", "start training",
  "run 4DGS on <dataset>", "start the pipeline", "run everything", or asks
  to execute any stage of the 4DGS-Unity-VR workflow (COLMAP, training, PLY
  export, compression, Unity import). Also use when the user asks to resume
  a pipeline stage or check pipeline status. Includes a live dashboard at
  localhost:7860 showing step checkboxes and progress bars — Claude never
  reads log files into context.
---

# 4DGS Pipeline Skill

Runs and monitors the full pipeline: environment → COLMAP → training → PLY export → compression → Unity.

**Core constraint**: All long-running commands are redirected to log files. Claude never reads full logs into context. The dashboard at `http://localhost:7860` handles all monitoring.

---

## Step 0: Start Dashboard

Before anything else, copy and start the dashboard if not already running.

```powershell
# Copy dashboard script to project root (first time only)
$skill_root = (Get-Item $PSCommandPath).DirectoryName
$scripts_dir = Join-Path $skill_root "scripts"
if (-not (Test-Path "pipeline_dashboard.py")) {
    Copy-Item "$scripts_dir\pipeline_dashboard.py" "pipeline_dashboard.py"
}

# Start in background (hidden window)
$running = Get-Process python -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -like "*pipeline_dashboard*" }
if (-not $running) {
    Start-Process python -ArgumentList "pipeline_dashboard.py" `
        -WorkingDirectory (Get-Location) -WindowStyle Hidden
    Start-Sleep 2
}
```

Tell the user: **"Dashboard is live at http://localhost:7860 — open it in your browser to monitor progress."**

---

## Step 1: Collect Configuration

Ask the user (if not already known):
- **Dataset**: `lego` (D-NeRF, ~16 min) or `coffee_martini` (DyNeRF, ~46 min) or other
- **Working directory**: default `C:\UnityProjects\`
- **Any steps already done?** (e.g. env already set up, COLMAP already done)

Initialize the pipeline state via the dashboard API:

```powershell
$dataset = "coffee_martini"  # fill from user input
$body = @{
    project = "4DGS-Unity-VR"
    dataset = $dataset
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:7860/api/init" `
    -Method Post -Body $body -ContentType "application/json"
```

---

## Step 2: Environment Setup

```powershell
# Mark in_progress
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="env"; status="in_progress"} | ConvertTo-Json) `
    -ContentType "application/json"
```

Follow CLAUDE.md §1 for environment setup commands.
When complete:
```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="env"; status="done"} | ConvertTo-Json) `
    -ContentType "application/json"
```

---

## Step 3: COLMAP Point Cloud (DyNeRF only)

Skip this step for D-NeRF synthetic datasets.

```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="colmap"; status="in_progress"} | ConvertTo-Json) `
    -ContentType "application/json"
```

Follow CLAUDE.md §3 for COLMAP commands. When done:
```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="colmap"; status="done"} | ConvertTo-Json) `
    -ContentType "application/json"
```

---

## Step 4: Training

```powershell
New-Item -ItemType Directory -Force "logs" | Out-Null

# Mark in_progress with log path
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="train"; status="in_progress"; log="logs/train.log"} | ConvertTo-Json) `
    -ContentType "application/json"
```

**ALWAYS redirect training output to a log file. Do NOT capture output into context.**

```powershell
conda activate Gaussians4D
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects

# D-NeRF example (lego):
python 4DGaussians/train.py `
    -s 4DGS_TrainData/data/lego `
    --port 6017 --expname "dnerf/lego" `
    --configs 4DGaussians/arguments/dnerf/lego.py `
    2>&1 | Tee-Object "logs/train.log"

# DyNeRF example (coffee_martini):
python 4DGaussians/train.py `
    -s 4DGS_TrainData/coffee_martini `
    --port 6017 --expname "dynerf/coffee_martini" `
    --configs 4DGaussians/arguments/dynerf/coffee_martini.py `
    2>&1 | Tee-Object "logs/train.log"
```

**After training finishes**, verify with last 5 lines only:
```powershell
Get-Content "logs/train.log" -Tail 5
```
Look for `Training complete.` — if present, mark done. If not, check for errors.

```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="train"; status="done"} | ConvertTo-Json) `
    -ContentType "application/json"
```

Tell user: **"Training done. Check dashboard: http://localhost:7860"**

---

## Step 5: Export Per-Frame PLY

```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="export_ply"; status="in_progress"} | ConvertTo-Json) `
    -ContentType "application/json"

conda activate Gaussians4D
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects

python 4DGaussians/export_perframe_3DGS.py `
    --iteration 14000 `
    --configs 4DGaussians/arguments/dnerf/lego.py `
    --model_path output/dnerf/lego `
    2>&1 | Tee-Object "logs/export.log"
```

The dashboard auto-tracks progress by counting `time_*.ply` files — no need to read the log.

After export, rename files:
```powershell
$dir = "C:\UnityProjects\output\dnerf\lego\gaussian_pertimestamp"
$files = Get-ChildItem $dir -Filter "time_*.ply" | Sort-Object Name
$i = 0; foreach ($f in $files) { Rename-Item $f.FullName "point_cloud_$i.ply"; $i++ }

Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="export_ply"; status="done"} | ConvertTo-Json) `
    -ContentType "application/json"
```

---

## Step 6: Compress to .dgs

```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="compress"; status="in_progress"; log="logs/compress.log"} | ConvertTo-Json) `
    -ContentType "application/json"

conda activate compress
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects

python DynGsplat-unity/CompressScripts/compress.py `
    --data_path "output/dnerf/lego/gaussian_pertimestamp" `
    --output_path "GSplatTest/Assets/DynGsplatData/lego" `
    --st 0 --ed 19 --codebook_size 16385 --len_block 20 --data_name lego `
    2>&1 | Tee-Object "logs/compress.log"
```

The dashboard tracks progress via `Block*.dgsblk` file count.

Verify with last 3 lines only, then mark done:
```powershell
Get-Content "logs/compress.log" -Tail 3

Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="compress"; status="done"} | ConvertTo-Json) `
    -ContentType "application/json"
```

---

## Step 7: Unity Import

```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="unity"; status="in_progress"} | ConvertTo-Json) `
    -ContentType "application/json"
```

Guide the user through CLAUDE.md §7 (Unity import steps — manual). When confirmed:
```powershell
Invoke-RestMethod -Uri "http://localhost:7860/api/update" -Method Post `
    -Body (@{step_id="unity"; status="done"} | ConvertTo-Json) `
    -ContentType "application/json"
```

---

## Resuming a Pipeline

If the user asks to resume or run a specific stage:
1. Read `pipeline_state.json` (tiny, ~1 KB) to check current state
2. Jump to the relevant step — skip all completed ones
3. Start the dashboard if not running

```powershell
Get-Content pipeline_state.json | ConvertFrom-Json | Select-Object -ExpandProperty steps |
    Format-Table id, label, status
```

---

## Error Handling

If any step fails:
1. Read ONLY the last 10 lines of the relevant log file
2. Update state to `"error"`: `@{step_id="train"; status="error"}`
3. Report the error to the user
4. Do NOT read the full log into context — tail 10 lines is enough for diagnosis

---

## Dashboard URL

Always remind the user: **http://localhost:7860**

Stop the dashboard when done:
```powershell
Get-Process python | Where-Object { $_.CommandLine -like "*pipeline_dashboard*" } |
    Stop-Process -Force
```
