<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=28&duration=3000&pause=1000&color=A78BFA&center=true&vCenter=true&width=500&lines=%F0%9F%8E%B5+UVR+Headless+Runner;Audio+Source+Separation+CLI">
    <img alt="UVR Headless Runner" src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=28&duration=3000&pause=1000&color=7C3AED&center=true&vCenter=true&width=500&lines=%F0%9F%8E%B5+UVR+Headless+Runner;Audio+Source+Separation+CLI">
  </picture>
</p>

<h3 align="center">🎧 Separate vocals, instruments, drums, bass & more from any audio</h3>

<p align="center">
  <strong>Command-line audio source separation powered by UVR</strong>
</p>

<p align="center">
  <a href="https://github.com/chyinan/uvr-headless-runner/blob/master/LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT">
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.9+-green.svg" alt="Python 3.9+">
  </a>
  <a href="https://pytorch.org/">
    <img src="https://img.shields.io/badge/PyTorch-2.0+-ee4c2c.svg" alt="PyTorch">
  </a>
  <a href="https://github.com/chyinan/uvr-headless-runner">
    <img src="https://img.shields.io/badge/platform-Windows%20|%20Linux%20|%20macOS-lightgrey.svg" alt="Platform">
  </a>
  <a href="https://pypi.org/project/uvr-headless-runner/">
    <img src="https://img.shields.io/pypi/v/uvr-headless-runner.svg?color=blue" alt="PyPI">
  </a>
</p>

<p align="center">
  <a href="README_CN.md">🇨🇳 中文</a> | <strong>🇬🇧 English</strong> | <a href="DOCKER_README.md">🐳 Docker</a>
</p>

---

## ✨ Features

<table>
<tr>
<td width="33%">

### 🎸 MDX-Net Runner
- MDX-Net / MDX-C models
- **Roformer** (MelBandRoformer, BSRoformer)
- **SCNet** (Sparse Compression Network)
- ONNX & PyTorch checkpoints

</td>
<td width="33%">

### 🥁 Demucs Runner
- Demucs v1 / v2 / v3 / v4
- **htdemucs** / **htdemucs_ft**
- **6-stem separation** (Guitar, Piano)
- Auto model download

</td>
<td width="33%">

### 🎤 VR Runner
- VR Architecture models
- **VR 5.1** model support
- Window size / Aggression tuning
- TTA & Post-processing

</td>
</tr>
</table>

### 🚀 Highlights

<table>
<tr>
<th width="50%">Feature</th>
<th width="50%">Description</th>
</tr>
<tr><td>🎯 <b>GUI-Identical</b></td><td>Exactly replicates UVR GUI behavior</td></tr>
<tr><td>⚡ <b>GPU Accelerated</b></td><td>NVIDIA CUDA & AMD DirectML support</td></tr>
<tr><td>🔧 <b>Zero Config</b></td><td>Auto-detect model parameters</td></tr>
<tr><td>📦 <b>Batch Ready</b></td><td>Perfect for automation & pipelines</td></tr>
<tr><td>🎚️ <b>Bit Depth Control</b></td><td>16/24/32-bit PCM, 32/64-bit float</td></tr>
<tr><td>📥 <b>Auto Download</b></td><td>Official UVR model registry with auto-download</td></tr>
<tr><td>🛡️ <b>Robust Error Handling</b></td><td>GPU fallback, retry, fuzzy matching</td></tr>
<tr><td>🔗 <b>Unified CLI</b></td><td><code>uvr mdx</code> / <code>uvr demucs</code> / <code>uvr vr</code> — one command for all</td></tr>
<tr><td>📦 <b>PyPI Ready</b></td><td><code>pip install uvr-headless-runner</code> — instant setup</td></tr>
</table>

---

## 📖 Design Philosophy

> <img src="https://img.shields.io/badge/IMPORTANT-red?style=flat-square" alt="Important"/>
> 
> **This project is a headless automation layer for [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui).**
> 
> It does **NOT** reimplement any separation logic.  
> It **EXACTLY REPLICATES** UVR GUI behavior — model loading, parameter fallback, and auto-detection.
> 
> **✅ If a model works in UVR GUI, it works here — no extra config needed.**

---

## 🤔 Why uvr-headless-runner?

> Built for maximum flexibility. Load any custom model without waiting for upstream updates.

<table>
<tr>
<td width="33%" align="center">

### 🎨 Full Custom Model Support

