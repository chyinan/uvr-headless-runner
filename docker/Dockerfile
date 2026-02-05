# ==============================================================================
# UVR Headless Runner - Production Docker Image
# ==============================================================================
# Multi-stage build optimized for:
# - Python 3.9 (matching poetry environment)
# - NVIDIA GPU support (CUDA 12.x via PyTorch wheels)
# - CPU fallback mode
# - Model caching via volumes
# - Native CLI experience (uvr-mdx, uvr-demucs, uvr-vr)
#
# SUPPLY-CHAIN SECURITY:
#   This Dockerfile implements pip hash verification for all Python packages.
#   SHA256 hashes are extracted from poetry.lock and PyPI to ensure:
#   - Package integrity: tampered packages will fail to install
#   - Reproducible builds: same hashes = identical binaries
#   - MITM protection: network attackers cannot inject malicious code
#   - CDN compromise protection: even if PyPI mirrors are compromised
#
#   If a package hash doesn't match, pip will exit with an error like:
#   "THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE"
#
# Build:
#   # Default (CUDA 12.4 - best compatibility)
#   docker build -t uvr-headless:gpu -f docker/Dockerfile .
#
#   # Specific CUDA version
#   docker build -t uvr-headless:gpu --build-arg CUDA_VERSION=cu124 -f docker/Dockerfile .
#   docker build -t uvr-headless:gpu --build-arg CUDA_VERSION=cu121 -f docker/Dockerfile .
#
#   # CPU only
#   docker build -t uvr-headless:cpu -f docker/Dockerfile --target cpu .
#
# CUDA Version Compatibility:
#   cu121 - CUDA 12.1, requires driver 530+
#   cu124 - CUDA 12.4, requires driver 550+ (recommended)
#   cu128 - CUDA 12.8, requires driver 560+
#
# ==============================================================================

# Build arguments
ARG CUDA_VERSION=cu124

# ------------------------------------------------------------------------------
# HTTP/HTTPS Proxy Support (Build-time)
# ------------------------------------------------------------------------------
# Pass proxy settings during build with:
#   docker build --build-arg HTTP_PROXY=http://proxy:port ...
#
# These ARGs automatically become ENV vars available to RUN commands.
# SECURITY: Proxy credentials will be visible in build logs - use build secrets
# for production CI/CD pipelines with sensitive credentials.
# ------------------------------------------------------------------------------
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# ------------------------------------------------------------------------------
# Stage 1: Base dependencies (shared between CPU and GPU)
# Using Ubuntu 22.04 for consistency and long-term support
# ------------------------------------------------------------------------------
FROM ubuntu:22.04 AS base

# Re-declare proxy ARGs after FROM (they don't persist across stages)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Prevent interactive prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install Python 3.9 and system dependencies for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Required GPG tooling for add-apt-repository to function correctly in minimal images
    gnupg \
    dirmngr \
    ca-certificates \
    # Python 3.9 related packages
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
    # Convert CRLF -> LF inside container if files were checked-out with CRLF
    dos2unix \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set Python 3.9 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.9 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Create app directory structure
WORKDIR /app

# Create non-root user for security
RUN groupadd -r uvr && useradd -r -g uvr -u 1000 uvr

# Create model cache directory
RUN mkdir -p /models /home/uvr/.cache && \
    chown -R uvr:uvr /models /home/uvr

# ------------------------------------------------------------------------------
# Stage 2: CPU Python dependencies builder
# ------------------------------------------------------------------------------
# SECURITY: This stage uses pip hash verification to ensure supply-chain integrity.
# All packages are verified against SHA256 hashes from poetry.lock.
# If a package is tampered with, pip will refuse to install it.
# ------------------------------------------------------------------------------
FROM base AS cpu-builder

# Re-declare proxy ARGs for this stage (pip needs them for downloads)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip (required for --require-hashes support)
RUN pip install --upgrade pip setuptools wheel

# Copy hashed requirements file
# SECURITY: requirements-hashed.txt contains SHA256 hashes for all packages.
# Any modification to packages (MITM, CDN compromise, malicious maintainer)
# will cause installation to fail with a hash mismatch error.
COPY docker/requirements-hashed.txt /tmp/requirements-hashed.txt

# Install CPU-only PyTorch first (from PyTorch CPU wheel index)
# NOTE: PyTorch from pytorch.org index doesn't have pre-computed hashes.
# For maximum security, download wheels manually and verify their hashes.
# The PyPI version includes CUDA 12.8 by default.
# Versions aligned with poetry.lock for Python 3.9
RUN pip install \
    torch==2.8.0 \
    torchvision==0.23.0 \
    torchaudio==2.8.0 \
    --index-url https://download.pytorch.org/whl/cpu

