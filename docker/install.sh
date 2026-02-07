#!/bin/bash
# ==============================================================================
# UVR Headless Runner - Installation Script
# ==============================================================================
# This script installs native-style CLI wrappers so you can run:
#   uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
#   uvr-demucs -m htdemucs -i song.wav -o output/
#   uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
#
# Without needing to type `docker run` commands!
# By default, it pulls pre-built images from Docker Hub for fast installation.
#
# Usage:
#   ./docker/install.sh              # Quick install (pulls from Docker Hub)
#   ./docker/install.sh --cpu        # Force CPU-only installation
#   ./docker/install.sh --gpu        # Force GPU installation (CUDA 12.4)
#   ./docker/install.sh --cuda cu121 # GPU with specific CUDA version
#   ./docker/install.sh --cuda cu124 # GPU with CUDA 12.4 (default)
#   ./docker/install.sh --cuda cu128 # GPU with CUDA 12.8
#   ./docker/install.sh --build      # Force local build (slower)
#   ./docker/install.sh --uninstall  # Remove installed wrappers
#
# Image Source:
#   Default: Pulls pre-built images from Docker Hub (fast, ~2-5 min)
#   --build: Builds locally from source (slower, ~10-30 min)
#
# CUDA Version Options:
#   cu121 - CUDA 12.1, requires NVIDIA driver 530+
#   cu124 - CUDA 12.4, requires NVIDIA driver 550+ (default, recommended)
#   cu128 - CUDA 12.8, requires NVIDIA driver 560+
#
# ==============================================================================

set -eo pipefail

# ------------------------------------------------------------------------------
# Crash-safety: Cleanup trap for temp files
# ------------------------------------------------------------------------------
# Track temp files created during installation so that Ctrl+C, network loss,
# or any unexpected exit doesn't leave orphaned files in /tmp.
_CLEANUP_FILES=()

cleanup_on_exit() {
    local exit_code=$?
    for f in "${_CLEANUP_FILES[@]}"; do
        rm -f "$f" 2>/dev/null || true
    done
    if [ "${exit_code}" -ne 0 ] && [ "${exit_code}" -ne 130 ]; then
        echo "" >&2
        log_warn "Installation was interrupted (exit code: ${exit_code})"
        log_info "It is safe to rerun this script — all steps are idempotent."
    fi
}

trap cleanup_on_exit EXIT INT TERM HUP

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${UVR_INSTALL_DIR:-/usr/local/bin}"

# FIX: Detect actual user's home when running under sudo.
# When `sudo ./install.sh` is used, $HOME becomes /root, but we want the
# real user's home directory so that model cache (~/.uvr_models) and wrapper
# MODELS_DIR default are accessible by the normal user after installation.
if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
    REAL_HOME=$(getent passwd "${SUDO_USER}" 2>/dev/null | cut -d: -f6) || REAL_HOME=$(eval echo "~${SUDO_USER}")
else
    REAL_HOME="${HOME}"
fi

MODELS_DIR="${UVR_MODELS_DIR:-${REAL_HOME}/.uvr_models}"
IMAGE_NAME="uvr-headless-runner"
# Docker Hub image for pre-built images (much faster!)
DOCKERHUB_IMAGE="chyinan/uvr-headless-runner"
# CUDA version for GPU builds (cu121, cu124, cu128)
CUDA_VERSION="${UVR_CUDA_VERSION:-cu124}"
# Whether to force local build instead of pulling from Docker Hub
FORCE_BUILD="${UVR_FORCE_BUILD:-}"
# Max retries for docker pull operations (handles flaky networks)
PULL_MAX_RETRIES=3

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# GPU test image (small ~80MB base image, used only for GPU detection)
GPU_TEST_IMAGE="nvidia/cuda:12.4.1-base-ubuntu22.04"
# Timeout (seconds) for GPU detection container test
GPU_TEST_TIMEOUT=60

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
# NOTE: All log functions output to STDERR intentionally.
# This prevents log messages from polluting function return values
# captured via $() subshells. Example: target=$(detect_gpu) must only
# capture "gpu" or "cpu", not intermixed log lines.
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

print_banner() {
    echo -e "${CYAN}" >&2
    echo "=========================================================" >&2
    echo "       UVR Headless Runner - Installation Script         " >&2
    echo "=========================================================" >&2
    echo -e "${NC}" >&2
}

# Portable in-place file editing (works on both macOS BSD sed and Linux GNU sed)
# Uses perl which is available on all Unix-like systems
sed_inplace() {
    local pattern="$1"
    local file="$2"
    if command -v perl &> /dev/null; then
        perl -pi -e "$pattern" "$file"
    else
        # Fallback to sed with temp file (works everywhere)
        local tmp="${file}.tmp.$$"
        _CLEANUP_FILES+=("${tmp}")
        sed "$pattern" "$file" > "$tmp" && mv "$tmp" "$file"
    fi
}

check_docker() {
    # Step 1: Verify the docker binary exists
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        echo "  https://docs.docker.com/get-docker/" >&2
        exit 1
    fi
    
    # Step 2: Run 'docker info' ONCE and capture both stderr and exit code.
    # FIX: The old code called docker info twice — once to capture stderr and
    # once to check the exit code. Between the two calls, daemon state could
    # change, causing the captured stderr to describe a DIFFERENT failure than
    # the one that actually triggered the error branch (TOCTOU race).
    local docker_stderr
    local docker_exit=0
    docker_stderr=$(docker info 2>&1 1>/dev/null) || docker_exit=$?
    
    if [ "${docker_exit}" -ne 0 ]; then
        if echo "${docker_stderr}" | grep -qi "permission denied\|dial unix.*connect"; then
            log_error "Docker permission denied — your user is not in the 'docker' group."
            echo "" >&2
            echo "Fix with:" >&2
            echo "  sudo usermod -aG docker \$USER" >&2
            echo "  Then log out and back in (or run: newgrp docker)" >&2
        elif echo "${docker_stderr}" | grep -qi "cannot connect\|connection refused\|Is the docker daemon running"; then
            log_error "Docker daemon is not running."
            echo "" >&2
            echo "Start Docker with one of:" >&2
            echo "  sudo systemctl start docker" >&2
            echo "  (or start Docker Desktop if installed)" >&2
        else
            log_error "Docker is not working properly."
            echo "Detail: ${docker_stderr}" >&2
            echo "" >&2
            echo "Common fixes:" >&2
            echo "  - Start Docker: sudo systemctl start docker" >&2
            echo "  - Add user to docker group: sudo usermod -aG docker \$USER" >&2
            echo "  - Then log out and back in" >&2
        fi
        exit 1
    fi
    
    log_success "Docker is available"
}

# Retry wrapper for docker pull (handles flaky networks and partial failures)
# Usage: pull_with_retry <image> [max_retries] [initial_delay_seconds]
pull_with_retry() {
    local image="$1"
    local max_retries="${2:-${PULL_MAX_RETRIES}}"
    local delay="${3:-5}"

    for i in $(seq 1 "${max_retries}"); do
        if docker pull "${image}" >&2; then
            return 0
        fi
        if [ "$i" -lt "${max_retries}" ]; then
            log_warn "Pull failed (attempt ${i}/${max_retries}), retrying in ${delay}s..."
            sleep "${delay}"
            delay=$((delay * 2))  # exponential back-off
        fi
    done
    log_warn "Pull failed after ${max_retries} attempts"
    return 1
}

