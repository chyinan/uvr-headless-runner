# ==============================================================================
# UVR Headless Runner - Windows Installation Script (PowerShell)
# ==============================================================================
# This script installs native-style CLI wrappers for Windows.
# By default, it pulls pre-built images from Docker Hub for fast installation.
#
# Usage:
#   .\docker\install.ps1                     # Quick install (pulls from Docker Hub)
#   .\docker\install.ps1 -Cpu                # Force CPU-only installation
#   .\docker\install.ps1 -Gpu                # Force GPU installation (CUDA 12.4)
#   .\docker\install.ps1 -Cuda cu121         # GPU with CUDA 12.1 (driver 530+)
#   .\docker\install.ps1 -Cuda cu124         # GPU with CUDA 12.4 (driver 550+, default)
#   .\docker\install.ps1 -Cuda cu128         # GPU with CUDA 12.8 (driver 560+)
#   .\docker\install.ps1 -Build              # Force local build (slower)
#   .\docker\install.ps1 -Uninstall          # Remove installed wrappers
#
# Image Source:
#   Default: Pulls pre-built images from Docker Hub (fast, ~2-5 min)
#   -Build:  Builds locally from source (slower, ~10-30 min)
#
# CUDA Version Options:
#   cu121 - CUDA 12.1, requires NVIDIA driver 530+
#   cu124 - CUDA 12.4, requires NVIDIA driver 550+ (default, recommended)
#   cu128 - CUDA 12.8, requires NVIDIA driver 560+
#
# ==============================================================================

param(
    [switch]$Cpu,
    [switch]$Gpu,
    [ValidateSet("cu121", "cu124", "cu128")]
    [string]$Cuda = "",
    [switch]$Build,        # Force local build instead of pulling from Docker Hub
    [switch]$Uninstall,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Configuration
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$InstallDir = if ($env:UVR_INSTALL_DIR) { $env:UVR_INSTALL_DIR } else { "$env:LOCALAPPDATA\UVR" }
$ModelsDir = if ($env:UVR_MODELS_DIR) { $env:UVR_MODELS_DIR } else { "$env:USERPROFILE\.uvr_models" }
$ImageName = "uvr-headless-runner"
# Docker Hub image for pre-built images (much faster!)
$DockerHubImage = "chyinan/uvr-headless-runner"
$DefaultCudaVersion = if ($env:UVR_CUDA_VERSION) { $env:UVR_CUDA_VERSION } else { "cu124" }
$ForceBuild = if ($env:UVR_FORCE_BUILD) { $true } else { $false }

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Blue }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-ErrorMsg { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# ------------------------------------------------------------------------------
# Robust Native Command Execution
# ------------------------------------------------------------------------------
# Replaces fragile Start-Process pattern. Uses System.Diagnostics.Process
# directly with async stream readers to prevent:
#   1. Deadlocks from synchronous stream reads filling OS pipe buffers
#   2. Null ExitCode from Start-Process + WaitForExit timing races
#   3. Stdout leakage into PowerShell's output pipeline
# Returns hashtable: @{ ExitCode; Stdout; Stderr; TimedOut }
function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)]
        [string]$FilePath,
        [string]$Arguments = "",
        [int]$TimeoutSeconds = 120
    )
    
    $proc = $null
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FilePath
        $psi.Arguments = $Arguments
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        
        $proc = [System.Diagnostics.Process]::Start($psi)
        
        # Read stdout/stderr asynchronously to prevent deadlock.
        # Synchronous ReadToEnd() blocks if the process writes more than the OS
        # pipe buffer (~4-64KB) to one stream while we're reading the other.
        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()
        
        $completed = $proc.WaitForExit($TimeoutSeconds * 1000)
        
        if (-not $completed) {
            try { $proc.Kill() } catch {}
            try { $proc.WaitForExit(10000) } catch {}
            $stdout = ""; $stderr = ""
            try { if ($stdoutTask.Wait(3000)) { $stdout = $stdoutTask.Result } } catch {}
            try { if ($stderrTask.Wait(3000)) { $stderr = $stderrTask.Result } } catch {}
            return @{
                ExitCode = 124
                Stdout   = $stdout
                Stderr   = $stderr
                TimedOut = $true
            }
        }
        
        # CRITICAL: Parameterless WaitForExit() after timed WaitForExit(ms).
        # The timed overload returns true when the process exits but BEFORE
        # async stream readers have flushed. Without this second call,
        # ExitCode and stream data may be incomplete.
        # Ref: https://learn.microsoft.com/dotnet/api/system.diagnostics.process.waitforexit
        $proc.WaitForExit()
        
        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
        $exitCode = $proc.ExitCode
        if ($null -eq $exitCode) { $exitCode = -1 }
        
        return @{
            ExitCode = $exitCode
            Stdout   = $stdout
            Stderr   = $stderr
            TimedOut = $false
        }
    } catch {
        return @{
            ExitCode = -1
            Stdout   = ""
            Stderr   = $_.Exception.Message
            TimedOut = $false
        }
    } finally {
        if ($proc) { try { $proc.Dispose() } catch {} }
    }
}

function Show-Banner {
    Write-Host ""
    Write-Host "=========================================================" -ForegroundColor Cyan
    Write-Host "       UVR Headless Runner - Windows Installation        " -ForegroundColor Cyan
    Write-Host "=========================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Get-CudaDriverRequirement {
    param([string]$CudaVersion)
    switch ($CudaVersion) {
        "cu121" { return "530+" }
        "cu124" { return "550+" }
        "cu128" { return "560+" }
        default { return "unknown" }
    }
}

# Returns a hashtable: @{ Available = $bool; Reason = "ok"|"not_installed"|"no_permission"|"not_running"|"unknown" }
function Test-Docker {
    # Step 1: Check if docker binary exists
    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) {
        return @{ Available = $false; Reason = "not_installed" }
    }
    
    # Step 2: Run docker info and capture output for diagnosis
    # FIX: Differentiate between "not running", "no permission", and other errors
    # so the user gets specific, actionable guidance.
    $savedErrorPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = docker info 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) {
            return @{ Available = $true; Reason = "ok" }
        }
        
        # Classify the failure
        if ($output -match "(?i)access denied|permission denied|Access is denied") {
            return @{ Available = $false; Reason = "no_permission" }
        }
        if ($output -match "(?i)cannot connect|connection refused|error during connect|daemon.*not running") {
            return @{ Available = $false; Reason = "not_running" }
        }
        return @{ Available = $false; Reason = "unknown"; Detail = $output.Trim() }
    } catch {
        return @{ Available = $false; Reason = "unknown"; Detail = $_.Exception.Message }
    } finally {
        $ErrorActionPreference = $savedErrorPref
    }
}

# ==============================================================================
# GPU Auto-Configuration Pipeline (Self-Healing)
# ==============================================================================
# This pipeline replaces the old passive Test-GpuSupport with an active,
# self-healing system that:
#   1. Validates host GPU hardware (nvidia-smi + driver version)
#   2. Ensures WSL2 is available (auto-enables if admin)
#   3. Ensures Docker Desktop uses WSL2 backend (auto-configures)
#   4. Runs GPU passthrough test with failure classification
#   5. Auto-fixes detected issues and retries
#   6. Only falls back to CPU after all auto-fixes are exhausted
# ==============================================================================

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Get NVIDIA driver version and GPU name via nvidia-smi
# Returns: @{ DriverVersion; GpuName; Error } or $null if nvidia-smi missing
function Get-NvidiaDriverInfo {
    $nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidiaSmi) { return $null }
    
    $result = Invoke-NativeCommand -FilePath "nvidia-smi" `
        -Arguments "--query-gpu=driver_version,name --format=csv,noheader,nounits" `
        -TimeoutSeconds 15
    
    if ($result.ExitCode -ne 0) {
        return @{ DriverVersion = ""; GpuName = ""; Error = "nvidia-smi exit code $($result.ExitCode): $($result.Stderr)" }
    }
    
    # CRITICAL: Wrap in @() to force array. Without this, a single-line result
    # is unwrapped to [string], and [string][0] returns [System.Char] which
    # has no .Split() method — causing "不包含名为 Split 的方法" error.
    $lines = @($result.Stdout.Trim().Split("`n") | Where-Object { $_.Trim() })
    if ($lines.Count -eq 0) { return @{ DriverVersion = ""; GpuName = ""; Error = "No output from nvidia-smi" } }
    
    $parts = @($lines[0].Split(",") | ForEach-Object { $_.Trim() })
    return @{
        DriverVersion = if ($parts.Count -gt 0) { $parts[0] } else { "" }
        GpuName       = if ($parts.Count -gt 1) { $parts[1] } else { "Unknown" }
        Error         = ""
    }
}