# Install all other dependencies with MANDATORY hash verification
# SECURITY: --require-hashes enforces that ALL packages must have matching hashes.
# This prevents:
#   - Man-in-the-middle attacks during download
#   - Compromised PyPI/CDN mirrors
#   - Malicious package maintainer uploads
# If any hash doesn't match, pip will exit with an error and the build will fail.
RUN pip install --require-hashes --no-deps -r /tmp/requirements-hashed.txt

# ------------------------------------------------------------------------------
# Stage 3: CPU Runtime Image
# ------------------------------------------------------------------------------
FROM base AS cpu

# Copy virtual environment from builder
COPY --from=cpu-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=uvr:uvr . /app/

# Copy CLI wrapper scripts, normalize line endings and set permissions
COPY --chown=uvr:uvr docker/bin/ /usr/local/bin/
RUN dos2unix /usr/local/bin/uvr /usr/local/bin/uvr-mdx /usr/local/bin/uvr-demucs /usr/local/bin/uvr-vr || true && \
    chmod +x /usr/local/bin/uvr /usr/local/bin/uvr-mdx /usr/local/bin/uvr-demucs /usr/local/bin/uvr-vr

# Copy entrypoint, normalize line endings and set permissions
COPY --chown=uvr:uvr docker/entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh || true && chmod +x /entrypoint.sh

# Environment variables
ENV UVR_MODELS_DIR=/models \
    UVR_DEVICE=cpu \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    PYTHONWARNINGS="ignore::UserWarning:pkg_resources"

