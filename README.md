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
</p>

<p align="center">
  <a href="README_CN.md">🇨🇳 中文</a> | <strong>🇬🇧 English</strong>
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

| Feature | Description |
|---------|-------------|
| 🎯 **GUI-Identical** | Exactly replicates UVR GUI behavior |
| ⚡ **GPU Accelerated** | NVIDIA CUDA & AMD DirectML support |
| 🔧 **Zero Config** | Auto-detect model parameters |
| 📦 **Batch Ready** | Perfect for automation & pipelines |
| 🎚️ **Bit Depth Control** | 16/24/32-bit PCM, 32/64-bit float |

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

## 📋 Requirements

| Component | Requirement |
|-----------|-------------|
| **Python** | 3.9.x (3.10+ not fully tested) |
| **GPU** | NVIDIA CUDA or AMD DirectML *(optional)* |
| **OS** | Windows / Linux / macOS |

---

## 🔧 Installation

<details>
<summary><b>📦 Option 1: Poetry (Recommended)</b></summary>

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
<summary><b>📦 Option 2: pip + venv</b></summary>

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

### ✅ Verify Installation

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

---

## 🎼 Quick Start

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

Default locations:
- **MDX**: `C:\Users\{user}\AppData\Local\Programs\Ultimate Vocal Remover\models\MDX_Net_Models\`
- **Demucs**: Auto-downloaded to `~/.cache/torch/hub/`
- **VR**: `C:\Users\{user}\AppData\Local\Programs\Ultimate Vocal Remover\models\VR_Models\`

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