# Check WSL2 availability without requiring admin privileges
# Returns: @{ Available; Reason; Detail }
function Test-WSL2Available {
    $wslCmd = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wslCmd) {
        return @{ Available = $false; Reason = "wsl_not_installed"; Detail = "wsl.exe not found in PATH" }
    }
    
    # wsl --version succeeds if WSL2 kernel is properly installed (Win 10 21H2+, Win 11)
    $result = Invoke-NativeCommand -FilePath "wsl.exe" -Arguments "--version" -TimeoutSeconds 15
    if ($result.ExitCode -eq 0 -and $result.Stdout.Trim()) {
        return @{ Available = $true; Reason = "ok"; Detail = $result.Stdout.Trim() }
    }
    
    # Fallback: wsl --status may work on older Windows 10 builds
    $result2 = Invoke-NativeCommand -FilePath "wsl.exe" -Arguments "--status" -TimeoutSeconds 15
    if ($result2.ExitCode -eq 0 -and $result2.Stdout.Trim()) {
        return @{ Available = $true; Reason = "ok"; Detail = $result2.Stdout.Trim() }
    }
    
    $detail = ("$($result.Stderr) $($result2.Stderr)").Trim()
    return @{
        Available = $false
        Reason    = "wsl2_not_ready"
        Detail    = if ($detail) { $detail } else { "WSL2 kernel not installed or not functional" }
    }
}

# Auto-enable WSL2 (requires admin). Handles both wsl --install and DISM fallback.
# Returns: $true if WSL2 is now available, $false otherwise
function Enable-WSL2 {
    if (-not (Test-IsAdmin)) {
        Write-Warn "WSL2 auto-enablement requires Administrator privileges"
        Write-Warn "Option 1: Re-run this script as Administrator"
        Write-Warn "Option 2: Manually run:  wsl --install --no-distribution"
        return $false
    }
    
    Write-Info "Installing/updating WSL2 (this may take a minute)..."
    
    # Primary method: wsl --install --no-distribution
    # Installs WSL2 kernel + features without a default Linux distro
    # (Docker Desktop manages its own internal WSL2 distributions)
    $result = Invoke-NativeCommand -FilePath "wsl.exe" -Arguments "--install --no-distribution" -TimeoutSeconds 300
    
    if ($result.ExitCode -ne 0) {
        Write-Info "wsl --install returned exit code $($result.ExitCode), trying DISM fallback..."
        
        # Fallback: enable features manually via DISM (for older Windows 10 builds)
        $dism1 = Invoke-NativeCommand -FilePath "dism.exe" `
            -Arguments "/online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart" `
            -TimeoutSeconds 120
        
        $dism2 = Invoke-NativeCommand -FilePath "dism.exe" `
            -Arguments "/online /enable-feature /featurename:VirtualMachinePlatform /all /norestart" `
            -TimeoutSeconds 120
        
        # 0 = success, 3010 = success but reboot needed
        $dism1ok = ($dism1.ExitCode -eq 0 -or $dism1.ExitCode -eq 3010)
        $dism2ok = ($dism2.ExitCode -eq 0 -or $dism2.ExitCode -eq 3010)
        
        if (-not $dism1ok -or -not $dism2ok) {
            Write-Warn "Failed to enable WSL features via DISM"
            if (-not $dism1ok) { Write-Warn "  WSL feature: exit $($dism1.ExitCode) — $($dism1.Stderr.Trim())" }
            if (-not $dism2ok) { Write-Warn "  VM Platform: exit $($dism2.ExitCode) — $($dism2.Stderr.Trim())" }
            return $false
        }
        
        # Set WSL2 as default version
        $null = Invoke-NativeCommand -FilePath "wsl.exe" -Arguments "--set-default-version 2" -TimeoutSeconds 30
    }
    
    # Verify installation (give it a moment to register)
    Start-Sleep -Seconds 3
    $check = Test-WSL2Available
    if ($check.Available) {
        Write-Success "WSL2 is now available"
        return $true
    }
    
    # Check if reboot is needed (match both English and Chinese locale strings)
    $allOutput = "$($result.Stdout) $($result.Stderr)"
    if ($allOutput -match "(?i)restart|reboot|重启|重新启动" -or $result.ExitCode -eq 3010) {
        Write-Warn "A system restart is required to complete WSL2 installation"
        Write-Warn "Please restart your computer and re-run this installer"
        return $false
    }
    
    Write-Warn "WSL2 installation completed but verification failed"
    Write-Warn "A restart may be required. Detail: $($check.Detail)"
    return $false
}

# Check if Docker Desktop is using WSL2 backend
# Returns: $true, $false, or $null if unknown
function Test-DockerWSL2Backend {
    # Primary: check Docker Desktop settings.json directly
    $settingsPath = "$env:APPDATA\Docker\settings.json"
    if (Test-Path $settingsPath) {
        try {
            $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
            if ($null -ne $settings.wslEngineEnabled) {
                return [bool]$settings.wslEngineEnabled
            }
        } catch {
            Write-Warn "Could not parse Docker Desktop settings.json: $_"
        }
    }
    
    # Fallback: check docker info output for WSL2 indicators
    $result = Invoke-NativeCommand -FilePath "docker" -Arguments "info" -TimeoutSeconds 15
    if ($result.ExitCode -eq 0) {
        if ($result.Stdout -match "(?i)Operating System.*linux" -or $result.Stdout -match "(?i)wsl") {
            return $true
        }
    }
    
    return $null  # unknown
}

# Enable Docker Desktop WSL2 backend by modifying settings.json
# Returns: $true if enabled (restart needed), $false if failed
function Enable-DockerWSL2Backend {
    $settingsPath = "$env:APPDATA\Docker\settings.json"
    if (-not (Test-Path $settingsPath)) {
        Write-Warn "Docker Desktop settings.json not found at: $settingsPath"
        Write-Warn "Please enable WSL2 backend manually: Docker Desktop > Settings > General > Use WSL 2"
        return $false
    }
    
    try {
        $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
        if ($settings.wslEngineEnabled -eq $true) {
            Write-Info "Docker Desktop WSL2 backend is already enabled"
            return $true
        }
        
        Write-Info "Enabling WSL2 backend in Docker Desktop settings..."
        $settings.wslEngineEnabled = $true
        $settings | ConvertTo-Json -Depth 10 | Set-Content $settingsPath -Encoding UTF8
        Write-Success "WSL2 backend enabled in settings (Docker restart required)"
        return $true
    } catch {
        Write-Warn "Failed to modify Docker Desktop settings: $_"
        return $false
    }
}

