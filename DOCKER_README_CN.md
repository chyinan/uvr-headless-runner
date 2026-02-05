# UVR Headless Runner - Docker 部署指南

> 🎵 专业级音频源分离工具的容器化部署方案

## 📋 概述

本项目提供了 Ultimate Vocal Remover (UVR) 的 Docker 化部署方案，支持：

- **三种架构**: MDX-Net/Roformer, Demucs, VR Architecture
- **GPU 加速**: NVIDIA CUDA 12.x 支持
- **CPU 回退**: 自动检测并回退到 CPU 模式
- **原生 CLI 体验**: 无需手动输入 `docker run` 命令
- **模型持久化**: 模型自动缓存，避免重复下载

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- (可选) NVIDIA GPU + nvidia-container-toolkit (用于 GPU 加速)

### 一键安装

**Linux/macOS:**
```bash
# 自动检测 GPU 支持
./docker/install.sh

# 或强制指定模式
./docker/install.sh --gpu   # GPU 模式
./docker/install.sh --cpu   # CPU 模式
```

**Windows (PowerShell):**
```powershell
# 自动检测 GPU 支持
.\docker\install.ps1

# 或强制指定模式
.\docker\install.ps1 -Gpu   # GPU 模式
.\docker\install.ps1 -Cpu   # CPU 模式
```

### 使用示例

安装完成后，你可以像使用原生命令一样使用 UVR：

```bash
# MDX-Net/Roformer 分离
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/

# Demucs 分离
uvr-demucs -m htdemucs -i song.wav -o output/

# VR Architecture 分离
uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/

# 统一入口
uvr mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
uvr demucs -m htdemucs -i song.wav -o output/
uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
```

## 📦 项目结构

```
docker/
├── Dockerfile           # 多阶段构建 (CPU + GPU)
├── docker-compose.yml   # Docker Compose 配置
├── entrypoint.sh        # 容器入口脚本
├── install.sh           # Linux/macOS 安装脚本
├── install.ps1          # Windows 安装脚本
└── bin/
    ├── uvr              # 统一 CLI 入口
    ├── uvr-mdx          # MDX-Net 专用 CLI
    ├── uvr-demucs       # Demucs 专用 CLI
    └── uvr-vr           # VR Architecture 专用 CLI
```

## 🔧 详细配置

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UVR_MODELS_DIR` | `~/.uvr_models` | 模型缓存目录 |
| `UVR_DEVICE` | 自动检测 | 强制指定设备 (`cuda`/`cpu`) |
| `UVR_INSTALL_DIR` | `/usr/local/bin` | CLI 安装目录 |

### 手动构建镜像

```bash
# 构建 GPU 镜像
docker build -t uvr-headless:gpu -f docker/Dockerfile --target gpu .

# 构建 CPU 镜像
docker build -t uvr-headless:cpu -f docker/Dockerfile --target cpu .
```

### 使用 Docker Compose

```bash
cd docker

# GPU 模式
docker compose run --rm uvr uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/

# CPU 模式
docker compose --profile cpu run --rm uvr-cpu uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/
```

### 直接使用 Docker Run

```bash
# GPU 模式
docker run --rm -it --gpus all \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless:gpu \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/

# CPU 模式
docker run --rm -it \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless:cpu \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/
```

## 📚 命令参考

### uvr-mdx (MDX-Net/Roformer)

```bash
# 基本用法
uvr-mdx -m <模型名称> -i <输入文件> -o <输出目录>

# 常用选项
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/ --gpu
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/ --vocals-only
uvr-mdx -m "model.ckpt" --json config.yaml -i song.wav -o output/

# 模型管理
uvr-mdx --list              # 列出所有可用模型
uvr-mdx --list-installed    # 列出已安装模型
uvr-mdx --download "UVR-MDX-NET Inst HQ 3"  # 下载模型
uvr-mdx --model-info "UVR-MDX-NET Inst HQ 3"  # 查看模型信息

# 高级选项
uvr-mdx -m <model> -i <input> -o <output> \
  --segment-size 256 \
  --overlap 0.25 \
  --batch-size 1 \
  --wav-type PCM_24
```

### uvr-demucs (Demucs)

```bash
# 基本用法
uvr-demucs -m <模型名称> -i <输入文件> -o <输出目录>

# 常用选项
uvr-demucs -m htdemucs -i song.wav -o output/ --gpu
uvr-demucs -m htdemucs_ft -i song.wav -o output/ --stem Vocals
uvr-demucs -m htdemucs_6s -i song.wav -o output/  # 6-stem 模型

# 模型管理
uvr-demucs --list
uvr-demucs --download "htdemucs_ft"

# 高级选项
uvr-demucs -m <model> -i <input> -o <output> \
  --shifts 2 \
  --overlap 0.25 \
  --segment Default
