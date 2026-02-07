# UVR Headless Runner - Docker Deployment Guide

> 🎵 Production-grade containerized audio source separation

## 📋 Overview

This project provides a Docker deployment solution for Ultimate Vocal Remover (UVR), featuring:

- **Three Architectures**: MDX-Net/Roformer, Demucs, VR Architecture
- **GPU Acceleration**: NVIDIA CUDA 12.x support with selectable versions (12.1/12.4/12.8)
- **CPU Fallback**: Automatic detection and fallback to CPU mode
- **Native CLI Experience**: No manual `docker run` commands required
- **Model Persistence**: Automatic model caching to avoid re-downloads
- **Proxy Support**: Automatic HTTP/HTTPS proxy passthrough for corporate networks
- **Supply Chain Security**: pip hash verification for all Python packages

## 🚀 Quick Start

### Prerequisites

- Docker 20.10+
- (Optional) NVIDIA GPU + nvidia-container-toolkit (for GPU acceleration)

### One-Click Installation

**Linux/macOS:**
```bash
# Auto-detect GPU support (default CUDA 12.4)
./docker/install.sh

# Force specific mode
./docker/install.sh --gpu   # GPU mode (CUDA 12.4)
./docker/install.sh --cpu   # CPU mode

# Specify CUDA version (for different driver compatibility)
./docker/install.sh --cuda cu121   # CUDA 12.1, driver 530+
./docker/install.sh --cuda cu124   # CUDA 12.4, driver 550+ (default)
./docker/install.sh --cuda cu128   # CUDA 12.8, driver 560+
```

**Windows (double-click or command line):**

> 💡 We recommend using `install.bat`. This batch script automatically launches PowerShell with `Bypass` execution policy, so you **don't need to modify system execution policies manually** — avoiding the common "cannot be loaded because running scripts is disabled" error when running `install.ps1` directly.

```bat
REM Double-click docker\install.bat, or run from the command line:

REM Auto-detect GPU support (default CUDA 12.4)
docker\install.bat

REM Force specific mode
docker\install.bat -Gpu   REM GPU mode (CUDA 12.4)
docker\install.bat -Cpu   REM CPU mode

REM Specify CUDA version
docker\install.bat -Cuda cu121   REM CUDA 12.1, driver 530+
docker\install.bat -Cuda cu124   REM CUDA 12.4, driver 550+ (default)
docker\install.bat -Cuda cu128   REM CUDA 12.8, driver 560+
```

<details>
<summary>If you've already configured PowerShell execution policy, you can also run .ps1 directly</summary>

```powershell
.\docker\install.ps1
.\docker\install.ps1 -Gpu
.\docker\install.ps1 -Cpu
.\docker\install.ps1 -Cuda cu121
```

</details>

### Usage Examples

After installation, you can use UVR like native commands:

```bash
# MDX-Net/Roformer separation
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/

# Demucs separation
uvr-demucs -m htdemucs -i song.wav -o output/

# VR Architecture separation
uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/

# Unified entry point
uvr mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
uvr demucs -m htdemucs -i song.wav -o output/
uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
```

> 💡 **Native Python also supports the same commands!** After `pip install uvr-headless-runner`, the unified `uvr mdx` / `uvr demucs` / `uvr vr` commands work identically to the Docker version.

## 📦 Project Structure

```
docker/
├── Dockerfile           # Multi-stage build (CPU + GPU)
├── docker-compose.yml   # Docker Compose configuration
├── entrypoint.sh        # Container entrypoint script
├── install.sh           # Linux/macOS installation script
├── install.bat          # Windows installation script (recommended, auto-bypasses execution policy)
├── install.ps1          # Windows installation script (PowerShell core logic)
└── bin/
    ├── uvr              # Unified CLI entry point
    ├── uvr-mdx          # MDX-Net dedicated CLI
    ├── uvr-demucs       # Demucs dedicated CLI
    └── uvr-vr           # VR Architecture dedicated CLI
```

## 🔧 Configuration

### Environment Variables

#### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `UVR_MODELS_DIR` | `~/.uvr_models` | Model cache directory |
| `UVR_DEVICE` | Auto-detect | Force device (`cuda`/`cpu`) |
| `UVR_INSTALL_DIR` | `/usr/local/bin` | CLI installation directory |
| `UVR_CUDA_VERSION` | `cu124` | CUDA version (`cu121`/`cu124`/`cu128`) |
| `UVR_DEBUG` | - | Set to `1` to show debug output |

#### Resource Limits (Docker Compose)

| Variable | Default | Description |
|----------|---------|-------------|
| `UVR_MEMORY_LIMIT` | `16G` | Maximum memory for container |
| `UVR_MEMORY_RESERVATION` | `4G` | Reserved memory for container |

#### HTTP/HTTPS Proxy (Auto-passthrough)

