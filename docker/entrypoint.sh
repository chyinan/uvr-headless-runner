#!/bin/bash
# ==============================================================================
# UVR Headless Runner - Container Entrypoint
# ==============================================================================
# Handles:
# - GPU auto-detection and fallback
# - Model directory initialization
# - CLI routing
# ==============================================================================

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ------------------------------------------------------------------------------
# GPU Detection
# ------------------------------------------------------------------------------
detect_gpu() {
    if [ "${UVR_DEVICE}" = "cpu" ]; then
        echo "cpu"
        return
    fi
    
    # Check for NVIDIA GPU
    if command -v nvidia-smi &> /dev/null; then
        if nvidia-smi &> /dev/null; then
            # Verify PyTorch can see CUDA
            if python -c "import torch; exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
                echo "cuda"
                return
            fi
        fi
    fi
    
    echo "cpu"
}

# ------------------------------------------------------------------------------
# Model Directory Setup
# ------------------------------------------------------------------------------
setup_model_dirs() {
    local models_dir="${UVR_MODELS_DIR:-/models}"
    
    # Create model subdirectories if they don't exist
    mkdir -p "${models_dir}/VR_Models/model_data" 2>/dev/null || true
    mkdir -p "${models_dir}/MDX_Net_Models/model_data/mdx_c_configs" 2>/dev/null || true
    mkdir -p "${models_dir}/Demucs_Models/v3_v4_repo" 2>/dev/null || true
    mkdir -p "${models_dir}/Apollo_Models/model_configs" 2>/dev/null || true
    
    # Copy model metadata if not present (from app to models volume)
    if [ -d /app/models ]; then
        # VR model data
        if [ -f /app/models/VR_Models/model_data/model_data.json ] && \
           [ ! -f "${models_dir}/VR_Models/model_data/model_data.json" ]; then
            cp -r /app/models/VR_Models/model_data/* "${models_dir}/VR_Models/model_data/" 2>/dev/null || true
        fi
        
        # MDX model data
        if [ -d /app/models/MDX_Net_Models/model_data ] && \
           [ ! -f "${models_dir}/MDX_Net_Models/model_data/model_data.json" ]; then
            cp -r /app/models/MDX_Net_Models/model_data/* "${models_dir}/MDX_Net_Models/model_data/" 2>/dev/null || true
        fi
        
        # Demucs model data
        if [ -f /app/models/Demucs_Models/model_data/model_name_mapper.json ] && \
           [ ! -f "${models_dir}/Demucs_Models/model_data/model_name_mapper.json" ]; then
            mkdir -p "${models_dir}/Demucs_Models/model_data" 2>/dev/null || true
            cp -r /app/models/Demucs_Models/model_data/* "${models_dir}/Demucs_Models/model_data/" 2>/dev/null || true
        fi
    fi
    
    # Update symlinks in app directory to point to models volume
    if [ -d /app/models ]; then
        # Remove existing directories/symlinks and create new symlinks
        for subdir in VR_Models MDX_Net_Models Demucs_Models Apollo_Models; do
            if [ -d "${models_dir}/${subdir}" ]; then
                rm -rf "/app/models/${subdir}" 2>/dev/null || true
                ln -sf "${models_dir}/${subdir}" "/app/models/${subdir}" 2>/dev/null || true
            fi
        done
    fi
}

# ------------------------------------------------------------------------------
# Print Startup Info
# ------------------------------------------------------------------------------
print_startup_info() {
    local device=$(detect_gpu)
    
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║           UVR Headless Runner - Container Started             ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    echo -e "Device: ${GREEN}${device}${NC}"
    
    if [ "${device}" = "cuda" ]; then
        GPU_NAME=$(python -c "import torch; print(torch.cuda.get_device_name(0))" 2>/dev/null || echo "Unknown")
        CUDA_VER=$(python -c "import torch; print(torch.version.cuda)" 2>/dev/null || echo "Unknown")
        echo -e "GPU: ${GREEN}${GPU_NAME}${NC}"
        echo -e "CUDA: ${GREEN}${CUDA_VER}${NC}"
    fi
    
    echo -e "Models: ${GREEN}${UVR_MODELS_DIR:-/models}${NC}"
    echo ""
}

# ------------------------------------------------------------------------------
# Main Entry Point
# ------------------------------------------------------------------------------
main() {
    # Setup model directories
    setup_model_dirs
    
    # Detect device
    DETECTED_DEVICE=$(detect_gpu)
    export UVR_DEVICE="${UVR_DEVICE:-${DETECTED_DEVICE}}"
    
    # Handle no arguments - show help
    if [ $# -eq 0 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
        print_startup_info
        echo "Usage:"
        echo "  uvr-mdx    - MDX-Net/Roformer separation"
        echo "  uvr-demucs - Demucs separation"
        echo "  uvr-vr     - VR Architecture separation"
        echo "  uvr        - Unified CLI"
        echo ""
        echo "Examples:"
        echo "  uvr-mdx -m \"Kim Vocal 2\" -i /input/song.wav -o /output/"
        echo "  uvr-demucs -m htdemucs -i /input/song.wav -o /output/"
        echo "  uvr-vr -m \"UVR-De-Echo-Normal\" -i /input/song.wav -o /output/"
        echo ""
        echo "For more help:"
        echo "  uvr-mdx --help"
        echo "  uvr-demucs --help"
        echo "  uvr-vr --help"
        exit 0
    fi
    
    # Route to appropriate command
    case "$1" in
        uvr-mdx|mdx)
            shift
            exec /usr/local/bin/uvr-mdx "$@"
            ;;
        uvr-demucs|demucs)
            shift
            exec /usr/local/bin/uvr-demucs "$@"
            ;;
        uvr-vr|vr)
            shift
            exec /usr/local/bin/uvr-vr "$@"
            ;;
        uvr)
            shift
            exec /usr/local/bin/uvr "$@"
            ;;
        python|python3)
            # Allow direct Python execution
            exec "$@"
            ;;
        bash|sh)
            # Allow shell access
            exec "$@"
            ;;
        *)
            # Default: try to execute as command
            exec "$@"
            ;;
    esac
}

main "$@"