# ==============================================================================
# GPU Auto-Configuration Pipeline (Self-Healing)
# ==============================================================================
# This pipeline replaces the old passive detect_gpu with an active,
# self-healing system that:
#   1. Validates host GPU hardware (nvidia-smi + driver version)
#   2. Auto-installs NVIDIA Container Toolkit if missing
#   3. Auto-configures Docker GPU runtime (daemon.json)
#   4. Auto-restarts Docker when required
#   5. Runs GPU passthrough test with failure classification
#   6. Auto-fixes detected issues and retries
#   7. Only falls back to CPU after all auto-fixes are exhausted
#
# Returns: "gpu" or "cpu" via stdout (all diagnostics go to stderr)
# ==============================================================================

# Detect Linux distribution for package manager selection
detect_distro() {
    if [ -f /etc/os-release ]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        echo "${ID}"
    elif command -v lsb_release &>/dev/null; then
        lsb_release -is 2>/dev/null | tr '[:upper:]' '[:lower:]'
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    else
        echo "unknown"
    fi
}

# Get NVIDIA driver version from nvidia-smi
get_nvidia_driver_version() {
    if ! command -v nvidia-smi &>/dev/null; then
        echo ""
        return
    fi
    nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d '[:space:]'
}

# Get sudo prefix (empty string if root, "sudo" if available, empty if neither)
_get_sudo_prefix() {
    if [ "$(id -u)" -eq 0 ]; then
        echo ""
    elif command -v sudo &>/dev/null; then
        echo "sudo"
    else
        echo ""
    fi
}

# Auto-install NVIDIA Container Toolkit
# Supports: Debian/Ubuntu, RHEL/CentOS/Fedora, openSUSE
# Returns: 0 on success, 1 on failure
ensure_nvidia_container_toolkit() {
    if command -v nvidia-ctk &>/dev/null; then
        log_info "NVIDIA Container Toolkit is already installed"
        return 0
    fi

    log_info "NVIDIA Container Toolkit not found — attempting auto-installation..."

    local distro
    distro=$(detect_distro)

    local sudo_prefix
    sudo_prefix=$(_get_sudo_prefix)

    if [ "$(id -u)" -ne 0 ] && [ -z "${sudo_prefix}" ]; then
        log_warn "Cannot install nvidia-container-toolkit: not root and sudo not available"
        return 1
    fi

    case "${distro}" in
        ubuntu|debian|linuxmint|pop)
            log_info "Detected ${distro} — using apt to install nvidia-container-toolkit"

            # Add NVIDIA GPG key
            if ! curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
                 ${sudo_prefix} gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null; then
                log_warn "Failed to add NVIDIA GPG key"
                return 1
            fi

            # Add repository
            if ! curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
                 sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                 ${sudo_prefix} tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null; then
                log_warn "Failed to add NVIDIA repository"
                return 1
            fi

            ${sudo_prefix} apt-get update -qq >/dev/null 2>&1
            if ! ${sudo_prefix} apt-get install -y -qq nvidia-container-toolkit >/dev/null 2>&1; then
                log_warn "Failed to install nvidia-container-toolkit via apt"
                return 1
            fi

            log_success "nvidia-container-toolkit installed via apt"
            return 0
            ;;
        rhel|centos|fedora|rocky|almalinux|amzn)
            log_info "Detected ${distro} — using yum/dnf to install nvidia-container-toolkit"

            if ! curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | \
                 ${sudo_prefix} tee /etc/yum.repos.d/nvidia-container-toolkit.repo >/dev/null; then
                log_warn "Failed to add NVIDIA repository"
                return 1
            fi

            if command -v dnf &>/dev/null; then
                if ! ${sudo_prefix} dnf install -y nvidia-container-toolkit >/dev/null 2>&1; then
                    log_warn "Failed to install nvidia-container-toolkit via dnf"
                    return 1
                fi
            elif command -v yum &>/dev/null; then
                if ! ${sudo_prefix} yum install -y nvidia-container-toolkit >/dev/null 2>&1; then
                    log_warn "Failed to install nvidia-container-toolkit via yum"
                    return 1
                fi
            else
                log_warn "Neither dnf nor yum found on ${distro}"
                return 1
            fi

            log_success "nvidia-container-toolkit installed"
            return 0
            ;;
        opensuse*|sles)
            log_info "Detected ${distro} — using zypper to install nvidia-container-toolkit"
            if ! ${sudo_prefix} zypper --non-interactive install nvidia-container-toolkit >/dev/null 2>&1; then
                log_warn "Failed to install nvidia-container-toolkit via zypper"
                return 1
            fi
            log_success "nvidia-container-toolkit installed"
            return 0
            ;;
        *)
            log_warn "Unsupported distribution for auto-install: ${distro}"
            log_warn "Please install nvidia-container-toolkit manually:"
            log_warn "  https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            return 1
            ;;
    esac
}

