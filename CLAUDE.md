# 4DGS-Unity-VR Full Pipeline

Train a dynamic 4D Gaussian Splatting model from multi-view video, compress it, and play it back in Unity in real time.

```
Multi-view video / open-source dataset
        ↓  Train (4DGaussians, conda: Gaussians4D)
   Per-frame PLY sequence
        ↓  Compress (DynGsplat, conda: compress)
      .dgs file
        ↓  Import to Unity 6
     Real-time playback
```

**Project root**: `C:\UnityProjects\`
**GitHub**: `https://github.com/ZQC8848/4DGS-Unity-VR.git`

---

## Directory Structure

```
C:\UnityProjects\
├── 4DGaussians\          # Training framework (git submodule)
├── DynGsplat-unity\      # Compression tool + Unity packages (git submodule)
│   ├── CompressScripts\  # PLY → .dgs compression scripts
│   ├── Gsplat\           # Unity static GS rendering package
│   └── DynGsplat\        # Unity dynamic GS rendering package
├── GSplatTest\           # Unity 6 test project (URP)
├── 4DGS_TrainData\       # Training data (not tracked in Git)
│   ├── data\lego\        # D-NeRF synthetic dataset
│   └── coffee_martini\   # DyNeRF real multi-camera dataset
├── output\               # Training output (not tracked in Git)
│   ├── dnerf\lego\
│   └── dynerf\coffee_martini\
└── colmap_coffee\        # COLMAP intermediate files (not tracked in Git)
```

---

## 1. Environment Setup

### 1.1 Training Environment — `Gaussians4D`

```powershell
conda create -n Gaussians4D python=3.9 -y
conda activate Gaussians4D

pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 `
    --index-url https://download.pytorch.org/whl/cu121

pip install mmcv==1.6.0 --no-build-isolation
pip install matplotlib lpips plyfile pytorch_msssim open3d "imageio[ffmpeg]"
pip install "numpy==1.26.4"

# Apply MSVC/CUDA compatibility fix to both submodule setup.py files FIRST (see §8)
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\4DGaussians
pip install -e submodules/depth-diff-gaussian-rasterization --no-build-isolation
pip install -e submodules/simple-knn --no-build-isolation
```

**Required fix — MSVC 14.44 + CUDA 12.1 incompatibility**: add these flags to `extra_compile_args` in both submodule `setup.py` files:
- nvcc flags: `--allow-unsupported-compiler`, `-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`
- cxx flags: `/D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`

**Required fix — editable install on Windows**: create an empty `__init__.py` so Python can find the package:
```powershell
New-Item -ItemType File "C:\UnityProjects\4DGaussians\submodules\simple-knn\simple_knn\__init__.py"
```

**Auto-add CUDA to PATH on activate** (one-time setup, avoids repeating `$env:PATH` every session):
```powershell
# File: C:\Users\<username>\miniconda3\envs\Gaussians4D\etc\conda\activate.d\cuda_path.bat
SET "PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;%PATH%"
```

### 1.2 Compression Environment — `compress`

```powershell
conda create -n compress python=3.9 -y
conda activate compress

pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 `
    --index-url https://download.pytorch.org/whl/cu121

# Apply the same MSVC/CUDA fix to weighted_distance/setup.py FIRST
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\DynGsplat-unity\CompressScripts
pip install weighted_distance/ --no-build-isolation
pip install -r requirements.txt
```

### 1.3 Unity Project Setup

1. Open `GSplatTest` in Unity Hub (Unity 6000.0.23f1, URP)
2. **Graphics API**: `Edit → Project Settings → Player → Other Settings`
   - Uncheck `Auto Graphics API for Windows`
   - Keep only `Direct3D12` or `Vulkan`
3. **Color Space**: set `Color Space` to `Gamma` on the same page
4. **URP Renderer Feature**: find the project's `Universal Renderer Data`
   - `Add Renderer Feature → Gsplat URP Feature`
   - Unity 6: disable Render Graph compat mode: `URP Settings → Compatibility Mode → Off`
5. **Addressables init**: `Window → Asset Management → Addressables → Groups → Create Addressables Settings`

Local package paths are already set in `GSplatTest/Packages/manifest.json`:
```json
{
  "dependencies": {
    "wu.yize.gsplat": "file:C:/UnityProjects/DynGsplat-unity/Gsplat",
    "org.hifihuman.dyngsplat": "file:C:/UnityProjects/DynGsplat-unity/DynGsplat"
  }
}
```

---

## 2. Dataset Options

### Option A — D-NeRF Synthetic Dataset (recommended for quick start)

**Download**: https://www.dropbox.com/scl/fi/cdcmkufncwcikk1dzbgb4/data.zip?dl=0&e=1&rlkey=n5m21i84v2b2xk6h7qgiu8nkg

