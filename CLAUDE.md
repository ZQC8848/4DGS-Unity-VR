# 4DGS-Unity-VR 项目全流程 Onboarding

## 项目概述

从多视角视频训练动态 4D Gaussian Splatting 模型，压缩后在 Unity 中实时播放。

```
多视角视频 / 开源数据集
        ↓  训练（4DGaussians）
   逐帧 PLY 序列
        ↓  压缩（DynGsplat）
      .dgs 文件
        ↓  导入 Unity
     实时预览播放
```

**项目路径**：`C:\UnityProjects\`  
**GitHub**：`https://github.com/ZQC8848/4DGS-Unity-VR.git`

---

## 目录结构

```
C:\UnityProjects\
├── 4DGaussians\          # 训练框架（git submodule）
├── DynGsplat-unity\      # 压缩工具 + Unity 包（git submodule）
│   ├── CompressScripts\  # PLY → .dgs 压缩脚本
│   ├── Gsplat\           # Unity 静态 GS 渲染包
│   └── DynGsplat\        # Unity 动态 GS 渲染包
├── GSplatTest\           # Unity 6 测试项目（URP）
├── 4DGS_TrainData\       # 训练数据（不进 Git）
│   ├── data\lego\        # D-NeRF 合成数据集
│   └── coffee_martini\   # DyNeRF 真实多相机数据集
├── output\               # 训练输出（不进 Git）
│   ├── dnerf\lego\
│   └── dynerf\coffee_martini\
└── colmap_coffee\        # COLMAP 中间文件（不进 Git）
```

---

## 一、Conda 环境配置

### 1.1 训练环境 Gaussians4D

```powershell
conda create -n Gaussians4D python=3.9 -y
conda activate Gaussians4D

pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 `
    --index-url https://download.pytorch.org/whl/cu121

pip install mmcv==1.6.0 --no-build-isolation
pip install matplotlib lpips plyfile pytorch_msssim open3d "imageio[ffmpeg]"
pip install "numpy==1.26.4"

$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
pip install -e submodules/depth-diff-gaussian-rasterization --no-build-isolation
pip install -e submodules/simple-knn --no-build-isolation
```

**必须修复的编译问题（MSVC 14.44 + CUDA 12.1 不兼容）**：

在两个 submodule 的 `setup.py` 中 `extra_compile_args` 加入：
- nvcc flags: `--allow-unsupported-compiler`, `-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`
- cxx flags: `/D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`

**必须创建空文件**（否则 editable install 在 Windows 上找不到包）：
```powershell
New-Item -ItemType File "C:\UnityProjects\4DGaussians\submodules\simple-knn\simple_knn\__init__.py"
```

**自动添加 CUDA 到 PATH**（每次 activate 自动生效）：
```powershell
# 文件：C:\Users\<用户名>\miniconda3\envs\Gaussians4D\etc\conda\activate.d\cuda_path.bat
SET "PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;%PATH%"
```

### 1.2 压缩环境 compress

```powershell
conda create -n compress python=3.9 -y
conda activate compress

pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 `
    --index-url https://download.pytorch.org/whl/cu121

$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\DynGsplat-unity\CompressScripts
pip install weighted_distance/ --no-build-isolation
pip install -r requirements.txt
```

`weighted_distance/setup.py` 同样需要 MSVC/CUDA 兼容标志。

---

## 二、数据集

### 方案 A：D-NeRF 合成数据集（入门推荐）

**下载**：`https://www.dropbox.com/scl/fi/cdcmkufncwcikk1dzbgb4/data.zip?dl=0&e=1&rlkey=n5m21i84v2b2xk6h7qgiu8nkg`

解压到 `4DGS_TrainData\data\`，包含 lego / bouncingballs / mutant 等场景。

格式：`transforms_train.json` + 图片，**每个时刻只有 1 个视角**（单目视频风格）。无需 COLMAP，直接训练。

### 方案 B：DyNeRF 真实多相机数据集

**下载**：`https://github.com/facebookresearch/Neural_3D_Video`（Release v1.0）

场景：coffee_martini / cook_spinach / cut_roasted_beef / flame_salmon_1 / flame_steak / sear_steak

格式：`cam*.mp4`（18 台同步摄像机）+ `poses_bounds.npy`（相机标定）

**重要**：官方数据集不含 `points3D_downsample2.ply`，需要用 COLMAP 自行生成（见第三节）。

---

## 三、DyNeRF 点云生成（方案 B 必须步骤）

官方数据集缺少 `points3D_downsample2.ply`，训练前必须生成。

### 3.1 安装 COLMAP