```

### uvr-vr (VR Architecture)

```bash
# 基本用法
uvr-vr -m <模型名称> -i <输入文件> -o <输出目录>

# 常用选项
uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/ --gpu
uvr-vr -m "UVR-De-Echo-Aggressive" -i song.wav -o output/ --tta

# 模型管理
uvr-vr --list
uvr-vr --download "UVR-De-Echo-Normal"

# 高级选项
uvr-vr -m <model> -i <input> -o <output> \
  --window-size 512 \
  --aggression 5 \
  --tta \
  --post-process
```

### uvr (统一入口)

```bash
# 子命令
uvr mdx ...      # 等同于 uvr-mdx
uvr demucs ...   # 等同于 uvr-demucs
uvr vr ...       # 等同于 uvr-vr

# 实用命令
uvr list [mdx|demucs|vr|all]  # 列出模型
uvr download <model> --arch <mdx|demucs|vr>  # 下载模型
uvr info         # 显示系统信息
uvr help         # 显示帮助
```

## 🗂️ 模型缓存

模型默认缓存在 `~/.uvr_models` 目录：

```
~/.uvr_models/
├── VR_Models/           # VR 架构模型 (.pth)
│   └── model_data/      # 模型元数据
├── MDX_Net_Models/      # MDX-Net 模型 (.onnx, .ckpt)
│   └── model_data/      # 模型元数据和配置
│       └── mdx_c_configs/  # Roformer/MDX-C 配置
└── Demucs_Models/       # Demucs 模型
    └── v3_v4_repo/      # v3/v4 模型文件
```

### 预下载模型

```bash
# 下载常用模型
uvr-mdx --download "UVR-MDX-NET Inst HQ 3"
uvr-mdx --download "UVR-MDX-NET Inst HQ 3"
uvr-demucs --download "htdemucs"
uvr-demucs --download "htdemucs_ft"
uvr-vr --download "UVR-De-Echo-Normal"
```

### 使用自定义模型目录

```bash
# 设置环境变量
export UVR_MODELS_DIR=/path/to/your/models

# 或在运行时指定
UVR_MODELS_DIR=/path/to/models uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
```

## 🖥️ GPU 支持

> ⚠️ **重要限制**
> 
> Docker 版本**不支持 AMD DirectML**。DirectML 是 Windows 专用 API，无法在 Linux 容器中运行。
> 
> | GPU 平台 | 原生安装 | Docker |
> |----------|----------|--------|
> | NVIDIA CUDA | ✅ | ✅ |
> | AMD DirectML | ✅ | ❌ 不支持 |
> 
> 如果你需要 AMD GPU 加速，请使用原生安装方式，或等待 ROCm 支持。

### NVIDIA GPU 要求

- NVIDIA 驱动 525.60.13+
- CUDA 12.x 兼容 GPU
- nvidia-container-toolkit

### 安装 nvidia-container-toolkit

**Ubuntu/Debian:**
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

**Windows:**
- Docker Desktop 会自动支持 NVIDIA GPU
- 确保安装了最新的 NVIDIA 驱动

### 验证 GPU 支持

```bash
# 检查 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

# 检查 UVR GPU 支持
uvr info
```

## 🔍 故障排除

### 常见问题

**1. "CUDA out of memory" 错误**
```bash
# 减小批处理大小
uvr-mdx -m <model> -i <input> -o <output> --batch-size 1 --segment-size 128

# 或使用 CPU 模式
uvr-mdx -m <model> -i <input> -o <output> --cpu
```

**2. 模型下载失败**
```bash
# 检查网络连接
curl -I https://github.com/TRvlvr/model_repo/releases

# 手动下载并放入模型目录
# 模型 URL 可通过 --model-info 查看
uvr-mdx --model-info "UVR-MDX-NET Inst HQ 3"
```

**3. 找不到命令**
```bash
# 重新运行安装脚本
./docker/install.sh

# 或手动添加到 PATH
export PATH="$PATH:/usr/local/bin"
```

**4. Docker 权限问题**
```bash
# 添加用户到 docker 组
sudo usermod -aG docker $USER
# 重新登录或运行
newgrp docker
```

### 查看日志

```bash
# 启用详细输出
uvr-mdx -m <model> -i <input> -o <output>  # 默认详细模式

# 静默模式
uvr-mdx -m <model> -i <input> -o <output> --quiet
```

## 🗑️ 卸载

```bash
# Linux/macOS
./docker/install.sh --uninstall

# Windows
.\docker\install.ps1 -Uninstall

# 删除 Docker 镜像
docker rmi uvr-headless:gpu uvr-headless:cpu

# 删除模型缓存
rm -rf ~/.uvr_models
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🔗 相关链接

- [Ultimate Vocal Remover GUI](https://github.com/Anjok07/ultimatevocalremovergui)
- [UVR 模型仓库](https://github.com/TRvlvr/model_repo)
- [Docker 官方文档](https://docs.docker.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