Directly load any `.pth` or `.ckpt` file.  
**Perfect for testing new finetunes or experimental models immediately.**

</td>
<td width="33%" align="center">

### 🖥️ Headless & Remote Ready

Built for seamless integration into  
**web services or automation scripts.**

</td>
<td width="33%" align="center">

### 👥 By Users, For Users

Designed by audio enthusiasts who  
**prioritize complete control and native UVR compatibility.**

</td>
</tr>
</table>

---

## 📋 Requirements

| Component | Requirement |
|-----------|-------------|
| **Python** | 3.9.x (3.10+ not fully tested) |
| **GPU** | NVIDIA CUDA or AMD DirectML *(optional)* |
| **OS** | Windows / Linux / macOS |

---

## 🔧 Installation

<details open>
<summary><b>🚀 Option 1: pip install from PyPI (Recommended)</b></summary>

```bash
# Install from PyPI
pip install uvr-headless-runner

# GPU support (NVIDIA)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# ONNX GPU (optional)
pip install onnxruntime-gpu
```

After installation, you get the **`uvr` unified CLI** — no need to clone the repo!

```bash
uvr mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
uvr demucs -m htdemucs -i song.wav -o output/
uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
```

</details>

<details>
<summary><b>📦 Option 2: Poetry (from source)</b></summary>

```bash
# Clone repository
git clone https://github.com/chyinan/uvr-headless-runner.git
cd uvr-headless-runner

# Install dependencies
poetry install

# GPU support (NVIDIA)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# ONNX GPU (optional)
pip install onnxruntime-gpu
```

</details>

<details>
<summary><b>📦 Option 3: pip + venv (from source)</b></summary>

```bash
# Clone repository
git clone https://github.com/chyinan/uvr-headless-runner.git
cd uvr-headless-runner

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# GPU support (NVIDIA)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

</details>

<details>
<summary><b>🔴 AMD GPU (DirectML)</b></summary>

```bash
# Install DirectML support
pip install torch-directml

# Use with --directml flag
python mdx_headless_runner.py -m model.ckpt -i song.wav -o output/ --directml
```

> ⚠️ DirectML is experimental. NVIDIA CUDA recommended for best performance.

</details>

### ✅ Verify Installation (Native Python Only)

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

> 💡 Skip this if using Docker - the container includes all dependencies.

<details>
<summary><b>🐳 Option 4: Docker Hub (No Build Required!)</b></summary>

**Fastest way to get started - just pull and run!**

```bash
# Pull pre-built image from Docker Hub
docker pull chyinan/uvr-headless-runner:latest

# Run directly (GPU mode)
docker run --rm --gpus all \
  -v ~/.uvr_models:/models \
  -v $(pwd):/data \
  chyinan/uvr-headless-runner:latest \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /data/song.wav -o /data/output/

# Run directly (CPU mode)
docker run --rm \
  -v ~/.uvr_models:/models \
  -v $(pwd):/data \
  chyinan/uvr-headless-runner:latest \
  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i /data/song.wav -o /data/output/ --cpu
```

**Or install CLI wrappers for native experience:**

```bash
# One-click install (auto-detects GPU)
./docker/install.sh      # Linux/macOS
.\docker\install.ps1     # Windows

# Then use like native commands
uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
uvr-demucs -m htdemucs -i song.wav -o output/
uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
```

📖 **[Full Docker Guide →](DOCKER_README.md)**

</details>

---

## 🎼 Quick Start

### Unified CLI (pip install / Docker)

After installing via `pip install uvr-headless-runner` or Docker, you can use the **short commands**:

```bash
# MDX-Net / Roformer separation
uvr mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/ --gpu

# Demucs separation
uvr demucs -m htdemucs -i song.wav -o output/ --gpu

# VR Architecture separation
uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/ --gpu

# List all available models
uvr list all

# Download a model
uvr download "UVR-MDX-NET Inst HQ 3" --arch mdx

# Show system info
uvr info
```

> 💡 You can also use standalone commands: `uvr-mdx`, `uvr-demucs`, `uvr-vr`

### MDX-Net / Roformer / SCNet

```bash
# Basic separation
python mdx_headless_runner.py -m "model.ckpt" -i "song.flac" -o "output/" --gpu