# Auto-configure Docker daemon for NVIDIA GPU runtime
# Uses nvidia-ctk (preferred) or manual daemon.json editing
# Returns: 0 on success, 1 on failure
ensure_docker_gpu_runtime() {
    local sudo_prefix
    sudo_prefix=$(_get_sudo_prefix)

    if [ "$(id -u)" -ne 0 ] && [ -z "${sudo_prefix}" ]; then
        log_warn "Cannot configure Docker runtime: not root and sudo not available"
        return 1
    fi

    # Check if Docker already has nvidia runtime configured
    local docker_runtimes
    docker_runtimes=$(docker info --format '{{json .Runtimes}}' 2>/dev/null || echo "")
    if echo "${docker_runtimes}" | grep -qi "nvidia"; then
        log_info "Docker GPU runtime (nvidia) is already configured"
        return 0
    fi

    # Method 1: Use nvidia-ctk (recommended, handles all edge cases)
    if command -v nvidia-ctk &>/dev/null; then
        log_info "Configuring Docker runtime with nvidia-ctk..."
        if ${sudo_prefix} nvidia-ctk runtime configure --runtime=docker >/dev/null 2>&1; then
            log_success "Docker GPU runtime configured via nvidia-ctk"
            return 0
        else
            log_warn "nvidia-ctk runtime configure failed, trying manual configuration..."
        fi
    fi

    # Method 2: Manual daemon.json editing
    local daemon_json="/etc/docker/daemon.json"
    log_info "Manually configuring Docker GPU runtime in ${daemon_json}..."

    if [ -f "${daemon_json}" ]; then
        # Check if already configured (in case docker info didn't show it)
        if grep -q "nvidia" "${daemon_json}" 2>/dev/null; then
            log_info "daemon.json already contains NVIDIA configuration"
            return 0
        fi

        # Backup existing config
        ${sudo_prefix} cp "${daemon_json}" "${daemon_json}.backup.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true

        # Merge nvidia runtime into existing config using python3
        if command -v python3 &>/dev/null; then
            ${sudo_prefix} python3 -c "
import json
with open('${daemon_json}') as f:
    cfg = json.load(f)
cfg.setdefault('runtimes', {})['nvidia'] = {
    'path': 'nvidia-container-runtime',
    'runtimeArgs': []
}
with open('${daemon_json}', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null
            if [ $? -eq 0 ]; then
                log_success "Docker GPU runtime configured (merged into existing daemon.json)"
                return 0
            fi
        fi

        log_warn "Could not merge into existing daemon.json — creating new config"
    fi

    # Create new daemon.json with nvidia runtime
    echo '{"runtimes":{"nvidia":{"path":"nvidia-container-runtime","runtimeArgs":[]}},"default-runtime":"nvidia"}' | \
        ${sudo_prefix} tee "${daemon_json}" >/dev/null 2>&1

    if [ $? -eq 0 ]; then
        log_success "Docker GPU runtime configured (new daemon.json created)"
        return 0
    fi

    log_warn "Failed to configure Docker GPU runtime"
    return 1
}

# Restart Docker daemon and wait for readiness
# Returns: 0 if Docker is ready, 1 if timed out
restart_docker_daemon() {
    local max_wait="${1:-60}"

    local sudo_prefix
    sudo_prefix=$(_get_sudo_prefix)

    if [ "$(id -u)" -ne 0 ] && [ -z "${sudo_prefix}" ]; then
        log_warn "Cannot restart Docker: not root and sudo not available"
        return 1
    fi

    log_info "Restarting Docker daemon..."

    if command -v systemctl &>/dev/null; then
        ${sudo_prefix} systemctl restart docker 2>/dev/null || {
            log_warn "systemctl restart docker failed"
            return 1
        }
    elif command -v service &>/dev/null; then
        ${sudo_prefix} service docker restart 2>/dev/null || {
            log_warn "service docker restart failed"
            return 1
        }
    else
        log_warn "Neither systemctl nor service found — cannot restart Docker"
        return 1
    fi

    # Poll for Docker readiness
    log_info "Waiting for Docker to be ready (up to ${max_wait}s)..."
    local waited=0
    while [ ${waited} -lt ${max_wait} ]; do
        if docker info >/dev/null 2>&1; then
            log_success "Docker is ready (took ${waited}s)"
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done

    log_warn "Docker did not become ready within ${max_wait}s"
    return 1
}

# Classify GPU test failure from stderr output
# Returns failure reason string via stdout
classify_gpu_failure() {
    local stderr="$1"
    local exit_code="$2"
    local stderr_lower

    if [ "${exit_code}" -eq 124 ]; then
        echo "timeout"
        return
    fi

    stderr_lower=$(echo "${stderr}" | tr '[:upper:]' '[:lower:]')

    case "${stderr_lower}" in
        *"could not select device driver"*|*"unknown flag"*"gpus"*|*"unknown"*"--gpus"*)
            echo "runtime_missing" ;;
        *"permission denied"*)
            echo "permission_denied" ;;
        *"cannot connect"*|*"connection refused"*|*"is the docker daemon running"*)
            echo "docker_not_running" ;;
        *"driver"*"version"*|*"insufficient"*"driver"*|*"nvml"*|*"failed to initialize"*)
            echo "driver_mismatch" ;;
        *"nvidia-container"*|*"libnvidia-container"*|*"oci runtime"*)
            echo "nvidia_runtime_error" ;;
        *"no such image"*|*"manifest unknown"*)
            echo "image_missing" ;;
        *)
            echo "unknown" ;;
    esac
}

# Run a single GPU passthrough test with full stdout+stderr capture.
# Sets global variables: _GPU_TEST_EXIT, _GPU_TEST_STDOUT, _GPU_TEST_STDERR, _GPU_TEST_REASON
# Returns: the exit code (0 = success)
run_gpu_test() {
    local test_image="${1:-${GPU_TEST_IMAGE}}"
    local timeout_sec="${2:-${GPU_TEST_TIMEOUT}}"
    local tmp_stdout tmp_stderr

    tmp_stdout=$(mktemp)
    tmp_stderr=$(mktemp)
    _CLEANUP_FILES+=("${tmp_stdout}" "${tmp_stderr}")

    _GPU_TEST_EXIT=0

    if command -v timeout &>/dev/null; then
        timeout --kill-after=15 "${timeout_sec}" \
            docker run --rm --gpus all "${test_image}" nvidia-smi \
            >"${tmp_stdout}" 2>"${tmp_stderr}" || _GPU_TEST_EXIT=$?
    else
        # Systems without timeout: background process + watchdog
        docker run --rm --gpus all "${test_image}" nvidia-smi \
            >"${tmp_stdout}" 2>"${tmp_stderr}" &
        local pid=$!
        local waited=0
        while kill -0 "${pid}" 2>/dev/null && [ ${waited} -lt ${timeout_sec} ]; do
            sleep 1
            waited=$((waited + 1))
        done
        if kill -0 "${pid}" 2>/dev/null; then
            kill -9 "${pid}" 2>/dev/null || true
            wait "${pid}" 2>/dev/null || true
            _GPU_TEST_EXIT=124
        else
            wait "${pid}" 2>/dev/null
            _GPU_TEST_EXIT=$?
        fi
    fi

    _GPU_TEST_STDOUT=$(cat "${tmp_stdout}" 2>/dev/null)
    _GPU_TEST_STDERR=$(cat "${tmp_stderr}" 2>/dev/null)
    rm -f "${tmp_stdout}" "${tmp_stderr}"

    if [ "${_GPU_TEST_EXIT}" -eq 0 ]; then
        _GPU_TEST_REASON="success"
    else
        _GPU_TEST_REASON=$(classify_gpu_failure "${_GPU_TEST_STDERR}" "${_GPU_TEST_EXIT}")
    fi

    return ${_GPU_TEST_EXIT}
}