Extract to `4DGS_TrainData\data\`. Scenes: `lego`, `bouncingballs`, `mutant`, `standup`, `jumpingjacks`, `hellwarrior`, `hook`, `trex`.

Format: `transforms_train.json` + images, **one viewpoint per timestep** (monocular-style). No COLMAP needed.

### Option B — DyNeRF Real Multi-Camera Dataset

**Download**: https://github.com/facebookresearch/Neural_3D_Video (Release v1.0)

Scenes: `coffee_martini`, `cook_spinach`, `cut_roasted_beef`, `flame_salmon_1`, `flame_steak`, `sear_steak`

Format: `cam*.mp4` (18 synchronized cameras) + `poses_bounds.npy` (camera calibration)

**Important**: the official dataset does NOT include `points3D_downsample2.ply`. You must generate it with COLMAP before training (see §3).

---

## 3. DyNeRF Point Cloud Generation (Option B prerequisite)

### 3.1 Install COLMAP

Download the Windows CUDA build from https://github.com/colmap/colmap/releases, extract to `C:\colmap\`.

### 3.2 Extract first frames

```powershell
conda activate Gaussians4D
& python C:\UnityProjects\4DGaussians\scripts\extract_first_frames.py `
    "C:\UnityProjects\4DGS_TrainData\coffee_martini" `
    "C:\UnityProjects\colmap_coffee\images"
```

### 3.3 Full COLMAP pipeline

```powershell
$COLMAP = "C:\colmap\COLMAP.bat"
$workspace = "C:\UnityProjects\colmap_coffee"

& $COLMAP feature_extractor --database_path "$workspace\database.db" --image_path "$workspace\images"
& $COLMAP exhaustive_matcher --database_path "$workspace\database.db"

New-Item -ItemType Directory -Force "$workspace\sparse" | Out-Null
& $COLMAP mapper --database_path "$workspace\database.db" --image_path "$workspace\images" --output_path "$workspace\sparse"

New-Item -ItemType Directory -Force "$workspace\dense" | Out-Null
& $COLMAP image_undistorter --image_path "$workspace\images" --input_path "$workspace\sparse\0" --output_path "$workspace\dense" --output_type COLMAP

# Dense MVS — GPU, ~20 min
& $COLMAP patch_match_stereo --workspace_path "$workspace\dense" --workspace_format COLMAP --PatchMatchStereo.geom_consistency true

# Point cloud fusion — use relaxed params or you'll get only ~1923 points on reflective scenes
& $COLMAP stereo_fusion --workspace_path "$workspace\dense" --workspace_format COLMAP `
    --input_type geometric --output_path "$workspace\dense\fused.ply" `
    --StereoFusion.min_num_pixels 2 `
    --StereoFusion.max_reproj_error 4 `
    --StereoFusion.max_depth_error 0.02

# Downsample to ≤40000 points
conda activate Gaussians4D
& python C:\UnityProjects\4DGaussians\scripts\downsample_point.py `
    "$workspace\dense\fused.ply" `
    "C:\UnityProjects\4DGS_TrainData\coffee_martini\points3D_downsample2.ply"
```

**Key parameter**: default `min_num_pixels=5` is too strict for reflective surfaces → results in only 1923 points. Using `2` yields 44000+ points.

---

## 4. Training

**Must run from `C:\UnityProjects\`** (not from inside `4DGaussians/`). The output path is computed relative to cwd — running from the wrong directory causes `FileNotFoundError: cfg_args`.

```powershell
conda activate Gaussians4D
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects
```

### Option A — D-NeRF synthetic data

```powershell
python 4DGaussians/train.py `
    -s 4DGS_TrainData/data/lego `
    --port 6017 `
    --expname "dnerf/lego" `
    --configs 4DGaussians/arguments/dnerf/lego.py
```

Duration (RTX 3070 Ti laptop): ~16 min. Test PSNR ~25 dB.

### Option B — DyNeRF real data

```powershell
python 4DGaussians/train.py `
    -s 4DGS_TrainData/coffee_martini `
    --port 6017 `
    --expname "dynerf/coffee_martini" `
    --configs 4DGaussians/arguments/dynerf/coffee_martini.py
```

**Required**: set `batch_size=1` in `arguments/dynerf/coffee_martini.py` or fine-training takes 17 hours instead of 46 min on a 3070 Ti:

```python
_base_ = './default.py'
OptimizationParams = dict(batch_size=1)
```

Duration: ~46 min. Test PSNR ~26.3 dB. Final Gaussian count: ~330k.
First run auto-decodes MP4 frames (~5 min); subsequent runs reuse the cache.

**Monitor training**:
```powershell
Get-Content "<output_log_path>" -Wait -Tail 5
```

---

## 5. Export Per-Frame PLY

```powershell
conda activate Gaussians4D
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects
```

### Option A — D-NeRF (export all frames)

```powershell
python 4DGaussians/export_perframe_3DGS.py `
    --iteration 14000 `
    --configs 4DGaussians/arguments/dnerf/lego.py `
    --model_path output/dnerf/lego
```

### Option B — DyNeRF (300 frames, use --max_frames to subsample)

```powershell
# Export all 300 frames (~23 GB total)
python 4DGaussians/export_perframe_3DGS.py `
    --iteration 14000 `
    --configs 4DGaussians/arguments/dynerf/coffee_martini.py `
    --model_path output/dynerf/coffee_martini

