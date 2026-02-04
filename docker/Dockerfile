# ==============================================================================
# UVR Headless Runner - Production Docker Image
# ==============================================================================
# Multi-stage build optimized for:
# - Python 3.9 (matching poetry environment)
# - NVIDIA GPU support (CUDA 12.x)
# - CPU fallback mode
# - Model caching via volumes
# - Native CLI experience (uvr-mdx, uvr-demucs, uvr-vr)
#
# Build:
#   docker build -t uvr-headless:gpu -f docker/Dockerfile .
#   docker build -t uvr-headless:cpu -f docker/Dockerfile --target cpu .
#
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Base dependencies (shared between CPU and GPU)
# ------------------------------------------------------------------------------
FROM python:3.9.0-slim-buster AS base

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Audio libraries
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    libavcodec-extra \
    libsox-fmt-all \
    sox \
    # Rubberband for time-stretching
    rubberband-cli \
    librubberband-dev \
    # Samplerate library
    libsamplerate0 \
    libsamplerate0-dev \
    # Build essentials (for some pip packages)
    build-essential \
    gcc \
    g++ \
    # Utilities
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app directory structure
WORKDIR /app

# Create non-root user for security
RUN groupadd -r uvr && useradd -r -g uvr uvr

# Create model cache directory
RUN mkdir -p /models /home/uvr/.cache && \
    chown -R uvr:uvr /models /home/uvr

# ------------------------------------------------------------------------------
# Stage 2: Python dependencies builder
# ------------------------------------------------------------------------------
FROM base AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies (CPU versions first, GPU can override later)
# Note: Dependencies are pinned to match poetry.lock versions
# Note: We install torch CPU version here, GPU stage will replace it
RUN pip install \
    numpy==1.23.5 \
    scipy==1.9.3 \
    && pip install \
    torch==2.6.0+cpu \
    torchaudio==2.6.0+cpu \
    torchvision==0.21.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu \
    && pip install \
    librosa==0.9.2 \
    soundfile==0.11.0 \
    audioread==3.0.0 \
    resampy==0.4.2 \
    julius==0.2.7 \
    pydub==0.25.1 \
    pyrubberband==0.3.0 \
    pytorch-lightning==2.0.0 \
    einops==0.8.2 \
    ml-collections==0.1.1 \
    omegaconf==2.2.3 \
    onnx==1.19.1 \
    onnx2pytorch==0.5.3 \
    onnxruntime==1.19.2 \
    rotary-embedding-torch==0.8.9 \
    beartype==0.15.0 \
    PyYAML==6.0 \
    natsort==8.2.0 \
    tqdm \
    rich \
    requests \
    aiohttp \
    samplerate==0.1.0 \
    diffq==0.2.4

# ------------------------------------------------------------------------------
# Stage 3: CPU Runtime Image
# ------------------------------------------------------------------------------
FROM base AS cpu

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=uvr:uvr . /app/

# Copy CLI wrapper scripts and set permissions
COPY --chown=uvr:uvr docker/bin/ /usr/local/bin/
RUN chmod +x /usr/local/bin/uvr /usr/local/bin/uvr-mdx /usr/local/bin/uvr-demucs /usr/local/bin/uvr-vr

# Copy entrypoint
COPY --chown=uvr:uvr docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables
ENV UVR_MODELS_DIR=/models \
    UVR_DEVICE=cpu \
    NUMBA_CACHE_DIR=/tmp/numba_cache