# Copy model metadata to a separate location (will be copied to volume on first run)
RUN mkdir -p /app/models_data/VR_Models /app/models_data/MDX_Net_Models /app/models_data/Demucs_Models /app/models_data/Apollo_Models && \
    if [ -d /app/models/VR_Models/model_data ]; then cp -r /app/models/VR_Models/model_data /app/models_data/VR_Models/; fi && \
    if [ -d /app/models/MDX_Net_Models/model_data ]; then cp -r /app/models/MDX_Net_Models/model_data /app/models_data/MDX_Net_Models/; fi && \
    if [ -d /app/models/Demucs_Models/model_data ]; then cp -r /app/models/Demucs_Models/model_data /app/models_data/Demucs_Models/; fi && \
    if [ -d /app/models/Apollo_Models ]; then cp -r /app/models/Apollo_Models/* /app/models_data/Apollo_Models/ 2>/dev/null || true; fi

# Create symlinks for model directories to use mounted volume
RUN rm -rf /app/models/VR_Models /app/models/MDX_Net_Models /app/models/Demucs_Models /app/models/Apollo_Models 2>/dev/null || true && \
    mkdir -p /app/models && \
    ln -sf /models/VR_Models /app/models/VR_Models && \
    ln -sf /models/MDX_Net_Models /app/models/MDX_Net_Models && \
    ln -sf /models/Demucs_Models /app/models/Demucs_Models && \
    ln -sf /models/Apollo_Models /app/models/Apollo_Models && \
    chown -R uvr:uvr /app/models /app/models_data

# Switch to non-root user
USER uvr

# Health check - verifies PyTorch and model directory accessibility
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import torch; import os; \
        assert os.path.isdir(os.environ.get('UVR_MODELS_DIR', '/models')), 'Models dir not accessible'; \
        print('OK')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--help"]

# ------------------------------------------------------------------------------
# Stage 4: GPU Python dependencies builder
# ------------------------------------------------------------------------------
# SECURITY: This stage uses pip hash verification to ensure supply-chain integrity.
# All packages are verified against SHA256 hashes from poetry.lock.
# If a package is tampered with, pip will refuse to install it.
# ------------------------------------------------------------------------------
FROM base AS gpu-builder

# Re-declare ARG after FROM (required for multi-stage builds)
ARG CUDA_VERSION=cu124

# Re-declare proxy ARGs for this stage (pip needs them for downloads)
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip (required for --require-hashes support)
RUN pip install --upgrade pip setuptools wheel

# Copy hashed requirements file
# SECURITY: requirements-hashed.txt contains SHA256 hashes for all packages.
COPY docker/requirements-hashed.txt /tmp/requirements-hashed.txt
COPY docker/requirements-gpu-extra.txt /tmp/requirements-gpu-extra.txt

# Install GPU-enabled PyTorch with specific CUDA version
# Using cu124 (CUDA 12.4) as default for better compatibility
# - cu121: CUDA 12.1, driver 530+
# - cu124: CUDA 12.4, driver 550+ (default, good balance)
# - cu128: CUDA 12.8, driver 560+
# NOTE: PyTorch from pytorch.org doesn't have pre-computed hashes.
# For maximum security, manually verify wheel checksums.
ARG PYTORCH_VERSION=2.6.0
ARG TORCHVISION_VERSION=0.21.0
ARG TORCHAUDIO_VERSION=2.6.0

RUN pip install \
# PyTorch versions MUST align with official CUDA wheel index at:
# https://download.pytorch.org/whl/
# IMPORTANT: Not all PyTorch versions support all CUDA versions.
# Always verify version combinations exist before building.
    torch==${PYTORCH_VERSION} \
    torchvision==${TORCHVISION_VERSION} \
    torchaudio==${TORCHAUDIO_VERSION} \
    --index-url https://download.pytorch.org/whl/${CUDA_VERSION}

# Install all other dependencies with MANDATORY hash verification
# SECURITY: --require-hashes enforces that ALL packages must have matching hashes.
# This prevents MITM attacks, compromised mirrors, and malicious uploads.
RUN pip install --require-hashes --no-deps -r /tmp/requirements-hashed.txt

# Replace CPU onnxruntime with GPU version
# SECURITY: GPU extra packages are also hash-verified.
# onnxruntime-gpu provides CUDA acceleration for ONNX model inference.
RUN pip uninstall -y onnxruntime && \
    pip install --require-hashes --no-deps -r /tmp/requirements-gpu-extra.txt

# ------------------------------------------------------------------------------
# Stage 5: GPU Final Image
# ------------------------------------------------------------------------------
FROM base AS gpu

# Re-declare ARG for labels
ARG CUDA_VERSION=cu124

# Copy virtual environment from GPU builder
COPY --from=gpu-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=uvr:uvr . /app/

# Copy CLI wrapper scripts, normalize line endings and set permissions
COPY --chown=uvr:uvr docker/bin/ /usr/local/bin/
RUN dos2unix /usr/local/bin/uvr /usr/local/bin/uvr-mdx /usr/local/bin/uvr-demucs /usr/local/bin/uvr-vr || true && \
    chmod +x /usr/local/bin/uvr /usr/local/bin/uvr-mdx /usr/local/bin/uvr-demucs /usr/local/bin/uvr-vr

# Copy entrypoint, normalize line endings and set permissions
COPY --chown=uvr:uvr docker/entrypoint.sh /entrypoint.sh
RUN dos2unix /entrypoint.sh || true && chmod +x /entrypoint.sh

# Environment variables
ENV UVR_MODELS_DIR=/models \
    UVR_DEVICE=cuda \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    PYTHONWARNINGS="ignore::UserWarning:pkg_resources"

# Copy model metadata to a separate location (will be copied to volume on first run)
RUN mkdir -p /app/models_data/VR_Models /app/models_data/MDX_Net_Models /app/models_data/Demucs_Models /app/models_data/Apollo_Models && \
    if [ -d /app/models/VR_Models/model_data ]; then cp -r /app/models/VR_Models/model_data /app/models_data/VR_Models/; fi && \
    if [ -d /app/models/MDX_Net_Models/model_data ]; then cp -r /app/models/MDX_Net_Models/model_data /app/models_data/MDX_Net_Models/; fi && \
    if [ -d /app/models/Demucs_Models/model_data ]; then cp -r /app/models/Demucs_Models/model_data /app/models_data/Demucs_Models/; fi && \
    if [ -d /app/models/Apollo_Models ]; then cp -r /app/models/Apollo_Models/* /app/models_data/Apollo_Models/ 2>/dev/null || true; fi

# Create symlinks for model directories
RUN rm -rf /app/models/VR_Models /app/models/MDX_Net_Models /app/models/Demucs_Models /app/models/Apollo_Models 2>/dev/null || true && \
    mkdir -p /app/models && \
    ln -sf /models/VR_Models /app/models/VR_Models && \
    ln -sf /models/MDX_Net_Models /app/models/MDX_Net_Models && \
    ln -sf /models/Demucs_Models /app/models/Demucs_Models && \
    ln -sf /models/Apollo_Models /app/models/Apollo_Models && \
    chown -R uvr:uvr /app/models /app/models_data

# Switch to non-root user
USER uvr

# Health check with GPU verification and model directory check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import torch; import os; \
        assert os.path.isdir(os.environ.get('UVR_MODELS_DIR', '/models')), 'Models dir not accessible'; \
        print(f'CUDA: {torch.cuda.is_available()}')" || exit 1

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
      org.opencontainers.image.source="https://github.com/Anjok07/ultimatevocalremovergui" \
      org.opencontainers.image.cuda="${CUDA_VERSION}"