# Restart Docker Desktop and wait for it to become ready.
# Handles process discovery, graceful shutdown, and readiness polling.
# Returns: $true if Docker is ready, $false if timed out
function Restart-DockerDesktop {
    param([int]$MaxWaitSeconds = 120)
    
    Write-Info "Restarting Docker Desktop..."
    
    # Discover Docker Desktop executable
    $dockerPath = $null
    $searchPaths = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    )
    
    # Try to get path from running process first
    $runningProc = Get-Process "Docker Desktop" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($runningProc) {
        try { $dockerPath = $runningProc.Path } catch {}
    }
    
    if (-not $dockerPath) {
        foreach ($p in $searchPaths) {
            if (Test-Path $p) { $dockerPath = $p; break }
        }
    }
    
    if (-not $dockerPath -or -not (Test-Path $dockerPath)) {
        Write-Warn "Docker Desktop executable not found — please restart Docker Desktop manually"
        return $false
    }
    
    # Gracefully stop all Docker Desktop processes
    $processNames = @("Docker Desktop", "com.docker.backend", "com.docker.proxy", "com.docker.service")
    $stoppedAny = $false
    foreach ($procName in $processNames) {
        Get-Process -Name $procName -ErrorAction SilentlyContinue | ForEach-Object {
            try { $_.Kill(); $stoppedAny = $true } catch {}
        }
    }
    
    if ($stoppedAny) {
        Write-Info "Waiting for Docker to fully stop..."
        Start-Sleep -Seconds 5
    }
    
    # Start Docker Desktop
    Write-Info "Starting Docker Desktop: $dockerPath"
    Start-Process -FilePath $dockerPath -WindowStyle Minimized
    
    # Poll for Docker readiness
    Write-Info "Waiting for Docker to initialize (up to ${MaxWaitSeconds}s)..."
    $waited = 0
    $interval = 3
    while ($waited -lt $MaxWaitSeconds) {
        Start-Sleep -Seconds $interval
        $waited += $interval
        
        $check = Invoke-NativeCommand -FilePath "docker" -Arguments "info" -TimeoutSeconds 10
        if ($check.ExitCode -eq 0) {
            Write-Success "Docker Desktop is ready (took ${waited}s)"
            return $true
        }
        
        if ($waited % 15 -eq 0) {
            Write-Info "Still waiting for Docker... (${waited}/${MaxWaitSeconds}s)"
        }
    }
    
    Write-Warn "Docker Desktop did not become ready within ${MaxWaitSeconds}s"
    return $false
}

# Classify GPU test failure from docker stderr output.
# Returns a structured reason string for the self-healing loop.
function Get-GpuFailureReason {
    param([string]$Stderr, [int]$ExitCode)
    
    if ($ExitCode -eq 124) { return "timeout" }
    
    $s = if ($Stderr) { $Stderr.ToLower() } else { "" }
    
    # Runtime not configured (--gpus flag not recognized or no GPU runtime)
    if ($s -match "could not select device driver|unknown.*flag.*gpus|invalid reference format") {
        return "runtime_missing"
    }
    # Permission denied
    if ($s -match "permission denied|access denied|access is denied") {
        return "permission_denied"
    }
    # WSL-related failures
    if ($s -match "wsl|windows subsystem") {
        return "wsl_error"
    }
    # Docker daemon not running
    if ($s -match "cannot connect|connection refused|daemon.*not running|error during connect") {
        return "docker_not_running"
    }
    # NVIDIA driver/CUDA version mismatch
    if ($s -match "cuda|driver.*version|insufficient.*driver|nvml|failed to initialize") {
        return "driver_mismatch"
    }
    # Image not found
    if ($s -match "no such image|manifest unknown|not found") {
        return "image_missing"
    }
    # OCI/nvidia runtime errors
    if ($s -match "oci runtime|nvidia-container|libnvidia") {
        return "nvidia_runtime_error"
    }
    
    return "unknown"
}

# Run a single GPU passthrough test with full stdout/stderr capture.
# Uses Invoke-NativeCommand for guaranteed exit code + stream capture.
# Returns structured result hashtable.
function Invoke-GpuPassthroughTest {
    param(
        [string]$TestImage = "nvidia/cuda:12.4.1-base-ubuntu22.04",
        [int]$TimeoutSeconds = 60
    )
    
    $result = Invoke-NativeCommand -FilePath "docker" `
        -Arguments "run --rm --gpus all $TestImage nvidia-smi" `
        -TimeoutSeconds $TimeoutSeconds
    
    $reason = if ($result.ExitCode -eq 0) { "success" } else {
        Get-GpuFailureReason -Stderr $result.Stderr -ExitCode $result.ExitCode
    }
    
    return @{
        Success       = ($result.ExitCode -eq 0)
        ExitCode      = $result.ExitCode
        Stdout        = $result.Stdout
        Stderr        = $result.Stderr
        TimedOut      = $result.TimedOut
        FailureReason = $reason
    }
}

