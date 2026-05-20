# Dynamic 3D Gaussian Splatting — Unity 实时渲染 Pipeline

从多视角视频训练动态高斯溅射模型，压缩后在 Unity 中实时播放的完整工作流。

```
多视角视频 / 开源数据集
        ↓  训练（4DGaussians）
   逐帧 PLY 序列
        ↓  压缩（DynGsplat）
      .dgs 文件
        ↓  导入 Unity
     实时预览播放
```

## 项目结构

```
C:\UnityProjects\
├── 4DGaussians\          # 训练框架（4D Gaussian Splatting, CVPR 2024）
├── DynGsplat-unity\      # 压缩工具 + Unity 渲染包
│   ├── CompressScripts\  # PLY → .dgs 压缩脚本
│   ├── Gsplat\           # Unity 静态 GS 渲染包 (wu.yize.gsplat)
│   └── DynGsplat\        # Unity 动态 GS 渲染包 (org.hifihuman.dyngsplat)
├── GSplatTest\           # Unity 6 测试项目 (URP)
└── 4DGS_TrainData\       # 训练数据集（不纳入 Git）
```

## 环境要求

| 组件 | 版本 |
|------|------|
| Windows | 11 |
| NVIDIA GPU | 支持 CUDA 12.1（本文档以 RTX 3070 Ti 笔记本为例） |
| CUDA Toolkit | 12.1 |
| Miniconda | 最新版 |
| Unity | 6000.0.23f1（Unity 6） |
| Git | 2.x |

---

## 一、环境配置

### 1.1 训练环境（Gaussians4D）

用于 4DGaussians 训练和逐帧 PLY 导出。

```powershell
# 创建环境
conda create -n Gaussians4D python=3.9 -y
conda activate Gaussians4D

# 安装 PyTorch（CUDA 12.1）
pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 `
    --index-url https://download.pytorch.org/whl/cu121

# 安装其他依赖
pip install mmcv==1.6.0 --no-build-isolation
pip install matplotlib lpips plyfile pytorch_msssim open3d "imageio[ffmpeg]"
pip install "numpy==1.26.4"

# 修改两个 submodule 的 setup.py，添加 MSVC/CUDA 兼容标志（见下方说明）
# 然后编译 CUDA 扩展
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
pip install -e submodules/depth-diff-gaussian-rasterization --no-build-isolation
pip install -e submodules/simple-knn --no-build-isolation
```

> **MSVC + CUDA 12.1 兼容性修复**：在两个 submodule 的 `setup.py` 的 `extra_compile_args` 中添加：
> - nvcc flags: `--allow-unsupported-compiler`, `-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`
> - cxx flags: `/D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`
>
> 同时在 `submodules/simple-knn/simple_knn/` 目录下创建空的 `__init__.py`，
> 否则 Windows 下 editable install 无法正确识别该包。

### 1.2 压缩环境（compress）

用于将 PLY 序列压缩为 `.dgs` 格式。

```powershell
conda create -n compress python=3.9 -y
conda activate compress

# 安装 PyTorch（CUDA 12.1）
pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 `
    --index-url https://download.pytorch.org/whl/cu121

# 编译 weighted_distance CUDA 扩展
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\DynGsplat-unity\CompressScripts
pip install weighted_distance/ --no-build-isolation

# 安装其他依赖
pip install -r requirements.txt
```

> `weighted_distance/setup.py` 同样需要添加上述 MSVC/CUDA 兼容标志。

### 1.3 Unity 项目配置

1. 在 Unity 中打开 `GSplatTest` 项目（Unity 6，URP）

2. **Graphics API**：`Edit → Project Settings → Player → Other Settings`
   - 取消勾选 `Auto Graphics API for Windows`
   - 只保留 `Direct3D12` 或 `Vulkan`

3. **Color Space**：同一页面将 `Color Space` 改为 `Gamma`