# Copy model metadata to a separate location (will be copied to volume on first run)
RUN mkdir -p /app/models_data/VR_Models /app/models_data/MDX_Net_Models /app/models_data/Demucs_Models /app/models_data/Apollo_Models && \
    (cp -r /app/models/VR_Models/model_data /app/models_data/VR_Models/ 2>/dev/null || true) && \
    (cp -r /app/models/MDX_Net_Models/model_data /app/models_data/MDX_Net_Models/ 2>/dev/null || true) && \
    (cp -r /app/models/Demucs_Models/model_data /app/models_data/Demucs_Models/ 2>/dev/null || true) && \
    (cp -r /app/models/Apollo_Models/* /app/models_data/Apollo_Models/ 2>/dev/null || true)

# Create symlinks for model directories to use mounted volume
RUN rm -rf /app/models/VR_Models /app/models/MDX_Net_Models /app/models/Demucs_Models /app/models/Apollo_Models && \
    ln -sf /models/VR_Models /app/models/VR_Models && \
    ln -sf /models/MDX_Net_Models /app/models/MDX_Net_Models && \
    ln -sf /models/Demucs_Models /app/models/Demucs_Models && \
    ln -sf /models/Apollo_Models /app/models/Apollo_Models && \
    chown -R uvr:uvr /app/models /app/models_data

# Switch to non-root user
USER uvr

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import torch; print('OK')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--help"]

# ------------------------------------------------------------------------------
# Stage 4: GPU Runtime Image (NVIDIA CUDA)
# ------------------------------------------------------------------------------
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS gpu-base

# Install Python 3.9 and system dependencies
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.9 \
    python3.9-venv \
    python3.9-dev \
    python3-pip \
    # Audio libraries
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    libavcodec-extra \
    libsox-fmt-all \
    sox \
    # Rubberband
    rubberband-cli \
    librubberband-dev \
    # Samplerate library
    libsamplerate0 \
    libsamplerate0-dev \
    # Build essentials
    build-essential \
    gcc \
    g++ \
    # Utilities
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Python 3.9 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.9 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1

WORKDIR /app

# Create non-root user
RUN groupadd -r uvr && useradd -r -g uvr uvr && \
    mkdir -p /models /home/uvr/.cache && \
    chown -R uvr:uvr /models /home/uvr /app

# ------------------------------------------------------------------------------
# Stage 5: GPU Python dependencies
# ------------------------------------------------------------------------------
FROM gpu-base AS gpu-builder

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install GPU-enabled PyTorch (CUDA 12.4)
RUN pip install \
    numpy==1.23.5 \
    scipy==1.9.3 \
    && pip install \
    torch==2.6.0+cu124 \
    torchaudio==2.6.0+cu124 \
    torchvision==0.21.0+cu124 \
    --index-url https://download.pytorch.org/whl/cu124 \
    && pip install \
    librosa==0.9.2 \
    soundfile==0.11.0 \
    audioread==3.0.0 \
    resampy==0.4.2 \
    julius==0.2.7 \
    pydub==0.25.1 \
    pyrubberband==0.3.0 \
    pytorch-lightning==2.0.0 \
    einops==0.8.2 \
    ml-collections==0.1.1 \
    omegaconf==2.2.3 \
    onnx==1.19.1 \
    onnx2pytorch==0.5.3 \
    onnxruntime-gpu==1.19.2 \
    rotary-embedding-torch==0.8.9 \
    beartype==0.15.0 \
    PyYAML==6.0 \
    natsort==8.2.0 \
    tqdm \
    rich \
    requests \
    aiohttp \
    samplerate==0.1.0 \
    diffq==0.2.4

# ------------------------------------------------------------------------------
# Stage 6: GPU Final Image
# ------------------------------------------------------------------------------
FROM gpu-base AS gpu

# Copy virtual environment from GPU builder
COPY --from=gpu-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=uvr:uvr . /app/

# Copy CLI wrapper scripts and set permissions
COPY --chown=uvr:uvr docker/bin/ /usr/local/bin/
RUN chmod +x /usr/local/bin/uvr /usr/local/bin/uvr-mdx /usr/local/bin/uvr-demucs /usr/local/bin/uvr-vr

# Copy entrypoint
COPY --chown=uvr:uvr docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables
ENV UVR_MODELS_DIR=/models \
    UVR_DEVICE=cuda \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Copy model metadata to a separate location (will be copied to volume on first run)
RUN mkdir -p /app/models_data/VR_Models /app/models_data/MDX_Net_Models /app/models_data/Demucs_Models /app/models_data/Apollo_Models && \
    (cp -r /app/models/VR_Models/model_data /app/models_data/VR_Models/ 2>/dev/null || true) && \
    (cp -r /app/models/MDX_Net_Models/model_data /app/models_data/MDX_Net_Models/ 2>/dev/null || true) && \
    (cp -r /app/models/Demucs_Models/model_data /app/models_data/Demucs_Models/ 2>/dev/null || true) && \
    (cp -r /app/models/Apollo_Models/* /app/models_data/Apollo_Models/ 2>/dev/null || true)

# Create symlinks for model directories
RUN rm -rf /app/models/VR_Models /app/models/MDX_Net_Models /app/models/Demucs_Models /app/models/Apollo_Models && \
    ln -sf /models/VR_Models /app/models/VR_Models && \
    ln -sf /models/MDX_Net_Models /app/models/MDX_Net_Models && \
    ln -sf /models/Demucs_Models /app/models/Demucs_Models && \
    ln -sf /models/Apollo_Models /app/models/Apollo_Models && \
    chown -R uvr:uvr /app/models /app/models_data

# Switch to non-root user
USER uvr

# Health check with GPU verification
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--help"]

# ==============================================================================
# Labels
# ==============================================================================
LABEL org.opencontainers.image.title="UVR Headless Runner" \
      org.opencontainers.image.description="Ultimate Vocal Remover - Headless CLI for audio source separation" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="UVR Community" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/Anjok07/ultimatevocalremovergui"