# Vocals only (24-bit)
python mdx_headless_runner.py -m "model.ckpt" -i "song.flac" -o "output/" --gpu --vocals-only --wav-type PCM_24
```

### Demucs

```bash
# All 4 stems
python demucs_headless_runner.py --model htdemucs --input "song.flac" --output "output/" --gpu

# Vocals only
python demucs_headless_runner.py --model htdemucs --input "song.flac" --output "output/" --gpu --stem Vocals --primary-only
```

### VR Architecture

```bash
# Basic separation (model in database)
python vr_headless_runner.py -m "model.pth" -i "song.flac" -o "output/" --gpu

# Custom model (not in database)
python vr_headless_runner.py -m "model.pth" -i "song.flac" -o "output/" --gpu \
    --param 4band_v3 --primary-stem Vocals
```

---

## 📥 Model Download Center

All runners now include **automatic model downloading** from official UVR sources - just like the GUI!

### List Available Models

```bash
# List all MDX-Net models
python mdx_headless_runner.py --list

# List only installed models
python mdx_headless_runner.py --list-installed

# List models not yet downloaded
python mdx_headless_runner.py --list-uninstalled

# Same for Demucs and VR
python demucs_headless_runner.py --list
python vr_headless_runner.py --list
```

### Download Models

```bash
# Download a specific model (without running inference)
python mdx_headless_runner.py --download "UVR-MDX-NET Inst HQ 3"
python demucs_headless_runner.py --download "htdemucs_ft"
python vr_headless_runner.py --download "UVR-De-Echo-Normal by FoxJoy"
```

### Auto-Download on Inference

```bash
# Just use the model name - it will download automatically if not installed!
python mdx_headless_runner.py -m "UVR-MDX-NET Inst HQ 3" -i "song.flac" -o "output/" --gpu

# Demucs models auto-download too
python demucs_headless_runner.py --model htdemucs_ft --input "song.flac" --output "output/" --gpu
```

### Model Info & Fuzzy Matching

```bash
# Get detailed info about a model
python mdx_headless_runner.py --model-info "UVR-MDX-NET Inst HQ 3"

# Typo? Get suggestions!
python mdx_headless_runner.py --model-info "UVR-MDX Inst HQ"
# Output: Did you mean: UVR-MDX-NET Inst HQ 1, UVR-MDX-NET Inst HQ 2, ...
```

### Features

| Feature | Description |
|---------|-------------|
| 🌐 **Official Registry** | Syncs with UVR's official model list |
| 🔄 **Resume Downloads** | Interrupted downloads can be resumed |
| ⏱️ **Retry with Backoff** | Automatic retry on network errors |
| 💾 **Disk Space Check** | Pre-checks available space before download |
| 🔍 **Fuzzy Matching** | Suggests similar model names on typos |
| ✅ **Integrity Check** | Validates downloaded files |

---

## 🛡️ Error Handling & GPU Fallback

All runners include **robust error handling** with automatic GPU-to-CPU fallback:

```bash
# If GPU runs out of memory, automatically falls back to CPU
python mdx_headless_runner.py -m "model.ckpt" -i "song.flac" -o "output/" --gpu

# Output on GPU error:
# ============================================================
# ERROR: GPU memory exhausted
# ============================================================
# Suggestion: Try: (1) Use --cpu flag, (2) Reduce --batch-size...
#
# Attempting to fall back to CPU mode...
```

### Error Messages

Errors now include clear explanations and suggestions:

| Before | After |
|--------|-------|
| `FileNotFoundError` | `Audio file not found: song.wav` |
| `CUDA out of memory` | `GPU memory exhausted. Try: --cpu or reduce --batch-size` |
| `Model not found` | `Model 'xyz' not found. Did you mean: UVR-MDX-NET...?` |

---

## 📊 CLI Progress Display

All runners feature a **professional CLI progress system** with real-time feedback:

```
╭──────────────────────────────────────────────────────────────────────────╮
│                          UVR Audio Separation                            │
├──────────────────────────────────────────────────────────────────────────┤
│  Model         │ UVR-MDX-NET Inst HQ 3                                   │
│  Input         │ song.flac                                               │
│  Output        │ ./output/                                               │
│  Device        │ CUDA:0                                                  │
│  Architecture  │ MDX-Net                                                 │
╰──────────────────────────────────────────────────────────────────────────╯

⠹ Downloading model: UVR-MDX-NET Inst HQ 3
  ████████████████████████████████████████ 100% • 245.3 MB • 12.5 MB/s • 0:00:00

✓ Model downloaded