# ==============================================================================
# Main GPU Detection: Self-Healing Pipeline
# ==============================================================================
detect_gpu() {
    local MAX_HEALING_ATTEMPTS=3

    # ══════════════════════════════════════════════════════════════════
    # Phase 1: Host GPU Hardware Validation
    # ══════════════════════════════════════════════════════════════════

    if ! command -v nvidia-smi &>/dev/null; then
        log_info "nvidia-smi not found — no NVIDIA GPU driver installed"
        echo "cpu"
        return
    fi

    if ! nvidia-smi >/dev/null 2>&1; then
        log_warn "nvidia-smi is installed but failed to communicate with the driver"
        log_warn "Possible causes:"
        log_warn "  - NVIDIA kernel module not loaded (try: sudo modprobe nvidia)"
        log_warn "  - Driver/kernel version mismatch after a kernel update"
        log_warn "  - GPU is in a bad state (try: sudo nvidia-smi -r)"
        echo "cpu"
        return
    fi

    local driver_version
    driver_version=$(get_nvidia_driver_version)
    local gpu_name
    gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | tr -d '\n')

    log_info "NVIDIA GPU detected: ${gpu_name:-Unknown}"
    log_info "Driver version: ${driver_version:-Unknown}"

    # ══════════════════════════════════════════════════════════════════
    # Phase 2: NVIDIA Container Toolkit Check + Auto-Install
    # ══════════════════════════════════════════════════════════════════

    if ! command -v nvidia-ctk &>/dev/null && ! command -v nvidia-container-runtime &>/dev/null; then
        log_warn "NVIDIA Container Toolkit not found"
        log_info "Attempting auto-installation..."

        if ensure_nvidia_container_toolkit; then
            log_success "NVIDIA Container Toolkit installed successfully"
        else
            log_warn "Auto-install failed — GPU passthrough may not work"
            log_info "Will attempt GPU test anyway"
        fi
    else
        log_info "NVIDIA Container Toolkit is installed"
    fi

    # ══════════════════════════════════════════════════════════════════
    # Phase 3: Docker GPU Runtime Configuration
    # ══════════════════════════════════════════════════════════════════

    local docker_runtimes
    docker_runtimes=$(docker info --format '{{json .Runtimes}}' 2>/dev/null || echo "")

    if ! echo "${docker_runtimes}" | grep -qi "nvidia"; then
        log_info "Docker GPU runtime not configured — attempting auto-configuration..."

        if ensure_docker_gpu_runtime; then
            log_info "Docker GPU runtime configured — restarting Docker..."
            if ! restart_docker_daemon 60; then
                log_warn "Docker restart failed after runtime configuration"
            fi
        else
            log_warn "Could not configure Docker GPU runtime"
            log_info "Will attempt GPU test anyway"
        fi
    else
        log_info "Docker GPU runtime (nvidia) is configured"
    fi

    # ══════════════════════════════════════════════════════════════════
    # Phase 4: Ensure GPU Test Image is Available
    # ══════════════════════════════════════════════════════════════════

    if ! docker image inspect "${GPU_TEST_IMAGE}" >/dev/null 2>&1; then
        log_info "GPU test image not cached — pulling: ${GPU_TEST_IMAGE}"
        log_info "(one-time download, ~80 MB — please wait)"

        local pull_ok=0
        local pull_delay=5
        local pull_attempt
        for pull_attempt in $(seq 1 "${PULL_MAX_RETRIES}"); do
            local pull_rc=0
            if command -v timeout &>/dev/null; then
                timeout --kill-after=15 180 docker pull "${GPU_TEST_IMAGE}" >&2 || pull_rc=$?
            else
                docker pull "${GPU_TEST_IMAGE}" >&2 || pull_rc=$?
            fi
            if [ "${pull_rc}" -eq 0 ]; then
                pull_ok=1
                break
            fi
            if [ "${pull_attempt}" -lt "${PULL_MAX_RETRIES}" ]; then
                log_warn "Pull failed (attempt ${pull_attempt}/${PULL_MAX_RETRIES}), retrying in ${pull_delay}s..."
                sleep "${pull_delay}"
                pull_delay=$((pull_delay * 2))
            fi
        done

        if [ "${pull_ok}" -eq 0 ]; then
            log_warn "Failed to pull GPU test image"
            # Heuristic: toolkit installed + driver works → probably fine
            if command -v nvidia-ctk &>/dev/null || command -v nvidia-container-runtime &>/dev/null; then
                log_info "NVIDIA runtime tools found — proceeding with GPU mode optimistically"
                echo "gpu"
                return
            fi
            log_warn "Cannot verify GPU passthrough — falling back to CPU"
            log_info "Tip: use  ./docker/install.sh --gpu  to force GPU mode"
            echo "cpu"
            return
        fi
    fi

    # ══════════════════════════════════════════════════════════════════
    # Phase 5: Self-Healing GPU Passthrough Test Loop
    # ══════════════════════════════════════════════════════════════════

    log_info "Testing Docker GPU passthrough (docker run --gpus all)..."

    local fixes_applied=""
    local heal_attempt

    for heal_attempt in $(seq 1 ${MAX_HEALING_ATTEMPTS}); do
        # Run GPU passthrough test (sets _GPU_TEST_EXIT, _GPU_TEST_STDERR, _GPU_TEST_REASON)
        _GPU_TEST_EXIT=0
        _GPU_TEST_STDERR=""
        _GPU_TEST_REASON=""
        run_gpu_test "${GPU_TEST_IMAGE}" "${GPU_TEST_TIMEOUT}" || true

        if [ "${_GPU_TEST_EXIT}" -eq 0 ]; then
            log_success "Docker GPU passthrough verified — all checks passed"
            if [ -n "${fixes_applied}" ]; then
                log_success "Auto-fixes applied:${fixes_applied}"
            fi
            echo "gpu"
            return
        fi

        # ── Diagnose failure and attempt auto-fix ──
        local reason="${_GPU_TEST_REASON}"
        log_warn "GPU test FAILED (attempt ${heal_attempt}/${MAX_HEALING_ATTEMPTS})"
        log_warn "  Exit code: ${_GPU_TEST_EXIT}"
        log_warn "  Reason: ${reason}"
        if [ -n "${_GPU_TEST_STDERR}" ]; then
            log_warn "  Docker stderr: $(echo "${_GPU_TEST_STDERR}" | head -c 500)"
        fi

        # Skip fixes we already tried
        if echo "${fixes_applied}" | grep -q "${reason}"; then
            log_warn "Fix for '${reason}' already attempted — trying Docker restart"
            reason="needs_restart"
        fi

        local fixed=0
        case "${reason}" in
            runtime_missing|nvidia_runtime_error)
                log_info "GPU runtime issue — installing toolkit and configuring runtime..."
                ensure_nvidia_container_toolkit || true
                if ensure_docker_gpu_runtime; then
                    if restart_docker_daemon 60; then
                        fixed=1
                        fixes_applied="${fixes_applied} ${reason}"
                    fi
                fi
                ;;
            docker_not_running)
                log_info "Docker not running — attempting restart..."
                if restart_docker_daemon 60; then
                    fixed=1
                    fixes_applied="${fixes_applied} docker_not_running"
                fi
                ;;
            needs_restart)
                log_info "Restarting Docker for GPU re-initialization..."
                if restart_docker_daemon 60; then
                    fixed=1
                    fixes_applied="${fixes_applied} needs_restart"
                fi
                ;;
            timeout)
                # Clean up orphaned containers that may be holding GPU resources
                local orphans
                orphans=$(docker ps -aq --filter "ancestor=${GPU_TEST_IMAGE}" 2>/dev/null) || true
                if [ -n "${orphans}" ]; then
                    log_info "Cleaning up orphaned GPU test containers..."
                    docker rm -f ${orphans} >/dev/null 2>&1 || true
                    sleep 3
                fi
                fixed=1  # just retry
                fixes_applied="${fixes_applied} timeout"
                ;;
            driver_mismatch)
                log_warn "NVIDIA driver/CUDA version mismatch — cannot auto-fix"
                log_warn "Please update your NVIDIA driver"
                break  # non-recoverable
                ;;
            permission_denied)
                log_warn "Permission denied for GPU access"
                log_warn "Please run with sudo or add your user to the docker group"
                break  # non-recoverable
                ;;
            image_missing)
                log_info "GPU test image missing — pulling..."
                if pull_with_retry "${GPU_TEST_IMAGE}" "${PULL_MAX_RETRIES}" 5; then
                    fixed=1
                    fixes_applied="${fixes_applied} image_missing"
                fi
                ;;
            *)
                # Unknown failure — Docker restart is the universal fix attempt
                log_info "Unknown failure — attempting Docker restart..."
                if restart_docker_daemon 60; then
                    fixed=1
                    fixes_applied="${fixes_applied} unknown_restart"
                fi
                ;;
        esac

        if [ "${fixed}" -eq 0 ]; then
            log_warn "Auto-fix for '${reason}' was not successful — stopping retry loop"
            break
        fi

        log_info "Retrying GPU test in 5s..."
        sleep 5
    done

    # ══════════════════════════════════════════════════════════════════
    # Phase 6: All Auto-Fixes Exhausted — Diagnostic Summary
    # ══════════════════════════════════════════════════════════════════

    log_warn ""
    log_warn "================================================================"
    log_warn " GPU AUTO-CONFIGURATION FAILED — DIAGNOSTIC SUMMARY"
    log_warn "================================================================"
    log_warn ""
    log_warn "GPU:             ${gpu_name:-Unknown}"
    log_warn "Driver:          ${driver_version:-Unknown}"
    log_warn "Toolkit:         $(command -v nvidia-ctk >/dev/null 2>&1 && echo 'installed' || echo 'NOT installed')"
    log_warn "Docker runtime:  $(docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia && echo 'configured' || echo 'NOT configured')"
    log_warn "Fixes attempted: ${fixes_applied:-none}"
    log_warn ""
    log_warn "Manual troubleshooting:"
    log_warn "  1. Install NVIDIA Container Toolkit:"
    log_warn "       https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    log_warn "  2. Configure Docker runtime:"
    log_warn "       sudo nvidia-ctk runtime configure --runtime=docker"
    log_warn "  3. Restart Docker:"
    log_warn "       sudo systemctl restart docker"
    log_warn "  4. Verify manually:"
    log_warn "       docker run --rm --gpus all ${GPU_TEST_IMAGE} nvidia-smi"
    log_warn ""
    log_warn "Falling back to CPU mode."
    log_info "Tip: use  ./docker/install.sh --gpu  to force GPU mode"

    echo "cpu"
}

