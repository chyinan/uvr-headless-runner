# UVR Headless Runner - Docker 部署指南

> 🎵 专业级音频源分离工具的容器化部署方案

## 📋 概述

本项目提供了 Ultimate Vocal Remover (UVR) 的 Docker 化部署方案，支持：

- **三种架构**: MDX-Net/Roformer, Demucs, VR Architecture
- **GPU 加速**: NVIDIA CUDA 12.x 支持，可选版本 (12.1/12.4/12.8)
- **CPU 回退**: 自动检测并回退到 CPU 模式
- **原生 CLI 体验**: 无需手动输入 `docker run` 命令
- **模型持久化**: 模型自动缓存，避免重复下载
- **代理支持**: 自动 HTTP/HTTPS 代理透传，适合企业网络
- **供应链安全**: 所有 Python 包均经过 SHA256 哈希验证

## 🚀 快速开始

### 前置要求

- Docker 20.10+
- (可选) NVIDIA GPU + nvidia-container-toolkit (用于 GPU 加速)

### 一键安装

**Linux/macOS:**
```bash
# 自动检测 GPU 支持 (默认 CUDA 12.4)
./docker/install.sh

# 强制指定模式
./docker/install.sh --gpu   # GPU 模式 (CUDA 12.4)
./docker/install.sh --cpu   # CPU 模式

# 指定 CUDA 版本 (根据驱动版本选择)
./docker/install.sh --cuda cu121   # CUDA 12.1, 驱动 530+
./docker/install.sh --cuda cu124   # CUDA 12.4, 驱动 550+ (默认)
./docker/install.sh --cuda cu128   # CUDA 12.8, 驱动 560+
```

**Windows (双击或命令行):**

> 💡 推荐使用 `install.bat`。该批处理脚本会自动以 `Bypass` 执行策略启动 PowerShell，**无需手动修改系统执行策略**，避免了 `install.ps1` 直接运行时常见的 "无法加载文件...未对文件进行数字签名" 权限错误。

```bat
REM 双击 docker\install.bat 即可，或在命令行中运行：

REM 自动检测 GPU 支持 (默认 CUDA 12.4)
docker\install.bat

REM 强制指定模式
docker\install.bat -Gpu   REM GPU 模式 (CUDA 12.4)
docker\install.bat -Cpu   REM CPU 模式

REM 指定 CUDA 版本
docker\install.bat -Cuda cu121   REM CUDA 12.1, 驱动 530+
docker\install.bat -Cuda cu124   REM CUDA 12.4, 驱动 550+ (默认)
docker\install.bat -Cuda cu128   REM CUDA 12.8, 驱动 560+
```

<details>
<summary>如果你已配置 PowerShell 执行策略，也可以直接运行 .ps1</summary>

```powershell
.\docker\install.ps1
.\docker\install.ps1 -Gpu
.\docker\install.ps1 -Cpu
.\docker\install.ps1 -Cuda cu121
```

</details>

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

> 💡 **原生 Python 环境也支持相同命令！** 通过 `pip install uvr-headless-runner` 安装后，`uvr mdx` / `uvr demucs` / `uvr vr` 等统一命令同样可用，体验与 Docker 版一致。

## 📦 项目结构

```
docker/
├── Dockerfile           # 多阶段构建 (CPU + GPU)
├── docker-compose.yml   # Docker Compose 配置
├── entrypoint.sh        # 容器入口脚本
├── install.sh           # Linux/macOS 安装脚本
├── install.bat          # Windows 安装脚本 (推荐，自动绕过执行策略)
├── install.ps1          # Windows 安装脚本 (PowerShell 核心逻辑)
└── bin/
    ├── uvr              # 统一 CLI 入口
    ├── uvr-mdx          # MDX-Net 专用 CLI
    ├── uvr-demucs       # Demucs 专用 CLI
    └── uvr-vr           # VR Architecture 专用 CLI
```

## 🔧 详细配置

### 环境变量

#### 核心设置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UVR_MODELS_DIR` | `~/.uvr_models` | 模型缓存目录 |
| `UVR_DEVICE` | 自动检测 | 强制指定设备 (`cuda`/`cpu`) |
| `UVR_INSTALL_DIR` | `/usr/local/bin` | CLI 安装目录 |
| `UVR_CUDA_VERSION` | `cu124` | CUDA 版本 (`cu121`/`cu124`/`cu128`) |
| `UVR_DEBUG` | - | 设为 `1` 显示调试输出 |

