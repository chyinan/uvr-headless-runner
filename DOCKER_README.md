# UVR Headless Runner - Docker Deployment Guide

> 🎵 Production-grade containerized audio source separation

## 📋 Overview

This project provides a Docker deployment solution for Ultimate Vocal Remover (UVR), featuring:

- **Three Architectures**: MDX-Net/Roformer, Demucs, VR Architecture
- **GPU Acceleration**: NVIDIA CUDA 12.x support
- **CPU Fallback**: Automatic detection and fallback to CPU mode
- **Native CLI Experience**: No manual `docker run` commands required
- **Model Persistence**: Automatic model caching to avoid re-downloads

## 🚀 Quick Start

### Prerequisites

- Docker 20.10+
- (Optional) NVIDIA GPU + nvidia-container-toolkit (for GPU acceleration)

### One-Click Installation

**Linux/macOS:**
```bash
# Auto-detect GPU support
./docker/install.sh

# Or force specific mode
./docker/install.sh --gpu   # GPU mode
./docker/install.sh --cpu   # CPU mode
```

**Windows (PowerShell):**
```powershell
# Auto-detect GPU support
.\docker\install.ps1

# Or force specific mode
.\docker\install.ps1 -Gpu   # GPU mode
.\docker\install.ps1 -Cpu   # CPU mode
```

### Usage Examples

After installation, you can use UVR like native commands:

```bash
# MDX-Net/Roformer separation
uvr-mdx -m "Kim Vocal 2" -i song.wav -o output/

# Demucs separation
uvr-demucs -m htdemucs -i song.wav -o output/

# VR Architecture separation
uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/

# Unified entry point
uvr mdx -m "Kim Vocal 2" -i song.wav -o output/
uvr demucs -m htdemucs -i song.wav -o output/
uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
```

## 📦 Project Structure

```
docker/
├── Dockerfile           # Multi-stage build (CPU + GPU)
├── docker-compose.yml   # Docker Compose configuration
├── entrypoint.sh        # Container entrypoint script
├── install.sh           # Linux/macOS installation script
├── install.ps1          # Windows installation script
└── bin/
    ├── uvr              # Unified CLI entry point
    ├── uvr-mdx          # MDX-Net dedicated CLI
    ├── uvr-demucs       # Demucs dedicated CLI
    └── uvr-vr           # VR Architecture dedicated CLI
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UVR_MODELS_DIR` | `~/.uvr_models` | Model cache directory |
| `UVR_DEVICE` | Auto-detect | Force device (`cuda`/`cpu`) |
| `UVR_INSTALL_DIR` | `/usr/local/bin` | CLI installation directory |

### Manual Image Build

```bash
# Build GPU image
docker build -t uvr-headless:gpu -f docker/Dockerfile --target gpu .

# Build CPU image
docker build -t uvr-headless:cpu -f docker/Dockerfile --target cpu .
```

### Using Docker Compose

```bash
cd docker

# GPU mode
docker compose run --rm uvr uvr-mdx -m "Kim Vocal 2" -i /input/song.wav -o /output/

# CPU mode
docker compose --profile cpu run --rm uvr-cpu uvr-mdx -m "Kim Vocal 2" -i /input/song.wav -o /output/
```

### Direct Docker Run

```bash
# GPU mode
docker run --rm -it --gpus all \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless:gpu \
  uvr-mdx -m "Kim Vocal 2" -i /input/song.wav -o /output/

# CPU mode
docker run --rm -it \
  -v ~/.uvr_models:/models \
  -v $(pwd)/input:/input:ro \
  -v $(pwd)/output:/output \
  uvr-headless:cpu \
  uvr-mdx -m "Kim Vocal 2" -i /input/song.wav -o /output/
```

## 📚 Command Reference

### uvr-mdx (MDX-Net/Roformer)

```bash
# Basic usage
uvr-mdx -m <model_name> -i <input_file> -o <output_dir>

# Common options
uvr-mdx -m "Kim Vocal 2" -i song.wav -o output/ --gpu
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/ --vocals-only
uvr-mdx -m "model.ckpt" --json config.yaml -i song.wav -o output/

# Model management
uvr-mdx --list              # List all available models
uvr-mdx --list-installed    # List installed models
uvr-mdx --download "Kim Vocal 2"  # Download a model
uvr-mdx --model-info "Kim Vocal 2"  # Show model info

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
uvr-mdx --download "Kim Vocal 2"
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
UVR_MODELS_DIR=/path/to/models uvr-mdx -m "Kim Vocal 2" -i song.wav -o output/
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

- NVIDIA Driver 525.60.13+
- CUDA 12.x compatible GPU
- nvidia-container-toolkit

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
uvr-mdx --model-info "Kim Vocal 2"
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
.\docker\install.ps1 -Uninstall

# Remove Docker images
docker rmi uvr-headless:gpu uvr-headless:cpu

# Remove model cache
rm -rf ~/.uvr_models
```

## 📊 Performance Comparison

| Mode | 3-minute Audio Processing Time | VRAM Usage |
|------|--------------------------------|------------|
| GPU (RTX 3080) | ~15s | ~4GB |
| GPU (RTX 4090) | ~8s | ~4GB |
| CPU (i7-12700) | ~3min | N/A |

## 🤝 Contributing

Issues and Pull Requests are welcome!

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 🔗 Related Links

- [Ultimate Vocal Remover GUI](https://github.com/Anjok07/ultimatevocalremovergui)
- [UVR Model Repository](https://github.com/TRvlvr/model_repo)
- [Docker Documentation](https://docs.docker.com/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