# Check if we can write to installation directory
check_install_permissions() {
    local dir="$1"
    
    if [ -w "${dir}" ]; then
        echo "direct"
    elif command -v sudo &> /dev/null; then
        # Check if sudo is available and user can use it
        if sudo -n true 2>/dev/null; then
            echo "sudo"
        else
            log_warn "Installation to ${dir} requires sudo access"
            echo "sudo"
        fi
    else
        echo "none"
    fi
}

# ------------------------------------------------------------------------------
# Pull or Build Docker Image
# ------------------------------------------------------------------------------
pull_image() {
    local target="$1"
    local local_tag="$2"
    local cuda_ver="$3"
    local hub_tag
    
    # Map target to Docker Hub tag
    # NOTE: Docker Hub currently only publishes cu124 GPU images.
    # For other CUDA versions, callers should skip pull and build locally.
    if [ "${target}" = "gpu" ]; then
        hub_tag="${DOCKERHUB_IMAGE}:latest"
    else
        hub_tag="${DOCKERHUB_IMAGE}:latest-cpu"
    fi
    
    log_info "Pulling pre-built image from Docker Hub: ${hub_tag}"
    log_info "This is much faster than building locally!"
    
    if pull_with_retry "${hub_tag}" "${PULL_MAX_RETRIES}" 5; then
        # Tag the pulled image with our local tag for consistency
        if ! docker tag "${hub_tag}" "${local_tag}"; then
            log_warn "Image pulled but tagging as ${local_tag} failed"
            return 1
        fi
        log_success "Image pulled and tagged: ${local_tag}"
        return 0
    else
        log_warn "Failed to pull from Docker Hub"
        return 1
    fi
}