⠹ Running inference
  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░  42% • 0:01:23 • 0:01:52

✓ Inference complete

╭──────────────────────────────────────────────────────────────────────────╮
│              ✓ Processing completed in 3:15                              │
╰──────────────────────────────────────────────────────────────────────────╯

Output files:
  • output/song_(Vocals).wav
  • output/song_(Instrumental).wav
```

### Features

| Feature | Description |
|---------|-------------|
| 📥 **Download Progress** | Real-time speed, ETA, and transfer stats for model downloads |
| 🎯 **Inference Progress** | Chunk-based progress tracking during audio processing |
| ⏱️ **Time Estimates** | Elapsed time and remaining time (ETA) display |
| 🎨 **Rich Output** | Beautiful terminal UI with `rich` library |
| 🐳 **Docker Compatible** | Works seamlessly inside containers |
| 📉 **Graceful Fallback** | Falls back to basic output if `rich` unavailable |

### Progress Library Support

The system automatically selects the best available library:

1. **`rich`** (preferred) - Full-featured progress bars with colors
2. **`tqdm`** (fallback) - Standard progress bars
3. **Basic** (no deps) - Simple text-based progress

Install `rich` for the best experience:
```bash
pip install rich
```

### Quiet Mode

Disable progress output for scripting:
```bash
python mdx_headless_runner.py -m model.ckpt -i song.wav -o output/ --quiet
```

---

## 🎛️ MDX-Net Runner

### Command Line Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--model` | `-m` | **Required** | Model file path (.ckpt/.onnx) |
| `--input` | `-i` | **Required** | Input audio file |
| `--output` | `-o` | **Required** | Output directory |
| `--gpu` | | Auto | Use NVIDIA CUDA |
| `--directml` | | | Use AMD DirectML |
| `--overlap` | | `0.25` | MDX overlap (0.25-0.99) |
| `--overlap-mdxc` | | `2` | MDX-C/Roformer overlap (2-50) |
| `--wav-type` | | `PCM_24` | Output: PCM_16/24/32, FLOAT, DOUBLE |
| `--vocals-only` | | | Output vocals only |
| `--instrumental-only` | | | Output instrumental only |

<details>
<summary><b>📋 All Arguments</b></summary>

| Argument | Description |
|----------|-------------|
| `--name` `-n` | Output filename base |
| `--json` | Model JSON config |
| `--cpu` | Force CPU |
| `--device` `-d` | GPU device ID |
| `--segment-size` | Segment size (default: 256) |
| `--batch-size` | Batch size (default: 1) |
| `--primary-only` | Save primary stem only |
| `--secondary-only` | Save secondary stem only |
| `--stem` | MDX-C stem select |
| `--quiet` `-q` | Quiet mode |

</details>

### Examples

```bash
# Roformer with custom overlap
python mdx_headless_runner.py \
    -m "MDX23C-8KFFT-InstVoc_HQ.ckpt" \
    -i "song.flac" -o "output/" \
    --gpu --overlap-mdxc 8

# 32-bit float output
python mdx_headless_runner.py \
    -m "model.ckpt" -i "song.flac" -o "output/" \
    --gpu --wav-type FLOAT
```

---

## 🥁 Demucs Runner

### Supported Models

| Model | Version | Stems | Quality |
|-------|---------|-------|---------|
| `htdemucs` | v4 | 4 | ⭐⭐⭐ |
| `htdemucs_ft` | v4 | 4 | ⭐⭐⭐⭐ Fine-tuned |
| `htdemucs_6s` | v4 | 6 | ⭐⭐⭐⭐ +Guitar/Piano |
| `hdemucs_mmi` | v4 | 4 | ⭐⭐⭐ |
| `mdx_extra_q` | v3 | 4 | ⭐⭐⭐ |

### Command Line Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--model` | `-m` | **Required** | Model name or path |
| `--input` | `-i` | **Required** | Input audio file |
| `--output` | `-o` | **Required** | Output directory |
| `--gpu` | | Auto | Use NVIDIA CUDA |
| `--segment` | | Default | Segment size (1-100+) |
| `--shifts` | | `2` | Time shifts |
| `--stem` | | | Vocals/Drums/Bass/Other/Guitar/Piano |
| `--wav-type` | | `PCM_24` | Output bit depth |
| `--primary-only` | | | Output primary stem only |

### Stem Selection