4. **URP Renderer Feature**：找到项目使用的 `Universal Renderer Data`
   - 点击 `Add Renderer Feature` → 选择 `Gsplat URP Feature`
   - Unity 6 需关闭 Render Graph 兼容模式：`URP Settings → Compatibility Mode → Off`

5. **Addressables 初始化**：
   `Window → Asset Management → Addressables → Groups → Create Addressables Settings`

Unity 包通过本地路径引用，已在 `GSplatTest/Packages/manifest.json` 中配置：
```json
{
  "dependencies": {
    "wu.yize.gsplat": "file:C:/UnityProjects/DynGsplat-unity/Gsplat",
    "org.hifihuman.dyngsplat": "file:C:/UnityProjects/DynGsplat-unity/DynGsplat",
    ...
  }
}
```

---

## 二、数据准备

### 方案 A：开源数据集（推荐入门）

**D-NeRF 合成数据集**（无需 COLMAP，下载即用）：

从 Dropbox 下载后解压到 `4DGS_TrainData/data/`：

```
4DGS_TrainData\data\lego\
    train\        # r_0.png ~ r_49.png（50帧，每帧一个视角）
    test\         # r_000.png ~ r_019.png
    val\
    transforms_train.json
    transforms_test.json
    transforms_val.json
```

可用场景：`lego`、`bouncingballs`、`mutant`、`standup`、`jumpingjacks`、`hellwarrior`、`hook`、`trex`

### 方案 B：自拍多视角数据

多台同步摄像机拍摄动态场景，按如下结构组织：

```
4DGS_TrainData\data\multipleview\<你的数据集名>\
    cam01\
        frame_00001.jpg
        frame_00002.jpg
        ...
    cam02\
        ...
```

然后运行 COLMAP 预处理（需要安装 COLMAP）：
```bash
cd C:\UnityProjects\4DGaussians
bash multipleviewprogress.sh <你的数据集名>
```

---

## 三、训练

```powershell
conda activate Gaussians4D
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\4DGaussians

# D-NeRF 合成数据（以 lego 为例）
python train.py `
    -s C:\UnityProjects\4DGS_TrainData\data\lego `
    --port 6017 `
    --expname "dnerf/lego" `
    --configs arguments/dnerf/lego.py

# 多视角自拍数据
python train.py `
    -s C:\UnityProjects\4DGS_TrainData\data\multipleview\<数据集名> `
    --port 6017 `
    --expname "multipleview/<数据集名>" `
    --configs arguments/multipleview/default.py
```

训练分两阶段，共 23,000 次迭代：

| 阶段 | 迭代数 | RTX 3070 Ti 笔记本耗时 |
|------|--------|----------------------|
| 粗训练 | 3,000 | ~1 分钟 |
| 细训练 | 20,000 | ~15 分钟 |
| **合计** | **23,000** | **~16 分钟** |

训练结果保存在 `4DGaussians/output/dnerf/lego/`，最终 Test PSNR 约 **25 dB**，Train PSNR 约 **36 dB**。

---

## 四、导出逐帧 PLY

```powershell
conda activate Gaussians4D
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\4DGaussians

python export_perframe_3DGS.py `
    --iteration 14000 `
    --configs arguments/dnerf/lego.py `
    --model_path output/dnerf/lego
```

输出：`output/dnerf/lego/gaussian_pertimestamp/time_00000.ply` ~ `time_000XX.ply`

导出后需重命名以匹配压缩脚本的命名规范：

```powershell
$dir = "C:\UnityProjects\4DGaussians\output\dnerf\lego\gaussian_pertimestamp"
$files = Get-ChildItem $dir -Filter "time_*.ply" | Sort-Object Name
$i = 0
foreach ($f in $files) { Rename-Item $f.FullName "point_cloud_$i.ply"; $i++ }
```

---

## 五、压缩为 .dgs

```powershell
conda activate compress
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
cd C:\UnityProjects\DynGsplat-unity\CompressScripts