| Variable | Description |
|----------|-------------|
| `HTTP_PROXY` / `http_proxy` | HTTP proxy URL (e.g., `http://proxy:8080`) |
| `HTTPS_PROXY` / `https_proxy` | HTTPS proxy URL |
| `NO_PROXY` / `no_proxy` | Hosts to bypass proxy (comma-separated) |

> **Note**: Proxy settings are automatically passed through to the container when set in your environment. No manual configuration needed.

### Manual Image Build

```bash
# Build GPU image (default CUDA 12.4)
docker build -t uvr-headless-runner:gpu -f docker/Dockerfile --target gpu .

# Build GPU image with specific CUDA version
docker build -t uvr-headless-runner:gpu-cu121 -f docker/Dockerfile --target gpu \
  --build-arg CUDA_VERSION=cu121 .

# Build CPU image
docker build -t uvr-headless-runner:cpu -f docker/Dockerfile --target cpu .

# Build with HTTP proxy (for corporate networks)
docker build -t uvr-headless-runner:gpu -f docker/Dockerfile --target gpu \
  --build-arg HTTP_PROXY=http://proxy:8080 \
  --build-arg HTTPS_PROXY=http://proxy:8080 .
```

### Using Docker Compose

```bash
cd docker

# GPU mode
docker compose run --rm uvr uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/

# CPU mode
docker compose --profile cpu run --rm uvr-cpu uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/
```

### Direct Docker Run

```bash
# GPU mode
docker run --rm -it --gpus all \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless-runner:gpu \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/

# CPU mode
docker run --rm -it \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless-runner:cpu \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /input/song.wav -o /output/
```

## 📚 Command Reference

### uvr-mdx (MDX-Net/Roformer)

```bash
# Basic usage
uvr-mdx -m <model_name> -i <input_file> -o <output_dir>

# Common options
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/ --gpu
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/ --vocals-only
uvr-mdx -m "model.ckpt" --json config.yaml -i song.wav -o output/

# Model management
uvr-mdx --list              # List all available models
uvr-mdx --list-installed    # List installed models
uvr-mdx --download "UVR-MDX-NET Inst HQ 3"  # Download a model
uvr-mdx --model-info "UVR-MDX-NET Inst HQ 3"  # Show model info

# Advanced options
uvr-mdx -m <model> -i <input> -o <output> \
  --segment-size 256 \
  --overlap 0.25 \
  --batch-size 1 \
  --wav-type PCM_24
```

### uvr-demucs (Demucs)

```bash
# Basic usage
uvr-demucs -m <model_name> -i <input_file> -o <output_dir>

# Common options
uvr-demucs -m htdemucs -i song.wav -o output/ --gpu
uvr-demucs -m htdemucs_ft -i song.wav -o output/ --stem Vocals
uvr-demucs -m htdemucs_6s -i song.wav -o output/  # 6-stem model

# Model management
uvr-demucs --list
uvr-demucs --download "htdemucs_ft"

# Advanced options
uvr-demucs -m <model> -i <input> -o <output> \
  --shifts 2 \
  --overlap 0.25 \
  --segment Default
```

### uvr-vr (VR Architecture)

```bash
# Basic usage
uvr-vr -m <model_name> -i <input_file> -o <output_dir>

# Common options
uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/ --gpu
uvr-vr -m "UVR-De-Echo-Aggressive" -i song.wav -o output/ --tta

# Model management
uvr-vr --list
uvr-vr --download "UVR-De-Echo-Normal"

# Advanced options
uvr-vr -m <model> -i <input> -o <output> \
  --window-size 512 \
  --aggression 5 \
  --tta \
  --post-process
```

### uvr (Unified Entry Point)

```bash
# Subcommands
uvr mdx ...      # Same as uvr-mdx
uvr demucs ...   # Same as uvr-demucs
uvr vr ...       # Same as uvr-vr

# Utility commands
uvr list [mdx|demucs|vr|all]  # List models
uvr download <model> --arch <mdx|demucs|vr>  # Download model
uvr info         # Show system information
uvr help         # Show help
```

## 🗂️ Model Cache

Models are cached in `~/.uvr_models` by default:

```
~/.uvr_models/
├── VR_Models/           # VR architecture models (.pth)
│   └── model_data/      # Model metadata
├── MDX_Net_Models/      # MDX-Net models (.onnx, .ckpt)
│   └── model_data/      # Model metadata and configs
│       └── mdx_c_configs/  # Roformer/MDX-C configs
└── Demucs_Models/       # Demucs models
    └── v3_v4_repo/      # v3/v4 model files
```

### Pre-download Models

```bash
# Download commonly used models
uvr-mdx --download "UVR-MDX-NET Inst HQ 3"
uvr-mdx --download "UVR-MDX-NET Inst HQ 3"
uvr-demucs --download "htdemucs"
uvr-demucs --download "htdemucs_ft"
uvr-vr --download "UVR-De-Echo-Normal"
```

### Custom Model Directory