| GUI Action | CLI Command |
|------------|-------------|
| All Stems | *(no --stem)* |
| Vocals only | `--stem Vocals --primary-only` |
| Instrumental only | `--stem Vocals --secondary-only` |

### Examples

```bash
# 6-stem separation
python demucs_headless_runner.py \
    --model htdemucs_6s \
    --input "song.flac" --output "output/" \
    --gpu

# High quality with custom segment
python demucs_headless_runner.py \
    --model htdemucs_ft \
    --input "song.flac" --output "output/" \
    --gpu --segment 85
```

---

## 🎤 VR Architecture Runner

### Command Line Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--model` | `-m` | **Required** | Model file path (.pth) |
| `--input` | `-i` | **Required** | Input audio file |
| `--output` | `-o` | **Required** | Output directory |
| `--gpu` | | Auto | Use NVIDIA CUDA |
| `--directml` | | | Use AMD DirectML |
| `--window-size` | | `512` | Window size (320/512/1024) |
| `--aggression` | | `5` | Aggression setting (0-50+) |
| `--wav-type` | | `PCM_16` | Output: PCM_16/24/32, FLOAT, DOUBLE |
| `--primary-only` | | | Output primary stem only |
| `--secondary-only` | | | Output secondary stem only |

<details>
<summary><b>📋 All Arguments</b></summary>

| Argument | Description |
|----------|-------------|
| `--name` `-n` | Output filename base |
| `--param` | Model param name (e.g., 4band_v3) |
| `--primary-stem` | Primary stem name (Vocals/Instrumental) |
| `--nout` | VR 5.1 nout parameter |
| `--nout-lstm` | VR 5.1 nout_lstm parameter |
| `--cpu` | Force CPU |
| `--device` `-d` | GPU device ID |
| `--batch-size` | Batch size (default: 1) |
| `--tta` | Enable Test-Time Augmentation |
| `--post-process` | Enable post-processing |
| `--post-process-threshold` | Post-process threshold (default: 0.2) |
| `--high-end-process` | Enable high-end mirroring |
| `--list-params` | List available model params |

</details>

### Model Parameters

When the model hash is not found in the database, you need to provide parameters manually:

```bash
# List available params
python vr_headless_runner.py --list-params

# Use custom params
python vr_headless_runner.py -m "model.pth" -i "song.flac" -o "output/" \
    --param 4band_v3 --primary-stem Vocals

# VR 5.1 model with nout/nout_lstm
python vr_headless_runner.py -m "model.pth" -i "song.flac" -o "output/" \
    --param 4band_v3 --primary-stem Vocals --nout 48 --nout-lstm 128
```

### Examples

```bash
# High quality with TTA
python vr_headless_runner.py \
    -m "UVR-MDX-NET-Voc_FT.pth" \
    -i "song.flac" -o "output/" \
    --gpu --tta --window-size 1024

# Aggressive separation
python vr_headless_runner.py \
    -m "model.pth" -i "song.flac" -o "output/" \
    --gpu --aggression 15 --post-process

# 24-bit output
python vr_headless_runner.py \
    -m "model.pth" -i "song.flac" -o "output/" \
    --gpu --wav-type PCM_24
```

---

## 📁 Output Structure

```
output/
├── song_(Vocals).wav        # Vocals
├── song_(Instrumental).wav  # Instrumental (MDX)
├── song_(Drums).wav         # Drums (Demucs)
├── song_(Bass).wav          # Bass (Demucs)
├── song_(Other).wav         # Other (Demucs)
├── song_(Guitar).wav        # Guitar (6-stem)
└── song_(Piano).wav         # Piano (6-stem)
```

---

## 🐍 Python API

```python
from mdx_headless_runner import run_mdx_headless
from demucs_headless_runner import run_demucs_headless
from vr_headless_runner import run_vr_headless

# MDX separation
run_mdx_headless(
    model_path='model.ckpt',
    audio_file='song.wav',
    export_path='output',
    use_gpu=True,
    verbose=True  # Print progress
)
# Output: output/song_(Vocals).wav, output/song_(Instrumental).wav

# Demucs separation (vocals only)
run_demucs_headless(
    model_path='htdemucs',
    audio_file='song.wav',
    export_path='output',
    use_gpu=True,
    demucs_stems='Vocals',  # or 'All Stems' for all
    primary_only=True,
    verbose=True
)
# Output: output/song_(Vocals).wav

# VR Architecture separation
run_vr_headless(
    model_path='model.pth',
    audio_file='song.wav',
    export_path='output',
    use_gpu=True,
    window_size=512,
    aggression_setting=5,
    is_tta=False,
    # For unknown models, provide params manually:
    # user_vr_model_param='4band_v3',
    # user_primary_stem='Vocals'
)
# Output: output/song_(Vocals).wav, output/song_(Instrumental).wav
```