从 `https://github.com/colmap/colmap/releases` 下载 Windows CUDA 版，解压到 `C:\colmap\`。

### 3.2 提取首帧

```powershell
conda activate Gaussians4D
& python C:\UnityProjects\4DGaussians\scripts\extract_first_frames.py `
    "C:\UnityProjects\4DGS_TrainData\coffee_martini" `
    "C:\UnityProjects\colmap_coffee\images"
```

（脚本位于 `4DGaussians\scripts\extract_first_frames.py`，本项目已添加）

### 3.3 COLMAP 完整流程

```powershell
$COLMAP = "C:\colmap\COLMAP.bat"
$workspace = "C:\UnityProjects\colmap_coffee"

# 特征提取
& $COLMAP feature_extractor --database_path "$workspace\database.db" --image_path "$workspace\images"

# 特征匹配
& $COLMAP exhaustive_matcher --database_path "$workspace\database.db"

# SFM 重建
New-Item -ItemType Directory -Force "$workspace\sparse" | Out-Null
& $COLMAP mapper --database_path "$workspace\database.db" --image_path "$workspace\images" --output_path "$workspace\sparse"

# 去畸变
New-Item -ItemType Directory -Force "$workspace\dense" | Out-Null
& $COLMAP image_undistorter --image_path "$workspace\images" --input_path "$workspace\sparse\0" --output_path "$workspace\dense" --output_type COLMAP

# 稠密 MVS（GPU，约 20 分钟）
& $COLMAP patch_match_stereo --workspace_path "$workspace\dense" --workspace_format COLMAP --PatchMatchStereo.geom_consistency true

# 点云融合（用宽松参数，否则只有 1923 点）
& $COLMAP stereo_fusion --workspace_path "$workspace\dense" --workspace_format COLMAP --input_type geometric --output_path "$workspace\dense\fused.ply" --StereoFusion.min_num_pixels 2 --StereoFusion.max_reproj_error 4 --StereoFusion.max_depth_error 0.02

# 下采样到 ≤40000 点
conda activate Gaussians4D
& python C:\UnityProjects\4DGaussians\scripts\downsample_point.py `
    "$workspace\dense\fused.ply" `
    "C:\UnityProjects\4DGS_TrainData\coffee_martini\points3D_downsample2.ply"
```

**关键参数**：stereo_fusion 默认 `min_num_pixels=5` 对反光场景太严，结果只有 1923 点；改为 2 可得到 44000+ 点。

---

## 四、训练

训练命令必须从 `C:\UnityProjects\` 目录运行（否则 output 路径不对）。

### 方案 A：D-NeRF 合成数据

```powershell
conda activate Gaussians4D
cd C:\UnityProjects
python 4DGaussians/train.py `
    -s 4DGS_TrainData/data/lego `
    --port 6017 `
    --expname "dnerf/lego" `
    --configs 4DGaussians/arguments/dnerf/lego.py
```

耗时：RTX 3070 Ti 笔记本约 16 分钟，Test PSNR ~25 dB。

### 方案 B：DyNeRF 真实数据

```powershell
conda activate Gaussians4D
cd C:\UnityProjects
python 4DGaussians/train.py `
    -s 4DGS_TrainData/coffee_martini `
    --port 6017 `
    --expname "dynerf/coffee_martini" `
    --configs 4DGaussians/arguments/dynerf/coffee_martini.py
```

**重要**：`arguments/dynerf/coffee_martini.py` 需设置 `batch_size=1`（否则在 3070 Ti 上细训练速度只有 0.25 it/s，需要 17 小时）：

```python
# arguments/dynerf/coffee_martini.py
_base_ = './default.py'
OptimizationParams = dict(
    batch_size = 1,
)
```

耗时：RTX 3070 Ti 笔记本约 46 分钟，Test PSNR ~26.3 dB，最终高斯点约 33 万个。

第一次运行会从 MP4 自动解帧（约 5 分钟），之后复用缓存。

**实时查看训练进度**：
```powershell
Get-Content "<output_log_path>" -Wait -Tail 5
```

---

## 五、导出逐帧 PLY

脚本已修改支持 `--max_frames` 参数（均匀采样）。

### 方案 A（D-NeRF，默认导出全部帧）

```powershell
conda activate Gaussians4D
cd C:\UnityProjects
python 4DGaussians/export_perframe_3DGS.py `
    --iteration 14000 `
    --configs 4DGaussians/arguments/dnerf/lego.py `
    --model_path output/dnerf/lego
```

### 方案 B（DyNeRF，300 帧全部导出）

```powershell
conda activate Gaussians4D
cd C:\UnityProjects
python 4DGaussians/export_perframe_3DGS.py `
    --iteration 14000 `
    --configs 4DGaussians/arguments/dynerf/coffee_martini.py `
    --model_path output/dynerf/coffee_martini