# Or subsample to N frames (uniform sampling, saves disk space)
python 4DGaussians/export_perframe_3DGS.py `
    --iteration 14000 `
    --configs 4DGaussians/arguments/dynerf/coffee_martini.py `
    --model_path output/dynerf/coffee_martini `
    --max_frames 60
```

Output: `output/<expname>/gaussian_pertimestamp/time_XXXXX.ply`

**Rename** (compress.py requires `point_cloud_N.ply` format):

```powershell
$dir = "C:\UnityProjects\output\dynerf\coffee_martini\gaussian_pertimestamp"
$files = Get-ChildItem $dir -Filter "time_*.ply" | Sort-Object Name
$i = 0
foreach ($f in $files) { Rename-Item $f.FullName "point_cloud_$i.ply"; $i++ }
```

---

## 6. Compress to .dgs

```powershell
conda activate compress
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects
```

### lego (20 frames)

```powershell
python DynGsplat-unity/CompressScripts/compress.py `
    --data_path "output/dnerf/lego/gaussian_pertimestamp" `
    --output_path "GSplatTest/Assets/DynGsplatData/lego" `
    --st 0 --ed 19 --codebook_size 16385 --len_block 20 --data_name lego
```

### coffee_martini (300 frames, 15 blocks)

```powershell
python DynGsplat-unity/CompressScripts/compress.py `
    --data_path "output/dynerf/coffee_martini/gaussian_pertimestamp" `
    --output_path "GSplatTest/Assets/DynGsplatData/coffee_martini" `
    --st 0 --ed 299 --codebook_size 16385 --len_block 20 --data_name coffee_martini
```

Output:
```
GSplatTest/Assets/DynGsplatData/<name>/
    <name>.dgs          # metadata (JSON)
    Data/
        Block0.dgsblk   # 20 frames per block
        Block1.dgsblk
        ...
```

Compression ratio: ~83% (coffee_martini: 23 GB → 3.98 GB).

---

## 7. Unity Import and Playback

1. Unity auto-imports `.dgs` and `.dgsblk` files when it detects Assets changes
2. `Window → Asset Management → Addressables → Groups` — confirm data appears in "DynGsplat Assets" group
3. Hierarchy panel → right-click → `Create Empty` → name it `<SceneName>Renderer`
4. `Add Component → Dyn Gsplat Renderer`
5. Drag `Assets/DynGsplatData/<name>/<name>` to the `Asset Ref` field
6. Check `Is Playing`; optionally enable `Streaming` (loads max 2 blocks at a time, saves memory)

| Property | Description |
|----------|-------------|
| `Asset Ref` | Points to the `.dgs` Dyn Gsplat Asset |
| `Is Playing` | Play / pause |
| `Streaming` | Load only 2 blocks at a time |
| `Async Loading` | Async load to prevent frame hitches |
| `Gamma To Linear` | For Linear color space projects (reduces quality — keep Gamma mode) |

---

## 8. Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `No module named 'simple_knn'` | editable install can't find package on Windows | Create empty `simple_knn/__init__.py` |
| `DLL load failed while importing _C` | CUDA DLL not in PATH | `$env:PATH = "C:\...\CUDA\v12.1\bin;" + $env:PATH` before each session |
| `STL1002: Unexpected compiler version` | MSVC 14.44 incompatible with CUDA 12.1 | Add `--allow-unsupported-compiler`, `-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH` to setup.py |
| COLMAP stereo_fusion: only 1923 points | Default `min_num_pixels=5` too strict for reflective surfaces | Use `min_num_pixels=2, max_reproj_error=4, max_depth_error=0.02` |
| DyNeRF fine-training: 0.25 it/s (17 hrs) | `batch_size=4` too large for 3070 Ti | Set `batch_size=1` in `arguments/dynerf/coffee_martini.py` |
| `FileNotFoundError: cfg_args` | Wrong working directory — output path is computed from cwd | Must run `train.py` from `C:\UnityProjects\` |
| DyNeRF missing `points3D_downsample2.ply` | Official dataset doesn't include it | Generate with COLMAP (see §3) |
| `pkg_resources` error on mmcv | mmcv build issue | `pip install mmcv==1.6.0 --no-build-isolation` |

---

## 9. Dataset Format Comparison

| Format | Example dataset | Views per timestep | COLMAP required | Loader |
|--------|----------------|-------------------|-----------------|--------|
| Blender/D-NeRF | lego, bouncingballs | 1 (monocular) | No | `readNerfSyntheticInfo` |
| DyNeRF | coffee_martini | 18 | Yes (point cloud only) | `readdynerfInfo` |
| MultipleView | custom capture | N | Yes (full pipeline) | `readMultipleViewinfos` |

---

## 10. Hardware Reference (RTX 3070 Ti laptop, 8 GB VRAM)

| Task | Duration |
|------|----------|
| lego training (23,000 iter) | ~16 min |
| coffee_martini training (batch=1, 17,000 iter) | ~46 min |
| coffee_martini PLY export (300 frames) | ~8 min |
| coffee_martini compression (300 frames, 15 blocks) | ~11 min |
| COLMAP dense reconstruction (18 images) | ~20 min |