```bash
# Set environment variable
export UVR_MODELS_DIR=/path/to/your/models

# Or specify at runtime
UVR_MODELS_DIR=/path/to/models uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
```

## 🖥️ GPU Support

> ⚠️ **Important Limitation**
> 
> The Docker version **does NOT support AMD DirectML**. DirectML is a Windows-only API and cannot run in Linux containers.
> 
> | GPU Platform | Native | Docker |
> |--------------|--------|--------|
> | NVIDIA CUDA | ✅ | ✅ |
> | AMD DirectML | ✅ | ❌ Not supported |
> 
> If you need AMD GPU acceleration, please use the native installation method or wait for ROCm support.

### NVIDIA GPU Requirements

- nvidia-container-toolkit
- CUDA 12.x compatible GPU
- Driver version depends on CUDA version:

| CUDA Version | Build Arg | Min Driver |
|--------------|-----------|------------|
| CUDA 12.1 | `cu121` | 530+ |
| CUDA 12.4 | `cu124` (default) | 550+ |
| CUDA 12.8 | `cu128` | 560+ |

> **Tip**: If you have an older driver, use `--cuda cu121` during installation.

### Installing nvidia-container-toolkit

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
- Docker Desktop automatically supports NVIDIA GPU
- Ensure latest NVIDIA drivers are installed

### Verify GPU Support

```bash
# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

# Check UVR GPU support
uvr info
```

## 🌐 HTTP/HTTPS Proxy Support

For corporate networks or restricted environments, UVR Docker automatically passes through proxy settings.

### Usage

Proxy environment variables are **automatically detected and passed** to the container. Just set them in your shell:

```bash
# Set proxy (Linux/macOS)
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1,.company.com

# Now use UVR normally - proxy is automatically used
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/

# Or specify inline for a single command
HTTP_PROXY=http://proxy:8080 uvr mdx --list
```

**Windows (PowerShell):**
```powershell
# Set proxy
$env:HTTP_PROXY = "http://proxy.company.com:8080"
$env:HTTPS_PROXY = "http://proxy.company.com:8080"

# Use UVR normally
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
```

### Docker Compose with Proxy

```bash
# Proxy is automatically passed through
export HTTP_PROXY=http://proxy:8080
docker compose build uvr   # Build uses proxy
docker compose run --rm uvr uvr mdx --list  # Runtime uses proxy
```

### Direct Docker Run with Proxy

```bash
docker run --rm -it \
  -e HTTP_PROXY=http://proxy:8080 \
  -e HTTPS_PROXY=http://proxy:8080 \
  uvr-headless-runner:gpu uvr info
```

> **Security Note**: Proxy URLs may contain credentials. They are passed to the container but intentionally excluded from debug logs to prevent accidental exposure.

## 🔍 Troubleshooting

### Common Issues

**1. "CUDA out of memory" Error**
```bash
# Reduce batch size
uvr-mdx -m <model> -i <input> -o <output> --batch-size 1 --segment-size 128

# Or use CPU mode
uvr-mdx -m <model> -i <input> -o <output> --cpu
```

**2. Model Download Failed**
```bash
# Check network connectivity
curl -I https://github.com/TRvlvr/model_repo/releases

# Manually download and place in model directory
# Model URL can be found via --model-info
uvr-mdx --model-info "UVR-MDX-NET Inst HQ 3"
```

**3. Command Not Found**
```bash
# Re-run installation script
./docker/install.sh

# Or manually add to PATH
export PATH="$PATH:/usr/local/bin"
```

**4. Docker Permission Issues**
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Re-login or run
newgrp docker
```

**5. Model Download Failed Behind Proxy**
```bash
# Ensure proxy variables are set
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080

# Verify proxy is being used
uvr info  # Should show "Proxy: configured"

# Test connectivity through proxy
curl -x http://proxy:8080 -I https://github.com
```

**6. Build Failed Behind Proxy**
```bash
# Pass proxy to build command
docker build \
  --build-arg HTTP_PROXY=http://proxy:8080 \
  --build-arg HTTPS_PROXY=http://proxy:8080 \
  -t uvr-headless-runner:gpu -f docker/Dockerfile --target gpu .
```

### Viewing Logs

```bash
# Enable verbose output
uvr-mdx -m <model> -i <input> -o <output>  # Verbose by default

# Quiet mode
uvr-mdx -m <model> -i <input> -o <output> --quiet
```

## 🗑️ Uninstallation

```bash
# Linux/macOS
./docker/install.sh --uninstall

# Windows
docker\install.bat -Uninstall

# Remove Docker images
docker rmi uvr-headless-runner:gpu uvr-headless-runner:cpu

# Remove model cache
rm -rf ~/.uvr_models
```

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 🔗 Related Links

- [Ultimate Vocal Remover GUI](https://github.com/Anjok07/ultimatevocalremovergui)
- [UVR Model Repository](https://github.com/TRvlvr/model_repo)
- [Docker Documentation](https://docs.docker.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