```

**注意**：DyNeRF 300 帧 × 78 MB ≈ 23 GB 磁盘。

输出在 `output/<expname>/gaussian_pertimestamp/time_XXXXX.ply`。

### 重命名（compress.py 要求 point_cloud_N.ply 格式）

```powershell
$dir = "C:\UnityProjects\output\dynerf\coffee_martini\gaussian_pertimestamp"
$files = Get-ChildItem $dir -Filter "time_*.ply" | Sort-Object Name
$i = 0
foreach ($f in $files) { Rename-Item $f.FullName "point_cloud_$i.ply"; $i++ }
```

---

## 六、压缩为 .dgs

```powershell
conda activate compress
cd C:\UnityProjects

# lego（20 帧）
python DynGsplat-unity/CompressScripts/compress.py `
    --data_path "output/dnerf/lego/gaussian_pertimestamp" `
    --output_path "GSplatTest/Assets/DynGsplatData/lego" `
    --st 0 --ed 19 --codebook_size 16385 --len_block 20 --data_name lego

# coffee_martini（300 帧，分 15 个 Block）
python DynGsplat-unity/CompressScripts/compress.py `
    --data_path "output/dynerf/coffee_martini/gaussian_pertimestamp" `
    --output_path "GSplatTest/Assets/DynGsplatData/coffee_martini" `
    --st 0 --ed 299 --codebook_size 16385 --len_block 20 --data_name coffee_martini
```

输出结构：
```
GSplatTest/Assets/DynGsplatData/<名称>/
    <名称>.dgs          # 元数据（JSON）
    Data/
        Block0.dgsblk   # 每 20 帧一个 Block
        Block1.dgsblk
        ...
```

压缩率约 83%（coffee_martini：23 GB → 3.98 GB）。

---

## 七、Unity 导入与播放

1. Unity 自动导入（检测到 Assets 变化后处理 .dgs/.dgsblk）
2. `Window → Asset Management → Addressables → Groups` 确认数据出现在 "DynGsplat Assets" 组
3. 层级面板右键 → `Create Empty` → 命名为 `<场景名>Renderer`
4. `Add Component` → `Dyn Gsplat Renderer`
5. 将 `Assets/DynGsplatData/<名称>/<名称>` 拖到 `Asset Ref` 字段
6. 勾选 `Is Playing`，可选开启 `Streaming`（流式加载，节省内存）

---

## 八、常见问题与修复

| 问题 | 原因 | 修复 |
|------|------|------|
| `No module named 'simple_knn'` | editable install 在 Windows 找不到包 | 创建空 `simple_knn/__init__.py` |
| `DLL load failed while importing _C` | CUDA DLL 不在 PATH | 每次运行前 `$env:PATH = "C:\...\CUDA\v12.1\bin;" + $env:PATH` |
| `STL1002: Unexpected compiler version` | MSVC 14.44 与 CUDA 12.1 不兼容 | setup.py 加 `--allow-unsupported-compiler` 等 flag |
| COLMAP stereo_fusion 只有 1923 点 | 反光表面 + 默认 min_num_pixels=5 过严 | 改为 `min_num_pixels=2, max_reproj_error=4, max_depth_error=0.02` |
| DyNeRF 细训练速度 0.25 it/s（17 小时） | batch_size=4 在 3070 Ti 太慢 | 改为 `batch_size=1`，速度提升 80 倍，约 46 分钟 |
| `FileNotFoundError: cfg_args` | 训练时工作目录不对，output 保存位置偏移 | 必须从 `C:\UnityProjects\` 运行 train.py |
| DyNeRF 缺少 `points3D_downsample2.ply` | 官方数据集不含此文件 | 用 COLMAP 生成（见第三节） |
| `pkg_resources` 报错 | mmcv 安装问题 | `pip install mmcv==1.6.0 --no-build-isolation` |

---

## 九、数据集格式对比

| 格式 | 代表数据集 | 每时刻视角数 | 是否需要 COLMAP | 加载器 |
|------|-----------|------------|----------------|-------|
| Blender/D-NeRF | lego 等合成场景 | 1 | 否 | `readNerfSyntheticInfo` |
| DyNeRF | coffee_martini 等 | 18 | 需要生成点云 | `readdynerfInfo` |
| MultipleView | 自拍多相机 | N | 是（完整流程） | `readMultipleViewinfos` |

---

## 十、硬件参考（RTX 3070 Ti 笔记本，8GB VRAM）

| 任务 | 耗时 |
|------|------|
| lego 训练（23000 iter） | ~16 分钟 |
| coffee_martini 训练（batch=1，17000 iter） | ~46 分钟 |
| coffee_martini PLY 导出（300 帧） | ~8 分钟 |
| coffee_martini 压缩（300 帧，15 Block） | ~11 分钟 |
| COLMAP 稠密重建（18 张图） | ~20 分钟 |
