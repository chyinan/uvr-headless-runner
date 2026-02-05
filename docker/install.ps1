# ==============================================================================
# UVR Headless Runner - Windows Installation Script (PowerShell)
# ==============================================================================
# This script installs native-style CLI wrappers for Windows.
#
# Usage:
#   .\docker\install.ps1              # Install with auto-detected GPU support
#   .\docker\install.ps1 -Cpu         # Force CPU-only installation
#   .\docker\install.ps1 -Gpu         # Force GPU installation
#   .\docker\install.ps1 -Uninstall   # Remove installed wrappers
#
# ==============================================================================

param(
    [switch]$Cpu,
    [switch]$Gpu,
    [switch]$Uninstall,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Configuration
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$InstallDir = if ($env:UVR_INSTALL_DIR) { $env:UVR_INSTALL_DIR } else { "$env:LOCALAPPDATA\UVR" }
$ModelsDir = if ($env:UVR_MODELS_DIR) { $env:UVR_MODELS_DIR } else { "$env:USERPROFILE\.uvr_models" }
$ImageName = "uvr-headless"

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Blue }
function Write-Success { param($Message) Write-Host "[SUCCESS] $Message" -ForegroundColor Green }
function Write-Warn { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

function Show-Banner {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║        UVR Headless Runner - Windows Installation             ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Docker {
    try {
        $null = docker info 2>$null
        return $true
    } catch {
        return $false
    }
}

function Test-GpuSupport {
    try {
        $null = nvidia-smi 2>$null
        if ($LASTEXITCODE -eq 0) {
            # Try running a GPU container
            $result = docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $true
            }
        }
    } catch {}
    return $false
}

# ------------------------------------------------------------------------------
# Build Docker Image
# ------------------------------------------------------------------------------
function Build-Image {
    param([string]$Target)
    
    $Tag = "${ImageName}:${Target}"
    
    Write-Info "Building Docker image: $Tag"
    Write-Info "This may take several minutes on first build..."
    
    Push-Location $ProjectRoot
    try {
        docker build -t $Tag -f docker/Dockerfile --target $Target .
        if ($LASTEXITCODE -ne 0) {
            throw "Docker build failed"
        }
        Write-Success "Image built successfully: $Tag"
    } finally {
        Pop-Location
    }
}

# ------------------------------------------------------------------------------
# Create CLI Wrapper Scripts
# ------------------------------------------------------------------------------
function New-Wrapper {
    param(
        [string]$CmdName,
        [string]$RunnerScript,
        [string]$Target
    )
    
    $WrapperPath = Join-Path $InstallDir "$CmdName.cmd"
    $PsWrapperPath = Join-Path $InstallDir "$CmdName.ps1"
    
    Write-Info "Creating wrapper: $CmdName"
    
    # GPU flags
    $GpuFlags = if ($Target -eq "gpu") { "--gpus all" } else { "" }
    
    # Create CMD wrapper
    $CmdContent = @"
@echo off
REM ==============================================================================
REM $CmdName - UVR Headless Runner CLI Wrapper
REM ==============================================================================
setlocal enabledelayedexpansion

set IMAGE=${ImageName}:${Target}
set MODELS_DIR=%UVR_MODELS_DIR%
if "%MODELS_DIR%"=="" set MODELS_DIR=$ModelsDir

REM Ensure models directory exists
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"

REM Run container
docker run --rm -it $GpuFlags -v "%MODELS_DIR%:/models" -e "UVR_MODELS_DIR=/models" %IMAGE% $RunnerScript %*
"@
    
    # Create PowerShell wrapper
    $PsContent = @"
# ==============================================================================
# $CmdName - UVR Headless Runner CLI Wrapper (PowerShell)
# ==============================================================================

`$Image = "${ImageName}:${Target}"
`$ModelsDir = if (`$env:UVR_MODELS_DIR) { `$env:UVR_MODELS_DIR } else { "$ModelsDir" }

# Ensure models directory exists
if (-not (Test-Path `$ModelsDir)) {
    New-Item -ItemType Directory -Path `$ModelsDir -Force | Out-Null
}

# Process arguments for path mounting
`$MountArgs = @()
`$ProcessedArgs = @()
`$MountedDirs = @{}

for (`$i = 0; `$i -lt `$args.Count; `$i++) {
    `$arg = `$args[`$i]
    
    if (`$arg -eq "-i" -or `$arg -eq "--input") {
        `$ProcessedArgs += `$arg
        `$i++
        if (`$i -lt `$args.Count) {
            `$path = `$args[`$i]
            `$absPath = (Resolve-Path `$path -ErrorAction SilentlyContinue).Path
            if (`$absPath) {
                `$dir = Split-Path `$absPath -Parent
                `$unixPath = `$absPath -replace '\\', '/' -replace '^([A-Za-z]):', '/`$1'
                `$unixDir = `$dir -replace '\\', '/' -replace '^([A-Za-z]):', '/`$1'
                if (-not `$MountedDirs.ContainsKey(`$dir)) {
                    `$MountedDirs[`$dir] = `$true
                    `$MountArgs += "-v"
                    `$MountArgs += "`${dir}:`${unixDir}:ro"
                }
                `$ProcessedArgs += `$unixPath
            } else {
                `$ProcessedArgs += `$path
            }
        }
    }
    elseif (`$arg -eq "-o" -or `$arg -eq "--output") {
        `$ProcessedArgs += `$arg
        `$i++
        if (`$i -lt `$args.Count) {
            `$path = `$args[`$i]
            if (-not (Test-Path `$path)) {
                New-Item -ItemType Directory -Path `$path -Force | Out-Null
            }
            `$absPath = (Resolve-Path `$path).Path
            `$unixPath = `$absPath -replace '\\', '/' -replace '^([A-Za-z]):', '/`$1'
            if (-not `$MountedDirs.ContainsKey(`$absPath)) {
                `$MountedDirs[`$absPath] = `$true
                `$MountArgs += "-v"
                `$MountArgs += "`${absPath}:`${unixPath}:rw"
            }
            `$ProcessedArgs += `$unixPath
        }
    }
    else {
        `$ProcessedArgs += `$arg
    }
}

# Build docker command
# Use -it only if running in a terminal
`$IsInteractive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
if (`$IsInteractive) {
    `$DockerArgs = @("run", "--rm", "-it")
} else {
    `$DockerArgs = @("run", "--rm")
}
`$GpuEnabled = "$($Target -eq 'gpu')"
if (`$GpuEnabled -eq "True") {
    `$DockerArgs += "--gpus"
    `$DockerArgs += "all"
}
`$DockerArgs += "-v"
`$DockerArgs += "`${ModelsDir}:/models"
`$DockerArgs += `$MountArgs
`$DockerArgs += "-e"
`$DockerArgs += "UVR_MODELS_DIR=/models"
`$DockerArgs += `$Image
`$DockerArgs += "$RunnerScript"
`$DockerArgs += `$ProcessedArgs

& docker @DockerArgs
"@
    
    # Write wrappers
    $CmdContent | Out-File -FilePath $WrapperPath -Encoding ASCII
    $PsContent | Out-File -FilePath $PsWrapperPath -Encoding UTF8
    
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
    Write-Host "  docker rmi ${ImageName}:gpu ${ImageName}:cpu"
    Write-Host ""
    Write-Host "To remove model cache:"
    Write-Host "  Remove-Item -Recurse -Force $ModelsDir"
}

# ------------------------------------------------------------------------------
# Main Installation
# ------------------------------------------------------------------------------
function Install-UVR {
    param([string]$Target)
    
    Show-Banner
    
    # Check Docker
    if (-not (Test-Docker)) {
        Write-Error "Docker is not installed or not running."
        Write-Host "Please install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
        exit 1
    }
    
    # Auto-detect GPU
    if (-not $Target) {
        Write-Info "Auto-detecting GPU support..."
        if (Test-GpuSupport) {
            $Target = "gpu"
            Write-Info "Detected: GPU support available"
        } else {
            $Target = "cpu"
            Write-Info "Detected: CPU mode (no GPU support found)"
        }
    }
    
    # Create directories
    Write-Info "Creating directories..."
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    New-Item -ItemType Directory -Path $ModelsDir -Force | Out-Null
    New-Item -ItemType Directory -Path "$ModelsDir\VR_Models" -Force | Out-Null
    New-Item -ItemType Directory -Path "$ModelsDir\MDX_Net_Models" -Force | Out-Null
    New-Item -ItemType Directory -Path "$ModelsDir\Demucs_Models" -Force | Out-Null
    
    # Build Docker image
    Build-Image -Target $Target
    
    # Create wrappers
    Write-Info "Installing CLI wrappers to $InstallDir..."
    
    New-Wrapper -CmdName "uvr-mdx" -RunnerScript "uvr-mdx" -Target $Target
    New-Wrapper -CmdName "uvr-demucs" -RunnerScript "uvr-demucs" -Target $Target
    New-Wrapper -CmdName "uvr-vr" -RunnerScript "uvr-vr" -Target $Target
    New-Wrapper -CmdName "uvr" -RunnerScript "uvr" -Target $Target
    
    # Add to PATH if not already
    $CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($CurrentPath -notlike "*$InstallDir*") {
        Write-Info "Adding $InstallDir to PATH..."
        [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$InstallDir", "User")
        $env:Path = "$env:Path;$InstallDir"
    }
    
    # Success message
    Write-Host ""
    Write-Success "Installation complete!"
    Write-Host ""
    Write-Host "You can now use these commands:" -ForegroundColor Green
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
        Write-Host "GPU acceleration is enabled!" -ForegroundColor Green
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
    Write-Host "  -Cpu        Force CPU-only installation"
    Write-Host "  -Gpu        Force GPU installation"
    Write-Host "  -Uninstall  Remove installed CLI wrappers"
    Write-Host "  -Help       Show this help message"
    Write-Host ""
    Write-Host "Environment Variables:"
    Write-Host "  UVR_INSTALL_DIR   Installation directory (default: %LOCALAPPDATA%\UVR)"
    Write-Host "  UVR_MODELS_DIR    Model cache directory (default: %USERPROFILE%\.uvr_models)"
    exit 0
}

if ($Uninstall) {
    Uninstall-Wrappers
    exit 0
}

$Target = $null
if ($Cpu) { $Target = "cpu" }
if ($Gpu) { $Target = "gpu" }

Install-UVR -Target $Target