build_image() {
    local target="$1"
    local cuda_ver="$2"
    local tag
    
    if [ "${target}" = "gpu" ]; then
        tag="${IMAGE_NAME}:gpu-${cuda_ver}"
    else
        tag="${IMAGE_NAME}:${target}"
    fi
    
    # Try pulling from Docker Hub first (unless force build is set)
    # Docker Hub only has cu124 GPU images — other CUDA versions require local build
    if [ -z "${FORCE_BUILD}" ]; then
        if [ "${target}" = "gpu" ] && [ "${cuda_ver}" != "cu124" ]; then
            log_info "Docker Hub only has cu124 GPU images — building locally for ${cuda_ver}"
        elif pull_image "${target}" "${tag}" "${cuda_ver}"; then
            return 0
        else
            log_info "Falling back to local build..."
        fi
        echo "" >&2
    fi
    
    log_info "Building Docker image locally: ${tag}"
    if [ "${target}" = "gpu" ]; then
        log_info "CUDA version: ${cuda_ver}"
    fi
    log_info "This may take 10-30 minutes on first build..."
    
    cd "${PROJECT_ROOT}"
    
    # Check for .dockerignore
    if [ ! -f "docker/.dockerignore" ]; then
        log_warn ".dockerignore not found - build context may be large"
    fi
    
    local build_args=()
    if [ "${target}" = "gpu" ]; then
        build_args=(--build-arg "CUDA_VERSION=${cuda_ver}")
    fi
    
    if docker build -t "${tag}" -f docker/Dockerfile --target "${target}" "${build_args[@]}" .; then
        log_success "Image built successfully: ${tag}"
    else
        log_error "Failed to build image"
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Create CLI Wrapper Scripts
# ------------------------------------------------------------------------------
create_wrapper() {
    local cmd_name="$1"
    local runner_script="$2"
    local target="$3"
    local perm_mode="$4"
    local cuda_ver="$5"
    local wrapper_path="${INSTALL_DIR}/${cmd_name}"
    local image_tag
    
    if [ "${target}" = "gpu" ]; then
        image_tag="${IMAGE_NAME}:gpu-${cuda_ver}"
    else
        image_tag="${IMAGE_NAME}:${target}"
    fi
    
    log_info "Creating wrapper: ${cmd_name} (image: ${image_tag})"
    
    # Create wrapper in temp location first
    # Register for cleanup in case of interruption
    _CLEANUP_FILES+=("/tmp/${cmd_name}")
    cat > "/tmp/${cmd_name}" << 'WRAPPER_EOF'
#!/bin/bash
# ==============================================================================
# WRAPPER_CMD_NAME - UVR Headless Runner CLI Wrapper
# ==============================================================================
# Auto-generated by install.sh
# Image: WRAPPER_IMAGE
# ==============================================================================

set -e

# Configuration
IMAGE="WRAPPER_IMAGE"
MODELS_DIR="${UVR_MODELS_DIR:-WRAPPER_MODELS_DIR}"

# Ensure models directory exists
mkdir -p "${MODELS_DIR}"

# Process arguments to handle file paths
DOCKER_ARGS=()
MOUNT_ARGS=()
PROCESSED_ARGS=()

# Track mounted directories with their modes using parallel indexed arrays.
# FIX (mount-mode upgrade): The old code only tracked whether a directory was
# mounted, not its mode.  If -i (ro) was processed before -o (rw) and both
# resolved to the SAME directory (e.g. input file lives in the output dir),
# the directory was mounted as :ro and the -o handler silently skipped it.
# This caused "No write permission for output directory" inside the container.
#
# New approach: three parallel arrays store host dir, container dir, and mode.
# _track_mount() allows upgrading ro→rw.  After all arguments are parsed,
# MOUNT_ARGS is rebuilt from these arrays with the final (correct) modes.
#
# Uses indexed arrays (Bash 2+) — no associative arrays needed.
_MOUNT_HOST_DIRS=()
_MOUNT_CONTAINER_DIRS=()
_MOUNT_MODES=()

# Track the output directory's container-side path for pre-flight write test.
# Set when -o/--output is parsed; used before exec to verify writability.
_OUTPUT_DOCKER_DIR=""

# Find index of a tracked directory; prints index or -1.
_find_mount_index() {
    local dir="$1"
    local i
    for i in "${!_MOUNT_HOST_DIRS[@]}"; do
        if [ "${_MOUNT_HOST_DIRS[$i]}" = "$dir" ]; then
            echo "$i"
            return 0
        fi
    done
    echo "-1"
    return 1
}

# Add a new mount or upgrade an existing ro mount to rw.
_track_mount() {
    local dir="$1"
    local mode="$2"  # "ro" or "rw"
    local idx
    idx="$(_find_mount_index "$dir")" || true
    if [ "$idx" -ge 0 ]; then
        # Already tracked — upgrade ro→rw if needed (rw is superset of ro)
        if [ "${_MOUNT_MODES[$idx]}" = "ro" ] && [ "$mode" = "rw" ]; then
            _MOUNT_MODES[$idx]="rw"
        fi
    else
        _MOUNT_HOST_DIRS+=("$dir")
        _MOUNT_CONTAINER_DIRS+=("$dir")
        _MOUNT_MODES+=("$mode")
    fi
}

# FIX: process_path stores its result in _RESOLVED_PATH (global variable)
# instead of echoing it. This avoids calling it inside $() command
# substitution, which creates a subshell where all side effects
# (_MOUNT_HOST_DIRS, _MOUNT_MODES modifications) would be silently lost.
# The old code called: PROCESSED_ARGS+=("$(process_path "$1" "ro")")
# which meant MOUNT_ARGS was ALWAYS empty — no directories were ever
# mounted into the container, breaking all input/output file access.
_RESOLVED_PATH=""

process_path() {
    local path="$1"
    local mode="$2"  # "ro" for input, "rw" for output
    
    # Skip if not a path
    if [[ ! "$path" =~ ^[./~] ]] && [[ ! "$path" =~ ^/ ]]; then
        _RESOLVED_PATH="$path"
        return
    fi
    
    # Expand path
    local abs_path
    if [[ "$path" = /* ]]; then
        abs_path="$path"
    elif [[ "$path" = ~* ]]; then
        abs_path="${path/#\~/$HOME}"
    else
        abs_path="$(cd "$(dirname "$path")" 2>/dev/null && pwd)/$(basename "$path")" || abs_path="$path"
    fi
    
    # Get directory
    local dir
    if [ -d "$abs_path" ]; then
        dir="$abs_path"
    else
        dir="$(dirname "$abs_path")"
    fi
    
    # Create directory if output
    if [ "$mode" = "rw" ] && [ ! -d "$dir" ]; then
        mkdir -p "$dir" 2>/dev/null || true
    fi
    
    # Track mount (add or upgrade ro→rw) if directory exists
    if [ -d "$dir" ]; then
        _track_mount "$dir" "$mode"
    fi
    
    _RESOLVED_PATH="$abs_path"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--input)
            PROCESSED_ARGS+=("$1")
            shift
            if [[ $# -gt 0 ]]; then
                process_path "$1" "ro"
                PROCESSED_ARGS+=("${_RESOLVED_PATH}")
                shift
            fi
            ;;
        -o|--output)
            PROCESSED_ARGS+=("$1")
            shift
            if [[ $# -gt 0 ]]; then
                process_path "$1" "rw"
                PROCESSED_ARGS+=("${_RESOLVED_PATH}")
                # Remember output dir for pre-flight write test
                _OUTPUT_DOCKER_DIR="${_RESOLVED_PATH}"
                shift
            fi
            ;;
        *)
            PROCESSED_ARGS+=("$1")
            shift
            ;;
    esac
done

# Build MOUNT_ARGS from tracked directories (final modes applied).
# This MUST happen after the argument-parsing loop so that any ro→rw
# upgrades (e.g. same dir used for both -i and -o) are already resolved.
MOUNT_ARGS=()
for _mi in "${!_MOUNT_HOST_DIRS[@]}"; do
    MOUNT_ARGS+=("-v" "${_MOUNT_HOST_DIRS[$_mi]}:${_MOUNT_CONTAINER_DIRS[$_mi]}:${_MOUNT_MODES[$_mi]}")
done

# Build docker run command
# Use -it only if running in a terminal
if [ -t 0 ] && [ -t 1 ]; then
    DOCKER_CMD=(docker run --rm -it)
else
    DOCKER_CMD=(docker run --rm)
fi
WRAPPER_EOF

    # Add GPU flags conditionally
    if [ "${target}" = "gpu" ]; then
        cat >> "/tmp/${cmd_name}" << 'GPU_EOF'
DOCKER_CMD+=(--gpus all)
GPU_EOF
    fi

    cat >> "/tmp/${cmd_name}" << 'END_EOF'
# Ensure host.docker.internal resolves on all platforms.
# Docker Desktop (macOS/Windows) resolves it natively; Linux needs --add-host.
# This is essential for host-based proxies (e.g., Clash, V2Ray on 127.0.0.1).
DOCKER_CMD+=(--add-host=host.docker.internal:host-gateway)

DOCKER_CMD+=(-v "${MODELS_DIR}:/models")
DOCKER_CMD+=("${MOUNT_ARGS[@]}")
DOCKER_CMD+=(-e "UVR_MODELS_DIR=/models")

# ── Proxy Passthrough ──────────────────────────────────────────────
# Rewrite localhost proxy addresses for Docker container access.
# Inside a container, 127.0.0.1/localhost refers to the container itself,
# not the host. We rewrite to host.docker.internal so the proxy is reachable.
# SECURITY: Values are passed but not logged (may contain credentials).
_rewrite_proxy() {
    local val="$1"
    [ -z "$val" ] && return
    # Regex handles: http://, https://, socks4://, socks5://, socks5h:// protocols
    # and optional user:pass@ authentication before the host address.
    # Examples matched:
    #   http://127.0.0.1:7890         → http://host.docker.internal:7890
    #   http://user:pass@localhost:80  → http://user:pass@host.docker.internal:80
    #   socks5://127.0.0.1:1080       → socks5://host.docker.internal:1080
    #   http://10.0.0.1:8080          → unchanged (not localhost)
    echo "$val" | sed -E 's@(://([^@]*@)?)(127\.0\.0\.1|localhost|\[::1\])@\1host.docker.internal@g'
}

# HTTP/HTTPS Proxy (both uppercase and lowercase for maximum compatibility)
if [ -n "${HTTP_PROXY:-}" ]; then
    DOCKER_CMD+=(-e "HTTP_PROXY=$(_rewrite_proxy "${HTTP_PROXY}")")
fi
if [ -n "${HTTPS_PROXY:-}" ]; then
    DOCKER_CMD+=(-e "HTTPS_PROXY=$(_rewrite_proxy "${HTTPS_PROXY}")")
fi
[ -n "${NO_PROXY:-}" ] && DOCKER_CMD+=(-e "NO_PROXY=${NO_PROXY}")
if [ -n "${http_proxy:-}" ]; then
    DOCKER_CMD+=(-e "http_proxy=$(_rewrite_proxy "${http_proxy}")")
fi
if [ -n "${https_proxy:-}" ]; then
    DOCKER_CMD+=(-e "https_proxy=$(_rewrite_proxy "${https_proxy}")")
fi
[ -n "${no_proxy:-}" ] && DOCKER_CMD+=(-e "no_proxy=${no_proxy}")
# ALL_PROXY: used by curl, git, and other tools as SOCKS/general proxy fallback
if [ -n "${ALL_PROXY:-}" ]; then
    DOCKER_CMD+=(-e "ALL_PROXY=$(_rewrite_proxy "${ALL_PROXY}")")
fi
if [ -n "${all_proxy:-}" ]; then
    DOCKER_CMD+=(-e "all_proxy=$(_rewrite_proxy "${all_proxy}")")
fi

DOCKER_CMD+=("${IMAGE}")
DOCKER_CMD+=(WRAPPER_RUNNER)
DOCKER_CMD+=("${PROCESSED_ARGS[@]}")

# Debug mode (proxy vars are intentionally excluded from debug output for security)
if [ -n "${UVR_DEBUG}" ]; then
    echo "Docker command: ${DOCKER_CMD[*]}" >&2
fi

# ── Pre-flight: verify output directory is writable inside container ──
# Spins up a throw-away container with the SAME volume mounts and attempts a
# test write.  This catches mount-mode mistakes (:ro vs :rw), host permission
# issues, and SELinux/AppArmor blocks BEFORE PyTorch and models are loaded —
# saving minutes of wasted startup time.
if [ -n "${_OUTPUT_DOCKER_DIR}" ]; then
    _WRITE_TEST="${_OUTPUT_DOCKER_DIR}/.uvr_write_test_$$"
    if ! docker run --rm \
            "${MOUNT_ARGS[@]}" \
            --entrypoint sh \
            "${IMAGE}" \
            -c "touch '${_WRITE_TEST}' && rm -f '${_WRITE_TEST}'" 2>/dev/null; then
        echo "" >&2
        echo "ERROR: Output directory is not writable inside the container:" >&2
        echo "  ${_OUTPUT_DOCKER_DIR}" >&2
        echo "" >&2
        echo "Possible causes:" >&2
        echo "  1. Volume mounted as read-only (:ro instead of :rw)" >&2
        echo "  2. Host directory permissions do not allow Docker to write" >&2
        echo "  3. SELinux/AppArmor blocking container writes (try :z suffix)" >&2
        echo "" >&2
        echo "Tip: re-run with UVR_DEBUG=1 to see the full docker command." >&2
        exit 1
    fi
fi

# Run container
exec "${DOCKER_CMD[@]}"
END_EOF

    # Replace placeholders using portable sed function
    # FIX: Escape sed/perl special characters in MODELS_DIR to handle paths
    # containing regex metacharacters (+, [, ], etc.) from user-provided UVR_MODELS_DIR
    local escaped_models_dir
    escaped_models_dir=$(printf '%s' "${MODELS_DIR}" | sed 's/[&/\|]/\\&/g')
    sed_inplace "s|WRAPPER_CMD_NAME|${cmd_name}|g" "/tmp/${cmd_name}"
    sed_inplace "s|WRAPPER_IMAGE|${image_tag}|g" "/tmp/${cmd_name}"
    sed_inplace "s|WRAPPER_MODELS_DIR|${escaped_models_dir}|g" "/tmp/${cmd_name}"
    sed_inplace "s|WRAPPER_RUNNER|${runner_script}|g" "/tmp/${cmd_name}"

    # Install wrapper based on permission mode
    case "$perm_mode" in
        direct)
            mv "/tmp/${cmd_name}" "${wrapper_path}"
            chmod +x "${wrapper_path}"
            ;;
        sudo)
            sudo mv "/tmp/${cmd_name}" "${wrapper_path}"
            sudo chmod +x "${wrapper_path}"
            ;;
        *)
            log_error "Cannot install to ${INSTALL_DIR} - no write permission and sudo not available"
            log_info "Try setting UVR_INSTALL_DIR to a writable directory:"
            log_info "  UVR_INSTALL_DIR=\$HOME/.local/bin ./docker/install.sh"
            rm -f "/tmp/${cmd_name}"
            exit 1
            ;;
    esac
    
    log_success "Installed: ${wrapper_path}"
}

# ------------------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------------------
uninstall() {
    log_info "Uninstalling UVR CLI wrappers..."
    
    local wrappers=("uvr" "uvr-mdx" "uvr-demucs" "uvr-vr")
    local perm_mode=$(check_install_permissions "${INSTALL_DIR}")
    
    for wrapper in "${wrappers[@]}"; do
        local path="${INSTALL_DIR}/${wrapper}"
        if [ -f "${path}" ]; then
            case "$perm_mode" in
                direct)
                    rm -f "${path}"
                    ;;
                sudo)
                    sudo rm -f "${path}"
                    ;;
                *)
                    log_warn "Cannot remove ${path} - no permission"
                    continue
                    ;;
            esac
            log_success "Removed: ${path}"
        fi
    done
    
    log_info "Uninstallation complete."
    log_info "Note: Docker images and model cache were not removed."
    echo "" >&2
    echo "To remove Docker images:" >&2
    echo "  docker images | grep '${IMAGE_NAME}' | awk '{print \$1\":\"\$2}' | xargs -r docker rmi" >&2
    echo "" >&2
    echo "To remove model cache:" >&2
    echo "  rm -rf ${MODELS_DIR}" >&2
}

# ------------------------------------------------------------------------------
# Main Installation
# ------------------------------------------------------------------------------
install() {
    local target="$1"
    local cuda_ver="${CUDA_VERSION}"
    
    print_banner
    
    # Warn if running under sudo — models dir and wrappers may behave differently
    if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        log_info "Running under sudo (real user: ${SUDO_USER})"
        log_info "Models directory will be: ${MODELS_DIR}"
    fi
    
    # Check prerequisites
    check_docker
    
    # Validate CUDA version
    case "${cuda_ver}" in
        cu121|cu124|cu128)
            ;;
        *)
            log_error "Invalid CUDA version: ${cuda_ver}"
            log_info "Valid options: cu121, cu124, cu128"
            exit 1
            ;;
    esac
    
    # Check installation permissions
    log_info "Checking installation permissions..."
    local perm_mode=$(check_install_permissions "${INSTALL_DIR}")
    
    if [ "$perm_mode" = "none" ]; then
        log_error "Cannot write to ${INSTALL_DIR} and sudo is not available"
        log_info "Option 1: Run with sudo: sudo ./docker/install.sh"
        log_info "Option 2: Set custom install directory:"
        log_info "  UVR_INSTALL_DIR=\$HOME/.local/bin ./docker/install.sh"
        exit 1
    fi
    
    if [ "$perm_mode" = "sudo" ]; then
        log_info "Will use sudo for installation to ${INSTALL_DIR}"
    fi
    
    # Auto-detect GPU if not specified
    if [ -z "${target}" ]; then
        log_info "Auto-detecting GPU support..."
        target=$(detect_gpu)
        # Final cleanup: remove any GPU test containers orphaned by a previous
        # interrupted run (e.g. script was killed with SIGKILL, or terminal was
        # closed during GPU detection). Safe to run every time — no-op if none exist.
        local leftover_gpu_containers
        leftover_gpu_containers=$(docker ps -aq --filter "ancestor=${GPU_TEST_IMAGE}" 2>/dev/null) || true
        if [ -n "${leftover_gpu_containers}" ]; then
            log_info "Cleaning up orphaned GPU test containers from previous run..."
            docker rm -f ${leftover_gpu_containers} > /dev/null 2>&1 || true
        fi
    fi
    
    echo "" >&2
    log_info "Installation mode: ${target}"
    if [ "${target}" = "gpu" ]; then
        log_info "CUDA version: ${cuda_ver}"
        case "${cuda_ver}" in
            cu121) log_info "Requires NVIDIA driver 530+" ;;
            cu124) log_info "Requires NVIDIA driver 550+" ;;
            cu128) log_info "Requires NVIDIA driver 560+" ;;
        esac
    fi
    echo "" >&2
    
    # Create models directory
    log_info "Creating models directory: ${MODELS_DIR}"
    mkdir -p "${MODELS_DIR}"
    mkdir -p "${MODELS_DIR}/VR_Models"
    mkdir -p "${MODELS_DIR}/MDX_Net_Models"
    mkdir -p "${MODELS_DIR}/Demucs_Models"
    
    # FIX: When running under sudo, mkdir creates directories owned by root.
    # The wrapper later runs as the normal user, and Docker mounts these as
    # bind volumes. The container runs as 'uvr' (uid 1000) which cannot write
    # to root-owned directories, causing all model downloads to fail with
    # "Permission denied". Restore ownership to the real user.
    if [ -n "${SUDO_USER:-}" ] && [ "${SUDO_USER}" != "root" ]; then
        local real_uid real_gid
        real_uid=$(id -u "${SUDO_USER}" 2>/dev/null) || real_uid=""
        real_gid=$(id -g "${SUDO_USER}" 2>/dev/null) || real_gid=""
        if [ -n "${real_uid}" ] && [ -n "${real_gid}" ]; then
            chown -R "${real_uid}:${real_gid}" "${MODELS_DIR}"
            log_info "Model directory ownership set to ${SUDO_USER} (uid:${real_uid})"
        else
            log_warn "Could not determine uid/gid for ${SUDO_USER}, models dir may have wrong ownership"
        fi
    fi
    
    log_success "Models directory created"
    
    # Build Docker image
    build_image "${target}" "${cuda_ver}"
    
    # Clean up dangling images from previous interrupted builds.
    # `docker build` leaves unnamed intermediate layers when interrupted (Ctrl+C,
    # network drop, OOM). These accumulate across repeated installs and waste disk.
    # This is safe and idempotent — only removes images with no tags and no children.
    local dangling
    dangling=$(docker images -qf "dangling=true" 2>/dev/null) || true
    if [ -n "${dangling}" ]; then
        log_info "Cleaning up dangling images from previous builds..."
        docker image prune -f > /dev/null 2>&1 || true
    fi
    
    # Create wrapper scripts
    log_info "Installing CLI wrappers to ${INSTALL_DIR}..."
    
    create_wrapper "uvr-mdx" "uvr-mdx" "${target}" "$perm_mode" "${cuda_ver}"
    create_wrapper "uvr-demucs" "uvr-demucs" "${target}" "$perm_mode" "${cuda_ver}"
    create_wrapper "uvr-vr" "uvr-vr" "${target}" "$perm_mode" "${cuda_ver}"
    create_wrapper "uvr" "uvr" "${target}" "$perm_mode" "${cuda_ver}"
    
    # Print success message
    echo "" >&2
    echo -e "${GREEN}=========================================================${NC}" >&2
    echo -e "${GREEN}            Installation Complete!                       ${NC}" >&2
    echo -e "${GREEN}=========================================================${NC}" >&2
    echo "" >&2
    echo -e "${CYAN}You can now use these commands:${NC}" >&2
    echo "" >&2
    echo "  uvr-mdx -m \"UVR-MDX-NET Inst HQ 3\" -i song.wav -o output/" >&2
    echo "  uvr-demucs -m htdemucs -i song.wav -o output/" >&2
    echo "  uvr-vr -m \"UVR-De-Echo-Normal\" -i song.wav -o output/" >&2
    echo "" >&2
    echo "  uvr mdx --list          # List MDX models" >&2
    echo "  uvr demucs --list       # List Demucs models" >&2
    echo "  uvr vr --list           # List VR models" >&2
    echo "  uvr info                # Show system info" >&2
    echo "" >&2
    echo -e "${CYAN}Models will be cached in: ${MODELS_DIR}${NC}" >&2
    echo "" >&2
    
    if [ "${target}" = "gpu" ]; then
        echo -e "${GREEN}GPU acceleration is enabled! (CUDA ${cuda_ver})${NC}" >&2
        echo "" >&2
        echo "CUDA compatibility:" >&2
        case "${cuda_ver}" in
            cu121) echo "  CUDA 12.1 - requires NVIDIA driver 530+" >&2 ;;
            cu124) echo "  CUDA 12.4 - requires NVIDIA driver 550+" >&2 ;;
            cu128) echo "  CUDA 12.8 - requires NVIDIA driver 560+" >&2 ;;
        esac
    else
        echo -e "${YELLOW}Running in CPU mode.${NC}" >&2
        echo "For GPU support, ensure NVIDIA drivers and nvidia-container-toolkit are installed." >&2
        echo "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html" >&2
    fi
    
    echo "" >&2
    echo "Debug mode: Set UVR_DEBUG=1 to see docker commands" >&2
}

# ------------------------------------------------------------------------------
# Parse Arguments
# ------------------------------------------------------------------------------
TARGET=""
ACTION="install"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cpu)
            TARGET="cpu"
            shift
            ;;
        --gpu)
            TARGET="gpu"
            shift
            ;;
        --cuda)
            TARGET="gpu"
            shift
            if [[ $# -gt 0 ]] && [[ "$1" != --* ]]; then
                CUDA_VERSION="$1"
                shift
            else
                log_error "--cuda requires a version argument (cu121, cu124, cu128)"
                exit 1
            fi
            ;;
        --uninstall|uninstall)
            ACTION="uninstall"
            shift
            ;;
        --build)
            FORCE_BUILD="1"
            shift
            ;;
        --help|-h)
            print_banner
            cat >&2 <<HELPEOF
Usage: $0 [OPTIONS]

Options:
  --cpu           Force CPU-only installation
  --gpu           Force GPU installation (uses default CUDA version)
  --cuda VERSION  GPU installation with specific CUDA version
                  VERSION: cu121, cu124 (default), cu128
  --build         Force local build instead of pulling from Docker Hub
  --uninstall     Remove installed CLI wrappers
  --help          Show this help message

Image Source:
  By default, the script pulls pre-built images from Docker Hub (fast!)
  Use --build to force local building (slower, but uses latest code)

CUDA Versions:
  cu121 - CUDA 12.1, requires NVIDIA driver 530+
  cu124 - CUDA 12.4, requires NVIDIA driver 550+ (default)
  cu128 - CUDA 12.8, requires NVIDIA driver 560+

Environment Variables:
  UVR_INSTALL_DIR    Installation directory (default: /usr/local/bin)
  UVR_MODELS_DIR     Model cache directory (default: ~/.uvr_models)
  UVR_CUDA_VERSION   CUDA version (default: cu124)
  UVR_FORCE_BUILD    Set to 1 to force local build
  UVR_DEBUG          Set to 1 to show debug output

Proxy Support (auto-passthrough if set):
  HTTP_PROXY         HTTP proxy URL (e.g., http://proxy:8080)
  HTTPS_PROXY        HTTPS proxy URL
  NO_PROXY           Comma-separated list of hosts to bypass proxy

Examples:
  # Quick install (pulls from Docker Hub)
  ./docker/install.sh

  # Install to user directory (no sudo needed)
  UVR_INSTALL_DIR=\$HOME/.local/bin ./docker/install.sh

  # Force local build with CUDA 12.1
  ./docker/install.sh --cuda cu121 --build

  # Install with custom model directory
  UVR_MODELS_DIR=/data/models ./docker/install.sh
HELPEOF
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Execute
case "${ACTION}" in
    install)
        install "${TARGET}"
        ;;
    uninstall)
        uninstall
        ;;
esac