> 💡 **Note**: Functions process audio and save to `export_path`. Check output directory for results.

---

## 🔍 Troubleshooting

<details>
<summary><b>❌ GPU not detected</b></summary>

```bash
# Check CUDA
python -c "import torch; print(torch.cuda.is_available())"

# Reinstall PyTorch with CUDA
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

</details>

<details>
<summary><b>❌ Model not found</b></summary>

**Option 1: Use automatic download (recommended)**
```bash
# List available models
python mdx_headless_runner.py --list

# Download the model
python mdx_headless_runner.py --download "UVR-MDX-NET Inst HQ 3"

# Or just use it - auto-downloads!
python mdx_headless_runner.py -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
```

**Option 2: Manual download**

Default locations:
- **MDX**: `./models/MDX_Net_Models/`
- **Demucs**: `./models/Demucs_Models/v3_v4_repo/`
- **VR**: `./models/VR_Models/`

</details>

<details>
<summary><b>❌ Network/Download errors</b></summary>

```bash
# Force refresh model registry
python model_downloader.py --sync

# Check network connectivity
python -c "import urllib.request; urllib.request.urlopen('https://github.com')"
```

The downloader includes:
- Automatic retry (3 attempts with exponential backoff)
- Resume interrupted downloads
- Fallback to cached registry

</details>

<details>
<summary><b>❌ VR model hash not found</b></summary>

If your VR model isn't in the database, provide parameters manually:

```bash
# List available params
python vr_headless_runner.py --list-params

# Specify param and primary stem
python vr_headless_runner.py -m "model.pth" -i "song.wav" -o "output/" \
    --param 4band_v3 --primary-stem Vocals
```

Common params: `4band_v3`, `4band_v2`, `1band_sr44100_hl512`, `3band_44100`

</details>

<details>
<summary><b>❌ Poor output quality</b></summary>

- Try increasing `--overlap` or `--overlap-mdxc`
- For Demucs, increase `--segment` (e.g., 85)
- Ensure correct model config with `--json`

</details>

---

## 🙏 Acknowledgments

<table>
<tr>
<td align="center">
<a href="https://github.com/Anjok07/ultimatevocalremovergui">
<img src="https://img.shields.io/badge/UVR-Ultimate%20Vocal%20Remover-purple?style=for-the-badge" alt="UVR"/>
</a>
<br/>
<sub><b>Anjok07</b> & <b>aufr33</b></sub>
</td>
<td align="center">
<a href="https://github.com/facebookresearch/demucs">
<img src="https://img.shields.io/badge/Meta-Demucs-blue?style=for-the-badge" alt="Demucs"/>
</a>
<br/>
<sub><b>Facebook Research</b></sub>
</td>
<td align="center">
<a href="https://github.com/kuielab">
<img src="https://img.shields.io/badge/Kuielab-MDX--Net-green?style=for-the-badge" alt="MDX-Net"/>
</a>
<br/>
<sub><b>Woosung Choi</b></sub>
</td>
<td align="center">
<a href="https://github.com/tsurumeso/vocal-remover">
<img src="https://img.shields.io/badge/Tsurumeso-VR%20Architecture-orange?style=for-the-badge" alt="VR Architecture"/>
</a>
<br/>
<sub><b>tsurumeso</b></sub>
</td>
</tr>
</table>

Special thanks to **[ZFTurbo](https://github.com/ZFTurbo)** for MDX23C & SCNet.

---

## 📄 License

```
MIT License

Copyright (c) 2022 Anjok07 (Ultimate Vocal Remover)
Copyright (c) 2026 UVR Headless Runner Contributors
```

<p align="center">
  <a href="LICENSE">View Full License</a>
</p>

---

## Contributing & Support

**Pull Requests** and **Issues** are welcome! Whether it's bug reports, feature suggestions, or code contributions, we greatly appreciate them all.

If you find this project helpful, please give us a **Star** ⭐ - it's the best support for us!

---

<p align="center">
  <sub>Made with ❤️ for the audio separation community</sub>
</p>