python compress.py `
    --data_path "C:\UnityProjects\4DGaussians\output\dnerf\lego\gaussian_pertimestamp" `
    --output_path "C:\UnityProjects\GSplatTest\Assets\DynGsplatData\lego" `
    --st 0 `
    --ed 19 `
    --codebook_size 16385 `
    --len_block 20 `
    --data_name lego
```

| 参数 | 说明 |
|------|------|
| `--st` / `--ed` | 起始 / 结束帧编号（从 0 开始，对应 `point_cloud_0.ply` ~ `point_cloud_N.ply`） |
| `--codebook_size` | 码本大小，越大质量越高，`2**14+1 = 16385` 为默认值 |
| `--len_block` | 每个压缩块包含的帧数，影响流式播放的内存占用 |

输出直接写入 Unity 项目的 Assets 目录：

```
GSplatTest\Assets\DynGsplatData\lego\
    lego.dgs          # 元数据（JSON，<1 KB）
    Data\
        Block0.dgsblk # 压缩帧数据（~79 MB，原始 450 MB，压缩率约 83%）
```

---

## 六、Unity 导入与预览

1. **等待 Unity 自动导入**：Unity 检测到 Assets 目录变化后自动处理 `.dgs` 和 `.dgsblk` 文件

2. **确认 Addressables**：
   - `Window → Asset Management → Addressables → Groups`
   - 确认 lego 数据已出现在 "DynGsplat Assets" 组中

3. **添加渲染器**：
   - 层级面板右键 → `Create Empty`，命名为 `LegoRenderer`
   - `Add Component` → 搜索 `Dyn Gsplat Renderer`
   - 将 `Assets/DynGsplatData/lego/lego`（`Dyn Gsplat Asset`）拖到 `Asset Ref` 字段

4. **播放**：勾选 `Is Playing`，即可在 Scene / Game 视图中看到动态 Gaussian Splatting 序列

| 组件属性 | 说明 |
|---------|------|
| `Asset Ref` | 指向 `.dgs` 对应的 Dyn Gsplat Asset |
| `Is Playing` | 播放 / 暂停 |
| `Streaming` | 开启后最多只加载 2 个 Block 到内存 |
| `Async Loading` | 异步加载，避免卡顿 |
| `Gamma To Linear` | 在 Linear 色彩空间项目中使用（会降低质量，建议保持 Gamma 模式） |

---

## 常见问题

### `ModuleNotFoundError: No module named 'simple_knn'`

`simple_knn` 通过 editable install 安装时，Windows 下需要在包目录手动创建 `__init__.py`：

```powershell
New-Item -ItemType File `
    "C:\UnityProjects\4DGaussians\submodules\simple-knn\simple_knn\__init__.py"
```

### `DLL load failed while importing _C`

CUDA 运行时 DLL 不在 PATH 中。每次运行训练/压缩前执行：

```powershell
$env:PATH = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin;" + $env:PATH
```

### `STL1002: Unexpected compiler version` / `unsupported Microsoft Visual Studio version`

MSVC 14.44 与 CUDA 12.1 的兼容性问题。在 `setup.py` 的 `extra_compile_args` 中添加：
- nvcc: `--allow-unsupported-compiler`, `-D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`
- cxx: `/D_ALLOW_COMPILER_AND_STL_VERSION_MISMATCH`

### Unity Package Manager 无法找到本地包

直接编辑 `GSplatTest/Packages/manifest.json`（文件可能需要先授予写权限）：

```powershell
icacls "C:\UnityProjects\GSplatTest\Packages\manifest.json" /grant "${env:USERNAME}:(F)"
```

---

## 参考项目

- [4DGaussians](https://github.com/hustvl/4DGaussians) — Wu et al., CVPR 2024
- [DynGsplat-unity](https://github.com/HiFi-Human/DynGsplat-unity) — HiFi-Human
- [gsplat-unity](https://github.com/wuyize25/gsplat-unity) — wuyize25