# ==============================================================================
# Main GPU Detection: Self-Healing Pipeline
# ==============================================================================
# This function orchestrates a multi-phase GPU detection and configuration
# pipeline. When a GPU test fails, it diagnoses the root cause and applies
# targeted auto-fixes before retrying. Only falls back to CPU after all
# auto-fix attempts are exhausted or the failure is non-recoverable.
# ==============================================================================
function Test-GpuSupport {
    $savedErrorPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    
    $GpuTestImage = "nvidia/cuda:12.4.1-base-ubuntu22.04"
    $MaxHealingAttempts = 3
    
    try {
        # ═══════════════════════════════════════════════════════════════
        # Phase 1: Host GPU Hardware Validation
        # ═══════════════════════════════════════════════════════════════
        
        $gpuInfo = Get-NvidiaDriverInfo
        if (-not $gpuInfo -or (-not $gpuInfo.DriverVersion)) {
            if ($gpuInfo -and $gpuInfo.Error) {
                Write-Warn "nvidia-smi failed: $($gpuInfo.Error)"
            } else {
                Write-Info "No NVIDIA GPU detected (nvidia-smi not found)"
            }
            return $false
        }
        
        Write-Info "NVIDIA GPU detected: $($gpuInfo.GpuName)"
        Write-Info "Driver version: $($gpuInfo.DriverVersion)"
        
        # Check minimum driver version for WSL2 CUDA support (470.76+)
        try {
            $driverMajor = [int]($gpuInfo.DriverVersion.Split(".")[0])
        } catch {
            Write-Warn "Could not parse driver version: $($gpuInfo.DriverVersion)"
            $driverMajor = 0
        }
        
        if ($driverMajor -gt 0 -and $driverMajor -lt 470) {
            Write-Warn "Driver $($gpuInfo.DriverVersion) is too old for WSL2 GPU passthrough"
            Write-Warn "Minimum required: 470.76+ (for basic CUDA), 530+ recommended"
            Write-Warn "Update from: https://www.nvidia.com/Download/index.aspx"
            return $false
        }
        
        Write-Info "Driver version meets WSL2 GPU requirements (470+)"
        
        # ═══════════════════════════════════════════════════════════════
        # Phase 2: WSL2 Prerequisite Check + Auto-Fix
        # ═══════════════════════════════════════════════════════════════
        
        $wslStatus = Test-WSL2Available
        if (-not $wslStatus.Available) {
            Write-Warn "WSL2 is not available (reason: $($wslStatus.Reason))"
            Write-Warn "Detail: $($wslStatus.Detail)"
            Write-Info "Attempting to auto-configure WSL2..."
            
            if (-not (Enable-WSL2)) {
                Write-Warn "Could not auto-configure WSL2 — GPU requires WSL2 on Windows"
                return $false
            }
        } else {
            Write-Info "WSL2 is available"
        }
        
        # ═══════════════════════════════════════════════════════════════
        # Phase 3: Docker Desktop WSL2 Backend Check + Auto-Fix
        # ═══════════════════════════════════════════════════════════════
        
        $wsl2Backend = Test-DockerWSL2Backend
        if ($wsl2Backend -eq $false) {
            Write-Warn "Docker Desktop is NOT using WSL2 backend (required for GPU)"
            Write-Info "Attempting to enable WSL2 backend..."
            
            if (Enable-DockerWSL2Backend) {
                Write-Info "Restarting Docker Desktop to apply WSL2 backend change..."
                if (-not (Restart-DockerDesktop -MaxWaitSeconds 120)) {
                    Write-Warn "Docker restart failed after WSL2 backend change"
                    return $false
                }
            } else {
                Write-Warn "Could not enable WSL2 backend automatically"
                Write-Warn "Please enable it manually: Docker Desktop > Settings > General > Use WSL 2"
                return $false
            }
        } elseif ($null -eq $wsl2Backend) {
            Write-Info "Could not determine Docker backend — proceeding with GPU test"
        } else {
            Write-Info "Docker Desktop is using WSL2 backend"
        }
        
        # ═══════════════════════════════════════════════════════════════
        # Phase 4: Ensure GPU Test Image is Available
        # ═══════════════════════════════════════════════════════════════
        
        $imageCheck = Invoke-NativeCommand -FilePath "docker" -Arguments "image inspect $GpuTestImage" -TimeoutSeconds 15
        if ($imageCheck.ExitCode -ne 0) {
            Write-Info "GPU test image not cached — pulling: $GpuTestImage"
            Write-Info "(one-time download, ~80 MB — please wait)"
            
            if (-not (Pull-WithRetry -Image $GpuTestImage -MaxRetries 3 -RetryDelay 5)) {
                Write-Warn "Failed to pull GPU test image"
                # Heuristic: compatible driver + WSL2 ready → probably fine
                if ($driverMajor -ge 470) {
                    Write-Info "Driver is compatible — proceeding with GPU mode optimistically"
                    return $true
                }
                Write-Warn "Cannot verify GPU passthrough — falling back to CPU"
                return $false
            }
        }
        
        # ═══════════════════════════════════════════════════════════════
        # Phase 5: Self-Healing GPU Passthrough Test Loop
        # ═══════════════════════════════════════════════════════════════
        
        Write-Info "Testing Docker GPU passthrough (docker run --gpus all)..."
        
        $fixesApplied = [System.Collections.Generic.List[string]]::new()
        
        for ($healAttempt = 1; $healAttempt -le $MaxHealingAttempts; $healAttempt++) {
            # Run the gold-standard GPU passthrough test
            $testResult = Invoke-GpuPassthroughTest -TestImage $GpuTestImage -TimeoutSeconds 60
            
            if ($testResult.Success) {
                Write-Success "Docker GPU passthrough verified!"
                if ($testResult.Stdout.Trim()) {
                    # Show nvidia-smi output for confirmation
                    $smiFirstLine = ($testResult.Stdout.Trim().Split("`n") | Select-Object -First 1).Trim()
                    if ($smiFirstLine) { Write-Info "nvidia-smi: $smiFirstLine" }
                }
                if ($fixesApplied.Count -gt 0) {
                    Write-Success "Auto-fixes applied: $($fixesApplied -join ', ')"
                }
                return $true
            }
            
            # ── Diagnose failure and attempt auto-fix ──
            $reason = $testResult.FailureReason
            Write-Warn "GPU test FAILED (attempt $healAttempt/$MaxHealingAttempts)"
            Write-Warn "  Exit code: $($testResult.ExitCode)"
            Write-Warn "  Reason: $reason"
            if ($testResult.Stderr.Trim()) {
                $errSnippet = $testResult.Stderr.Trim()
                if ($errSnippet.Length -gt 500) { $errSnippet = $errSnippet.Substring(0, 500) + "..." }
                Write-Warn "  Docker stderr: $errSnippet"
            }
            
            # Skip fixes we already tried
            if ($fixesApplied -contains $reason) {
                Write-Warn "Fix for '$reason' was already attempted — trying Docker restart as fallback"
                $reason = "needs_restart"
            }
            
            $fixed = $false
            switch ($reason) {
                "runtime_missing" {
                    # On Windows Docker Desktop, --gpus requires WSL2 backend + NVIDIA driver
                    # The nvidia-container-toolkit is built into Docker Desktop (no separate install)
                    Write-Info "GPU runtime not available — checking Docker Desktop WSL2 configuration..."
                    $fixesApplied.Add("runtime_missing")
                    if (Enable-DockerWSL2Backend) {
                        if (Restart-DockerDesktop -MaxWaitSeconds 120) { $fixed = $true }
                    }
                }
                "nvidia_runtime_error" {
                    Write-Info "NVIDIA container runtime error — restarting Docker Desktop..."
                    $fixesApplied.Add("nvidia_runtime_error")
                    if (Restart-DockerDesktop -MaxWaitSeconds 120) { $fixed = $true }
                }
                "docker_not_running" {
                    Write-Info "Docker is not running — starting Docker Desktop..."
                    $fixesApplied.Add("docker_not_running")
                    if (Restart-DockerDesktop -MaxWaitSeconds 120) { $fixed = $true }
                }
                "needs_restart" {
                    Write-Info "Restarting Docker Desktop for GPU re-initialization..."
                    $fixesApplied.Add("needs_restart")
                    if (Restart-DockerDesktop -MaxWaitSeconds 120) { $fixed = $true }
                }
                "timeout" {
                    # Clean up orphaned containers that may be holding GPU resources
                    $fixesApplied.Add("timeout")
                    $orphans = docker ps -aq --filter "ancestor=$GpuTestImage" 2>$null
                    if ($orphans) {
                        Write-Info "Cleaning up orphaned GPU test containers..."
                        docker rm -f $orphans 2>$null | Out-Null
                        Start-Sleep -Seconds 3
                    }
                    $fixed = $true  # just retry
                }
                "wsl_error" {
                    Write-Info "WSL-related GPU error — attempting WSL2 repair..."
                    $fixesApplied.Add("wsl_error")
                    if (Enable-WSL2) {
                        if (Restart-DockerDesktop -MaxWaitSeconds 120) { $fixed = $true }
                    }
                }
                "driver_mismatch" {
                    Write-Warn "NVIDIA driver/CUDA version mismatch — cannot auto-fix"
                    Write-Warn "Please update your NVIDIA driver: https://www.nvidia.com/Download/index.aspx"
                    break  # non-recoverable
                }
                "permission_denied" {
                    Write-Warn "Permission denied for GPU access"
                    if (-not (Test-IsAdmin)) {
                        Write-Warn "Try running this script as Administrator"
                    }
                    break  # non-recoverable without elevation
                }
                "image_missing" {
                    Write-Info "GPU test image missing — pulling..."
                    $fixesApplied.Add("image_missing")
                    if (Pull-WithRetry -Image $GpuTestImage -MaxRetries 3 -RetryDelay 5) {
                        $fixed = $true
                    }
                }
                default {
                    # Unknown failure — Docker restart is the universal fix attempt
                    Write-Info "Unknown failure — attempting Docker restart..."
                    $fixesApplied.Add("unknown_restart")
                    if (Restart-DockerDesktop -MaxWaitSeconds 120) { $fixed = $true }
                }
            }
            
            if (-not $fixed) {
                Write-Warn "Auto-fix for '$reason' was not successful — stopping retry loop"
                break
            }
            
            Write-Info "Retrying GPU test in 5s..."
            Start-Sleep -Seconds 5
        }
        
        # ═══════════════════════════════════════════════════════════════
        # Phase 6: All Auto-Fixes Exhausted — Diagnostic Summary
        # ═══════════════════════════════════════════════════════════════
        
        Write-Warn ""
        Write-Warn "================================================================"
        Write-Warn " GPU AUTO-CONFIGURATION FAILED — DIAGNOSTIC SUMMARY"
        Write-Warn "================================================================"
        Write-Warn ""
        Write-Warn "GPU:             $($gpuInfo.GpuName)"
        Write-Warn "Driver:          $($gpuInfo.DriverVersion)"
        Write-Warn "Admin:           $(if (Test-IsAdmin) { 'Yes' } else { 'No' })"
        Write-Warn "WSL2:            $($wslStatus.Reason)"
        Write-Warn "Docker Backend:  $(if ($wsl2Backend -eq $true) { 'WSL2' } elseif ($wsl2Backend -eq $false) { 'Hyper-V' } else { 'Unknown' })"
        Write-Warn "Fixes attempted: $(if ($fixesApplied.Count -gt 0) { $fixesApplied -join ', ' } else { 'none' })"
        Write-Warn ""
        Write-Warn "Manual troubleshooting:"
        Write-Warn "  1. Update NVIDIA driver (530+ recommended):"
        Write-Warn "       https://www.nvidia.com/Download/index.aspx"
        Write-Warn "  2. Ensure Docker Desktop uses WSL2 backend:"
        Write-Warn "       Docker Desktop > Settings > General > Use WSL 2 based engine"
        Write-Warn "  3. Restart Docker Desktop after any changes"
        Write-Warn "  4. Verify manually:"
        Write-Warn "       docker run --rm --gpus all $GpuTestImage nvidia-smi"
        Write-Warn ""
        Write-Warn "Falling back to CPU mode."
        Write-Info "Tip: use  .\docker\install.ps1 -Gpu  to force GPU mode"
        return $false
    } catch {
        Write-Warn "GPU detection pipeline error: $_"
        if ($_.ScriptStackTrace) {
            Write-Warn "  at: $($_.ScriptStackTrace.Split("`n")[0].Trim())"
        }
        return $false
    } finally {
        $ErrorActionPreference = $savedErrorPref
    }
}

# Convert Windows path to Docker-compatible path
# Docker Desktop on Windows accepts paths like /c/Users/... or //c/Users/...
function Convert-ToDockerPath {
    param([string]$WindowsPath)
    
    if ([string]::IsNullOrEmpty($WindowsPath)) {
        return $WindowsPath
    }
    
    # Get absolute path
    try {
        $absPath = (Resolve-Path $WindowsPath -ErrorAction Stop).Path
    } catch {
        # Path doesn't exist yet, try to make it absolute anyway
        $absPath = [System.IO.Path]::GetFullPath($WindowsPath)
    }
    
    # Convert backslashes to forward slashes
    $unixPath = $absPath -replace '\\', '/'
    
    # Convert drive letter: C:\... -> /c/...
    # Docker Desktop on Windows expects lowercase drive letter
    if ($unixPath -match '^([A-Za-z]):(.*)$') {
        $driveLetter = $Matches[1].ToLower()
        $pathRest = $Matches[2]
        $unixPath = "/$driveLetter$pathRest"
    }
    
    return $unixPath
}

# ------------------------------------------------------------------------------
# Pull helpers
# ------------------------------------------------------------------------------

# Retry wrapper for docker pull (handles flaky networks, partial failures, rate limits)
# FIX: Uses Start-Process instead of direct `docker pull $Image` invocation.
# Running docker directly in a PowerShell function causes docker's stdout to
# leak into the function's output pipeline, corrupting the boolean return value.
# For example, the function returns @("Status: Downloaded ...", $false) instead
# of just $false. A non-empty array evaluates as truthy in if-conditions, so a
# failed pull is silently treated as success — breaking the fallback-to-build logic.
# Start-Process -NoNewWindow sends output directly to the console (not the PS
# pipeline), -Wait blocks until done, -PassThru gives reliable ExitCode access.
function Pull-WithRetry {
    param(
        [string]$Image,
        [int]$MaxRetries = 3,
        [int]$RetryDelay = 5
    )
    
    $pullExitCode = -1
    
    for ($i = 1; $i -le $MaxRetries; $i++) {
        try {
            $proc = Start-Process -FilePath "docker" `
                -ArgumentList "pull $Image" `
                -NoNewWindow -Wait -PassThru
            
            $pullExitCode = $proc.ExitCode
            if ($null -eq $pullExitCode) { $pullExitCode = -1 }
            
            if ($pullExitCode -eq 0) { return $true }
        } catch {
            Write-Warn "Docker pull process error: $_"
            $pullExitCode = -1
        }
        
        if ($i -lt $MaxRetries) {
            Write-Warn "Pull failed (attempt $i/$MaxRetries, exit code: $pullExitCode), retrying in ${RetryDelay}s..."
            Start-Sleep -Seconds $RetryDelay
            $RetryDelay *= 2  # exponential back-off
        }
    }
    Write-Warn "Pull failed after $MaxRetries attempts (last exit code: $pullExitCode)"
    return $false
}

# ------------------------------------------------------------------------------
# Pull or Build Docker Image
# ------------------------------------------------------------------------------
function Pull-Image {
    param(
        [string]$Target,
        [string]$LocalTag,
        [string]$CudaVersion
    )
    
    # Protect native command stderr from triggering terminating errors
    # (same pattern as Test-GpuSupport — see detailed comment there)
    $savedErrorPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    
    try {
        # Map target to Docker Hub tag
        # NOTE: Docker Hub currently only publishes cu124 GPU images.
        if ($Target -eq "gpu") {
            $HubTag = "${DockerHubImage}:latest"
        } else {
            $HubTag = "${DockerHubImage}:latest-cpu"
        }
        
        Write-Info "Pulling pre-built image from Docker Hub: $HubTag"
        Write-Info "This is much faster than building locally!"
        
        if (Pull-WithRetry -Image $HubTag -MaxRetries 3 -RetryDelay 5) {
            # Tag the pulled image with our local tag for consistency
            # FIX: Assign to $null to prevent docker tag stdout from leaking
            # into Pull-Image's return value pipeline (same class of bug as
            # the Pull-WithRetry stdout leak — see detailed comment there).
            $null = docker tag $HubTag $LocalTag
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Image pulled but tagging as $LocalTag failed"
                return $false
            }
            Write-Success "Image pulled and tagged: $LocalTag"
            return $true
        } else {
            Write-Warn "Failed to pull from Docker Hub"
            return $false
        }
    } finally {
        $ErrorActionPreference = $savedErrorPref
    }
}

function Build-Image {
    param(
        [string]$Target,
        [string]$CudaVersion
    )
    
    if ($Target -eq "gpu") {
        $Tag = "${ImageName}:gpu-${CudaVersion}"
    } else {
        $Tag = "${ImageName}:${Target}"
    }
    
    # Try pulling from Docker Hub first (unless force build is set)
    # Docker Hub only has cu124 GPU images — other CUDA versions require local build
    if (-not $ForceBuild -and -not $Build) {
        if ($Target -eq "gpu" -and $CudaVersion -ne "cu124") {
            Write-Info "Docker Hub only has cu124 GPU images - building locally for $CudaVersion"
        } elseif (Pull-Image -Target $Target -LocalTag $Tag -CudaVersion $CudaVersion) {
            return
        } else {
            Write-Info "Falling back to local build..."
        }
        Write-Host ""
    }
    
    Write-Info "Building Docker image locally: $Tag"
    if ($Target -eq "gpu") {
        Write-Info "CUDA version: $CudaVersion (requires driver $(Get-CudaDriverRequirement $CudaVersion))"
    }
    Write-Info "This may take 10-30 minutes on first build..."
    
    # Protect native command stderr from triggering terminating errors
    # docker build writes progress/layer info to stderr — not actual errors
    $savedErrorPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    
    Push-Location $ProjectRoot
    try {
        # Check if .dockerignore exists, if not create it
        $dockerignorePath = Join-Path $ProjectRoot "docker\.dockerignore"
        if (-not (Test-Path $dockerignorePath)) {
            Write-Warn ".dockerignore not found - build context may be large"
        }
        
        $buildArgs = @()
        if ($Target -eq "gpu") {
            $buildArgs += "--build-arg"
            $buildArgs += "CUDA_VERSION=$CudaVersion"
        }
        
        docker build -t $Tag -f docker/Dockerfile --target $Target @buildArgs .
        if ($LASTEXITCODE -ne 0) {
            throw "Docker build failed with exit code $LASTEXITCODE"
        }
        Write-Success "Image built successfully: $Tag"
    } finally {
        Pop-Location
        $ErrorActionPreference = $savedErrorPref
    }
}

# ------------------------------------------------------------------------------
# Create CLI Wrapper Scripts
# ------------------------------------------------------------------------------
function New-Wrapper {
    param(
        [string]$CmdName,
        [string]$RunnerScript,
        [string]$Target,
        [string]$CudaVersion
    )
    
    $WrapperPath = Join-Path $InstallDir "$CmdName.cmd"
    $PsWrapperPath = Join-Path $InstallDir "$CmdName.ps1"
    
    # Determine image tag
    if ($Target -eq "gpu") {
        $ImageTag = "${ImageName}:gpu-${CudaVersion}"
    } else {
        $ImageTag = "${ImageName}:${Target}"
    }
    
    Write-Info "Creating wrapper: $CmdName (image: $ImageTag)"
    
    # GPU flags
    $GpuFlags = if ($Target -eq "gpu") { "--gpus all" } else { "" }
    
    # Convert ModelsDir to Docker path
    $ModelsDockerPath = Convert-ToDockerPath $ModelsDir
    
    # Create CMD wrapper — delegates to the PowerShell wrapper for correct path handling.
    # FIX: The old CMD wrapper only mounted the models volume and passed raw %* to
    # Docker without mounting input/output directories. This meant `uvr-mdx -i file.wav`
    # would ALWAYS fail because the file was never mounted into the container.
    # Delegation to the PS1 wrapper fixes this and also handles paths with spaces.
    $CmdContent = @"
@echo off
REM ==============================================================================
REM $CmdName - UVR Headless Runner CLI Wrapper
REM ==============================================================================
REM This delegates to the PowerShell wrapper for proper path handling.
REM PowerShell is pre-installed on all modern Windows systems (Win 10+).
REM ==============================================================================
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0$CmdName.ps1" %*
exit /b %ERRORLEVEL%
"@
    
    # Create PowerShell wrapper (handles complex paths properly)
    $PsContent = @"
# ==============================================================================
# $CmdName - UVR Headless Runner CLI Wrapper (PowerShell)
# ==============================================================================
# This wrapper handles Windows paths correctly for Docker
# ==============================================================================

`$ErrorActionPreference = "Continue"

`$Image = "$ImageTag"
`$ModelsDir = if (`$env:UVR_MODELS_DIR) { `$env:UVR_MODELS_DIR } else { "$ModelsDir" }

# Function to convert Windows path to Docker path
function Convert-ToDockerPath {
    param([string]`$WindowsPath)
    
    if ([string]::IsNullOrEmpty(`$WindowsPath)) {
        return `$WindowsPath
    }
    
    # Get absolute path
    try {
        if (Test-Path `$WindowsPath) {
            `$absPath = (Resolve-Path `$WindowsPath).Path
        } else {
            `$absPath = [System.IO.Path]::GetFullPath(`$WindowsPath)
        }
    } catch {
        `$absPath = `$WindowsPath
    }
    
    # Convert backslashes to forward slashes
    `$unixPath = `$absPath -replace '\\', '/'
    
    # Convert drive letter: C:\... -> /c/...
    if (`$unixPath -match '^([A-Za-z]):(.*)$') {
        `$driveLetter = `$Matches[1].ToLower()
        `$pathRest = `$Matches[2]
        `$unixPath = "/`$driveLetter`$pathRest"
    }
    
    return `$unixPath
}

# Ensure models directory exists
if (-not (Test-Path `$ModelsDir)) {
    New-Item -ItemType Directory -Path `$ModelsDir -Force | Out-Null
}

# Convert models directory to Docker path
`$ModelsDockerPath = Convert-ToDockerPath `$ModelsDir

# Process arguments for path mounting
# FIX (mount-mode upgrade): The old code stored `$true in `$MountedDirs and
# built `$MountArgs incrementally.  If -i (ro) was processed before -o (rw)
# and both resolved to the SAME directory (e.g. input file lives in the
# output dir), the directory was already in `$MountedDirs so the -o handler
# skipped it — leaving it mounted as :ro.  This caused the container error:
#   "No write permission for output directory"
#
# New approach: `$MountedDirs stores @{DockerDir; Mode} per host directory.
# When output requests :rw for a dir already tracked as :ro, the mode is
# upgraded.  `$MountArgs is built ONCE after all arguments are parsed,
# ensuring the final (correct) mode is used for each mount.
`$ProcessedArgs = @()
`$MountedDirs = @{}  # key=hostDir, value=@{DockerDir=...; Mode="ro"|"rw"}

# Track the output directory's container-side path for pre-flight write test.
# Set when -o/--output is parsed; used before exec to verify writability.
`$OutputDockerDir = ""

for (`$i = 0; `$i -lt `$args.Count; `$i++) {
    `$arg = `$args[`$i]
    
    if (`$arg -eq "-i" -or `$arg -eq "--input") {
        `$ProcessedArgs += `$arg
        `$i++
        if (`$i -lt `$args.Count) {
            `$path = `$args[`$i]
            
            # Resolve and convert path
            if (Test-Path `$path) {
                `$absPath = (Resolve-Path `$path).Path
                `$dir = Split-Path `$absPath -Parent
                `$dockerPath = Convert-ToDockerPath `$absPath
                `$dockerDir = Convert-ToDockerPath `$dir
                
                if (-not `$MountedDirs.ContainsKey(`$dir)) {
                    `$MountedDirs[`$dir] = @{ DockerDir = `$dockerDir; Mode = "ro" }
                }
                # If already mounted (even as rw by a prior -o), no change needed;
                # rw is a superset of ro.
                `$ProcessedArgs += `$dockerPath
            } else {
                Write-Warning "Input file not found: `$path"
                `$ProcessedArgs += `$path
            }
        }
    }
    elseif (`$arg -eq "-o" -or `$arg -eq "--output") {
        `$ProcessedArgs += `$arg
        `$i++
        if (`$i -lt `$args.Count) {
            `$path = `$args[`$i]
            
            # Create output directory if it doesn't exist
            if (-not (Test-Path `$path)) {
                try {
                    New-Item -ItemType Directory -Path `$path -Force | Out-Null
                } catch {
                    Write-Warning "Cannot create output directory: `$path"
                }
            }
            
            if (Test-Path `$path) {
                `$absPath = (Resolve-Path `$path).Path
                `$dockerPath = Convert-ToDockerPath `$absPath
                
                if (`$MountedDirs.ContainsKey(`$absPath)) {
                    # CRITICAL: Upgrade ro -> rw so output directory is writable
                    `$MountedDirs[`$absPath].Mode = "rw"
                } else {
                    `$MountedDirs[`$absPath] = @{ DockerDir = `$dockerPath; Mode = "rw" }
                }
                `$ProcessedArgs += `$dockerPath
                # Remember output dir for pre-flight write test
                `$OutputDockerDir = `$dockerPath
            } else {
                `$ProcessedArgs += `$path
            }
        }
    }
    else {
        `$ProcessedArgs += `$arg
    }
}