#### 资源限制 (Docker Compose)

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `UVR_MEMORY_LIMIT` | `16G` | 容器最大内存 |
| `UVR_MEMORY_RESERVATION` | `4G` | 容器保留内存 |

#### HTTP/HTTPS 代理 (自动透传)

| 变量 | 说明 |
|------|------|
| `HTTP_PROXY` / `http_proxy` | HTTP 代理 URL (如 `http://proxy:8080`) |
| `HTTPS_PROXY` / `https_proxy` | HTTPS 代理 URL |
| `NO_PROXY` / `no_proxy` | 绕过代理的主机列表 (逗号分隔) |

> **说明**: 代理设置会自动传递到容器中，无需手动配置。只需在主机环境中设置代理变量即可。

### 手动构建镜像

```bash
# 构建 GPU 镜像 (默认 CUDA 12.4)
docker build -t uvr-headless-runner:gpu -f docker/Dockerfile --target gpu .

# 构建 GPU 镜像并指定 CUDA 版本
docker build -t uvr-headless-runner:gpu-cu121 -f docker/Dockerfile --target gpu \
  --build-arg CUDA_VERSION=cu121 .

# 构建 CPU 镜像
docker build -t uvr-headless-runner:cpu -f docker/Dockerfile --target cpu .

# 通过代理构建 (企业网络)
docker build -t uvr-headless-runner:gpu -f docker/Dockerfile --target gpu \
  --build-arg HTTP_PROXY=http://proxy:8080 \
  --build-arg HTTPS_PROXY=http://proxy:8080 .
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
  uvr-headless-runner:gpu \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/

# CPU 模式
docker run --rm -it \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless-runner:cpu \
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

- nvidia-container-toolkit
- CUDA 12.x 兼容 GPU
- 驱动版本要求取决于 CUDA 版本：

| CUDA 版本 | 构建参数 | 最低驱动 |
|-----------|----------|----------|
| CUDA 12.1 | `cu121` | 530+ |
| CUDA 12.4 | `cu124` (默认) | 550+ |
| CUDA 12.8 | `cu128` | 560+ |

> **提示**: 如果你的驱动较旧，安装时使用 `--cuda cu121` 参数。

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

## 🌐 HTTP/HTTPS 代理支持

对于企业网络或受限网络环境，UVR Docker 支持自动透传代理设置。

### 使用方法

代理环境变量会**自动检测并传递**到容器中。只需在 shell 中设置：

```bash
# 设置代理 (Linux/macOS)
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1,.company.com

# 正常使用 UVR - 代理会自动生效
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/

# 或为单个命令指定
HTTP_PROXY=http://proxy:8080 uvr mdx --list
```

**Windows (PowerShell):**
```powershell
# 设置代理
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"

# 正常使用 UVR
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
```

### Docker Compose 配合代理

```bash
# 代理会自动透传
export HTTP_PROXY=http://proxy:8080
docker compose build uvr   # 构建时使用代理
docker compose run --rm uvr uvr mdx --list  # 运行时使用代理
```

### 直接 Docker Run 配合代理

```bash
docker run --rm -it \
  -e HTTP_PROXY=http://proxy:8080 \
  -e HTTPS_PROXY=http://proxy:8080 \
  uvr-headless-runner:gpu uvr info
```

> **安全说明**: 代理 URL 可能包含凭据。它们会传递到容器中，但故意不会出现在调试日志中，以防止意外泄露。

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

**5. 代理环境下模型下载失败**
```bash
# 确保设置了代理变量
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080

# 验证代理是否生效
uvr info  # 应显示 "Proxy: configured"

# 测试通过代理的连接
curl -x http://proxy:8080 -I https://github.com
```

**6. 代理环境下构建失败**
```bash
# 将代理传递给构建命令
docker build \
  --build-arg HTTP_PROXY=http://proxy:8080 \
  --build-arg HTTPS_PROXY=http://proxy:8080 \
  -t uvr-headless-runner:gpu -f docker/Dockerfile --target gpu .
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
docker\install.bat -Uninstall

# 删除 Docker 镜像
docker rmi uvr-headless-runner:gpu uvr-headless-runner:cpu

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