# Build mount args from tracked directories (final pass ensures correct modes).
# This MUST happen after the argument-parsing loop so that any ro->rw
# upgrades (e.g. same dir used for both -i and -o) are already resolved.
`$MountArgs = @()
foreach (`$entry in `$MountedDirs.GetEnumerator()) {
    `$MountArgs += "-v"
    `$MountArgs += "`$(`$entry.Key):`$(`$entry.Value.DockerDir):`$(`$entry.Value.Mode)"
}

# Rewrite localhost proxy addresses for Docker container access.
# Inside a container, 127.0.0.1/localhost refers to the container itself,
# not the host machine. Replace with host.docker.internal so the proxy is reachable.
function Rewrite-ProxyForDocker {
    param([string]`$Url)
    if ([string]::IsNullOrEmpty(`$Url)) { return `$Url }
    # Regex handles: http://, https://, socks4://, socks5://, socks5h:// protocols
    # and optional user:pass@ authentication before the host address.
    # Examples matched:
    #   http://127.0.0.1:7890         -> http://host.docker.internal:7890
    #   http://user:pass@localhost:80  -> http://user:pass@host.docker.internal:80
    #   socks5://127.0.0.1:1080       -> socks5://host.docker.internal:1080
    return `$Url -replace '(://([^@]*@)?)(127\.0\.0\.1|localhost|\[::1\])', '`$1host.docker.internal'
}

# Build docker command
`$DockerArgs = @("run", "--rm")

# Add -it only if running interactively in a terminal
if ([Environment]::UserInteractive -and `$Host.Name -eq 'ConsoleHost') {
    `$DockerArgs += "-it"
}

# Ensure host.docker.internal resolves on all platforms.
# Docker Desktop on Windows resolves it natively, but this is harmless and
# makes the wrapper portable (e.g., if run under WSL2 Docker daemon directly).
`$DockerArgs += "--add-host=host.docker.internal:host-gateway"

# Add GPU flags if needed
`$GpuEnabled = "$($Target -eq 'gpu')"
if (`$GpuEnabled -eq "True") {
    `$DockerArgs += "--gpus"
    `$DockerArgs += "all"
}

# Add models volume (mount to /models — the path the container expects)
`$DockerArgs += "-v"
`$DockerArgs += "`$(`$ModelsDir):/models"

# Add mounted directories
`$DockerArgs += `$MountArgs

# Add environment variable
`$DockerArgs += "-e"
`$DockerArgs += "UVR_MODELS_DIR=/models"

# HTTP/HTTPS Proxy passthrough (with localhost rewriting for Docker)
# Automatically passes proxy settings from host to container if set.
# Rewrites 127.0.0.1/localhost to host.docker.internal so the proxy is
# reachable from inside the container.
# SECURITY: Values are passed but not logged (may contain credentials)
if (`$env:HTTP_PROXY) { `$DockerArgs += "-e"; `$DockerArgs += "HTTP_PROXY=`$(Rewrite-ProxyForDocker `$env:HTTP_PROXY)" }
if (`$env:HTTPS_PROXY) { `$DockerArgs += "-e"; `$DockerArgs += "HTTPS_PROXY=`$(Rewrite-ProxyForDocker `$env:HTTPS_PROXY)" }
if (`$env:NO_PROXY) { `$DockerArgs += "-e"; `$DockerArgs += "NO_PROXY=`$(`$env:NO_PROXY)" }
if (`$env:http_proxy) { `$DockerArgs += "-e"; `$DockerArgs += "http_proxy=`$(Rewrite-ProxyForDocker `$env:http_proxy)" }
if (`$env:https_proxy) { `$DockerArgs += "-e"; `$DockerArgs += "https_proxy=`$(Rewrite-ProxyForDocker `$env:https_proxy)" }
if (`$env:no_proxy) { `$DockerArgs += "-e"; `$DockerArgs += "no_proxy=`$(`$env:no_proxy)" }
# ALL_PROXY: used by curl, git, and other tools as SOCKS/general proxy fallback
if (`$env:ALL_PROXY) { `$DockerArgs += "-e"; `$DockerArgs += "ALL_PROXY=`$(Rewrite-ProxyForDocker `$env:ALL_PROXY)" }
if (`$env:all_proxy) { `$DockerArgs += "-e"; `$DockerArgs += "all_proxy=`$(Rewrite-ProxyForDocker `$env:all_proxy)" }

# Add image and command
`$DockerArgs += `$Image
`$DockerArgs += "$RunnerScript"
`$DockerArgs += `$ProcessedArgs

# Show command in verbose mode (proxy vars intentionally excluded for security)
if (`$env:UVR_DEBUG) {
    Write-Host "Docker command: docker `$(`$DockerArgs -join ' ')" -ForegroundColor Gray
}

# ── Pre-flight: verify output directory is writable inside container ──
# Spins up a throw-away container with the SAME volume mounts and attempts a
# test write.  This catches mount-mode mistakes (:ro vs :rw), host permission
# issues, and Docker Desktop file-sharing blocks BEFORE PyTorch and models are
# loaded — saving minutes of wasted startup time.
if (`$OutputDockerDir) {
    `$WriteTest = "`$OutputDockerDir/.uvr_write_test_`$PID"
    `$TestArgs = @("run", "--rm") + `$MountArgs + @("--entrypoint", "sh", `$Image, "-c", "touch '`$WriteTest' && rm -f '`$WriteTest'")
    & docker @TestArgs 2>`$null
    if (`$LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Output directory is not writable inside the container:" -ForegroundColor Red
        Write-Host "  `$OutputDockerDir" -ForegroundColor Red
        Write-Host ""
        Write-Host "Possible causes:" -ForegroundColor Yellow
        Write-Host "  1. Volume mounted as read-only (:ro instead of :rw)"
        Write-Host "  2. Host directory permissions do not allow Docker to write"
        Write-Host "  3. Docker Desktop file sharing not configured for this drive"
        Write-Host ""
        Write-Host "Tip: set env UVR_DEBUG=1 to see the full docker command." -ForegroundColor Gray
        exit 1
    }
}

# Execute docker
& docker @DockerArgs
exit `$LASTEXITCODE
"@
    
    # Write wrappers with correct encoding
    [System.IO.File]::WriteAllText($WrapperPath, $CmdContent, [System.Text.Encoding]::ASCII)
    [System.IO.File]::WriteAllText($PsWrapperPath, $PsContent, [System.Text.UTF8Encoding]::new($false))
    
    Write-Success "Installed: $WrapperPath"
}

# ------------------------------------------------------------------------------
# Uninstall
# ------------------------------------------------------------------------------
function Uninstall-Wrappers {
    Write-Info "Uninstalling UVR CLI wrappers..."
    
    $Wrappers = @("uvr", "uvr-mdx", "uvr-demucs", "uvr-vr")
    
    foreach ($wrapper in $Wrappers) {
        $cmdPath = Join-Path $InstallDir "$wrapper.cmd"
        $psPath = Join-Path $InstallDir "$wrapper.ps1"
        
        if (Test-Path $cmdPath) {
            Remove-Item $cmdPath -Force
            Write-Success "Removed: $cmdPath"
        }
        if (Test-Path $psPath) {
            Remove-Item $psPath -Force
            Write-Success "Removed: $psPath"
        }
    }
    
    Write-Info "Uninstallation complete."
    Write-Host ""
    Write-Host "Note: Docker images and model cache were not removed."
    Write-Host ""
    Write-Host "To remove Docker images:"
    Write-Host "  docker rmi ${ImageName}:gpu-cu124 ${ImageName}:cpu"
    Write-Host ""
    Write-Host "To remove model cache:"
    Write-Host "  Remove-Item -Recurse -Force `"$ModelsDir`""
}

# ------------------------------------------------------------------------------
# Main Installation
# ------------------------------------------------------------------------------
function Install-UVR {
    param(
        [string]$Target,
        [string]$CudaVersion
    )
    
    Show-Banner
    
    # Check Docker — use structured result for specific guidance
    $dockerStatus = Test-Docker
    if (-not $dockerStatus.Available) {
        switch ($dockerStatus.Reason) {
            "not_installed" {
                Write-ErrorMsg "Docker is not installed."
                Write-Host ""
                Write-Host "Please install Docker Desktop:" -ForegroundColor Yellow
                Write-Host "  https://docs.docker.com/desktop/install/windows-install/"
            }
            "no_permission" {
                Write-ErrorMsg "Docker access denied — your user may not be in the 'docker-users' group."
                Write-Host ""
                Write-Host "Fix:" -ForegroundColor Yellow
                Write-Host "  1. Open 'Computer Management' -> Local Users and Groups -> Groups"
                Write-Host "  2. Add your user to the 'docker-users' group"
                Write-Host "  3. Log out and back in"
                Write-Host ""
                Write-Host "Or run this script as Administrator."
            }
            "not_running" {
                Write-ErrorMsg "Docker daemon is not running."
                Write-Host ""
                Write-Host "Please start Docker Desktop and wait for it to finish initializing." -ForegroundColor Yellow
                Write-Host "Look for the Docker whale icon in the system tray."
            }
            default {
                Write-ErrorMsg "Docker is not working properly."
                if ($dockerStatus.Detail) {
                    Write-Host "Detail: $($dockerStatus.Detail)" -ForegroundColor Gray
                }
                Write-Host ""
                Write-Host "Make sure Docker Desktop is installed and running:" -ForegroundColor Yellow
                Write-Host "  https://docs.docker.com/desktop/install/windows-install/"
            }
        }
        Write-Host ""
        exit 1
    }
    
    Write-Success "Docker is available"
    
    # Auto-detect GPU
    if (-not $Target) {
        Write-Info "Auto-detecting GPU support..."
        if (Test-GpuSupport) {
            $Target = "gpu"
            Write-Success "GPU support detected!"
        } else {
            $Target = "cpu"
            Write-Info "Using CPU mode (no GPU support found)"
        }
        # Final cleanup: remove any GPU test containers orphaned by a previous
        # interrupted run (e.g. terminal closed during GPU detection).
        # Safe and idempotent — no-op if none exist.
        $savedEP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $leftover = docker ps -aq --filter "ancestor=nvidia/cuda:12.4.1-base-ubuntu22.04" 2>$null
        if ($leftover) {
            Write-Info "Cleaning up orphaned GPU test containers from previous run..."
            docker rm -f $leftover 2>$null | Out-Null
        }
        $ErrorActionPreference = $savedEP
    }
    
    Write-Host ""
    Write-Host "Installation mode: $Target" -ForegroundColor Cyan
    if ($Target -eq "gpu") {
        Write-Host "CUDA version: $CudaVersion (requires driver $(Get-CudaDriverRequirement $CudaVersion))" -ForegroundColor Cyan
    }
    Write-Host ""
    
    # Create directories
    Write-Info "Creating directories..."
    try {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        New-Item -ItemType Directory -Path $ModelsDir -Force | Out-Null
        New-Item -ItemType Directory -Path "$ModelsDir\VR_Models" -Force | Out-Null
        New-Item -ItemType Directory -Path "$ModelsDir\MDX_Net_Models" -Force | Out-Null
        New-Item -ItemType Directory -Path "$ModelsDir\Demucs_Models" -Force | Out-Null
        Write-Success "Directories created"
    } catch {
        Write-ErrorMsg "Failed to create directories: $_"
        exit 1
    }
    
    # Build Docker image
    Build-Image -Target $Target -CudaVersion $CudaVersion
    
    # Clean up dangling images from previous interrupted builds.
    # docker build leaves unnamed intermediate layers when interrupted (Ctrl+C,
    # network drop, OOM). These accumulate across repeated installs and waste disk.
    # Safe and idempotent — only removes images with no tags and no children.
    $savedEP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $dangling = docker images -qf "dangling=true" 2>$null
    if ($dangling) {
        Write-Info "Cleaning up dangling images from previous builds..."
        docker image prune -f 2>$null | Out-Null
    }
    $ErrorActionPreference = $savedEP
    
    # Create wrappers
    Write-Info "Installing CLI wrappers to $InstallDir..."
    
    New-Wrapper -CmdName "uvr-mdx" -RunnerScript "uvr-mdx" -Target $Target -CudaVersion $CudaVersion
    New-Wrapper -CmdName "uvr-demucs" -RunnerScript "uvr-demucs" -Target $Target -CudaVersion $CudaVersion
    New-Wrapper -CmdName "uvr-vr" -RunnerScript "uvr-vr" -Target $Target -CudaVersion $CudaVersion
    New-Wrapper -CmdName "uvr" -RunnerScript "uvr" -Target $Target -CudaVersion $CudaVersion
    
    # Add to PATH if not already
    # FIX: The old code read PATH at time T1 and wrote it back at time T2.
    # If another installer modified the registry PATH between T1 and T2,
    # those changes would be silently overwritten (lost). We now re-read
    # the value immediately before writing to minimize the TOCTOU window.
    if (-not ([Environment]::GetEnvironmentVariable("Path", "User") -like "*$InstallDir*")) {
        Write-Info "Adding $InstallDir to PATH..."
        try {
            # Re-read at write time to minimize race window with concurrent installers
            $freshPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if ($freshPath -notlike "*$InstallDir*") {
                [Environment]::SetEnvironmentVariable("Path", "$freshPath;$InstallDir", "User")
            }
            $env:Path = "$env:Path;$InstallDir"
            Write-Success "PATH updated"
        } catch {
            Write-Warn "Could not update PATH automatically. Please add manually:"
            Write-Host "  $InstallDir"
        }
    }
    
    # Success message
    Write-Host ""
    Write-Host "=========================================================" -ForegroundColor Green
    Write-Host "            Installation Complete!                       " -ForegroundColor Green
    Write-Host "=========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now use these commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host '  uvr-mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/'
    Write-Host '  uvr-demucs -m htdemucs -i song.wav -o output/'
    Write-Host '  uvr-vr -m "UVR-De-Echo-Normal" -i song.wav -o output/'
    Write-Host ""
    Write-Host "  uvr mdx --list          # List MDX models"
    Write-Host "  uvr demucs --list       # List Demucs models"
    Write-Host "  uvr vr --list           # List VR models"
    Write-Host ""
    Write-Host "Models will be cached in: $ModelsDir" -ForegroundColor Cyan
    Write-Host ""
    
    if ($Target -eq "gpu") {
        Write-Host "GPU acceleration is enabled! (CUDA $CudaVersion)" -ForegroundColor Green
        Write-Host ""
        Write-Host "CUDA compatibility:" -ForegroundColor Cyan
        switch ($CudaVersion) {
            "cu121" { Write-Host "  CUDA 12.1 - requires NVIDIA driver 530+" }
            "cu124" { Write-Host "  CUDA 12.4 - requires NVIDIA driver 550+" }
            "cu128" { Write-Host "  CUDA 12.8 - requires NVIDIA driver 560+" }
        }
    } else {
        Write-Host "Running in CPU mode." -ForegroundColor Yellow
        Write-Host "For GPU support, ensure NVIDIA drivers and Docker GPU support are configured."
    }
    
    Write-Host ""
    Write-Host "NOTE: You may need to restart your terminal for PATH changes to take effect." -ForegroundColor Yellow
}

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
if ($Help) {
    Show-Banner
    Write-Host "Usage: .\install.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Cpu           Force CPU-only installation"
    Write-Host "  -Gpu           Force GPU installation (uses default CUDA version)"
    Write-Host "  -Cuda VERSION  GPU installation with specific CUDA version"
    Write-Host "                 VERSION: cu121, cu124 (default), cu128"
    Write-Host "  -Build         Force local build instead of pulling from Docker Hub"
    Write-Host "  -Uninstall     Remove installed CLI wrappers"
    Write-Host "  -Help          Show this help message"
    Write-Host ""
    Write-Host "Image Source:"
    Write-Host "  By default, the script pulls pre-built images from Docker Hub (fast!)"
    Write-Host "  Use -Build to force local building (slower, but uses latest code)"
    Write-Host ""
    Write-Host "CUDA Versions:"
    Write-Host "  cu121 - CUDA 12.1, requires NVIDIA driver 530+"
    Write-Host "  cu124 - CUDA 12.4, requires NVIDIA driver 550+ (default)"
    Write-Host "  cu128 - CUDA 12.8, requires NVIDIA driver 560+"
    Write-Host ""
    Write-Host "Environment Variables:"
    Write-Host "  UVR_INSTALL_DIR    Installation directory (default: %LOCALAPPDATA%\UVR)"
    Write-Host "  UVR_MODELS_DIR     Model cache directory (default: %USERPROFILE%\.uvr_models)"
    Write-Host "  UVR_CUDA_VERSION   CUDA version (default: cu124)"
    Write-Host "  UVR_FORCE_BUILD    Set to 1 to force local build"
    Write-Host "  UVR_DEBUG          Set to 1 to show debug output"
    Write-Host ""
    Write-Host "Proxy Support (auto-passthrough if set):"
    Write-Host "  HTTP_PROXY         HTTP proxy URL (e.g., http://proxy:8080)"
    Write-Host "  HTTPS_PROXY        HTTPS proxy URL"
    Write-Host "  NO_PROXY           Comma-separated list of hosts to bypass proxy"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  # Quick install (pulls from Docker Hub)"
    Write-Host "  .\install.ps1"
    Write-Host ""
    Write-Host "  # Install GPU with CUDA 12.1 (for older drivers)"
    Write-Host "  .\install.ps1 -Cuda cu121"
    Write-Host ""
    Write-Host "  # Force local build with GPU"
    Write-Host "  .\install.ps1 -Gpu -Build"
    exit 0
}

if ($Uninstall) {
    Uninstall-Wrappers
    exit 0
}

# Determine target and CUDA version
$Target = $null
$CudaVersion = $DefaultCudaVersion

if ($Cpu) { 
    $Target = "cpu" 
}
if ($Gpu) { 
    $Target = "gpu" 
}
if ($Cuda) {
    $Target = "gpu"
    $CudaVersion = $Cuda
}

try {
    Install-UVR -Target $Target -CudaVersion $CudaVersion
} catch {
    Write-Host ""
    Write-Warn "Installation was interrupted: $_"
    Write-Info "It is safe to rerun this script - all steps are idempotent."
    Write-Host ""
    Write-Host "Error details:" -ForegroundColor Yellow
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Gray
    if ($_.ScriptStackTrace) {
        Write-Host "  at: $($_.ScriptStackTrace.Split("`n")[0].Trim())" -ForegroundColor Gray
    }
    # FIX: Pause before exit so users launched from install.bat or Explorer
    # can read the error message before the window closes ("flash exit").
    # Without this, the CMD window closes immediately on exit 1,
    # and the user never sees what went wrong.
    if ([Environment]::UserInteractive) {
        Write-Host ""
        Write-Host "Press Enter to exit..." -ForegroundColor Yellow
        $null = Read-Host
    }
    exit 1
}
