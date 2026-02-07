#!/usr/bin/env python3
"""
UVR Headless Runner - Unified CLI Entry Point
==============================================

Provides a single `uvr` command that dispatches to the appropriate runner.

Usage:
    uvr mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/
    uvr demucs -m htdemucs -i song.wav -o output/
    uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/
    uvr list [mdx|demucs|vr|all]
    uvr download <model-name> --arch <mdx|demucs|vr>
    uvr info
    uvr help

This module is the entry point registered as `uvr` in pyproject.toml:
    [tool.poetry.scripts]
    uvr = "cli:main"
"""

import os
import sys

VERSION = "1.0.3"


def _run_runner(module_name, suppress_errors=False):
    """
    Import and run a runner module's main() function.
    
    Handles ImportError gracefully (e.g. missing dependencies).
    """
    try:
        import importlib
        mod = importlib.import_module(module_name)
        return mod.main()
    except ImportError as e:
        if suppress_errors:
            print(f"  (unavailable: {e})")
            return 1
        print(f"Error: Missing dependency — {e}")
        print("Run: pip install -r requirements.txt")
        return 1
    except SystemExit as e:
        # argparse --help raises SystemExit(0), let it through
        return e.code if e.code else 0
    except Exception as e:
        if suppress_errors:
            print(f"  (error: {e})")
            return 1
        raise


def print_banner():
    """Print the UVR banner."""
    print()
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║     UVR Headless Runner - Audio Source Separation CLI         ║")
    print(f"║                        Version {VERSION}                          ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()


def print_usage():
    """Print usage information."""
    print_banner()
    print("Usage: uvr <command> [options]")
    print()
    print("Commands:")
    print("  mdx       Run MDX-Net/Roformer/SCNet separation")
    print("  demucs    Run Demucs separation")
    print("  vr        Run VR Architecture separation")
    print("  list      List available models")
    print("  download  Download a model")
    print("  info      Show system information")
    print("  help      Show this help message")
    print()
    print("Examples:")
    print('  uvr mdx -m "UVR-MDX-NET Inst HQ 3" -i song.wav -o output/')
    print('  uvr demucs -m htdemucs -i song.wav -o output/')
    print('  uvr vr -m "UVR-De-Echo-Normal" -i song.wav -o output/')
    print('  uvr list mdx')
    print('  uvr download "htdemucs_ft" --arch demucs')
    print()
    print("For command-specific help:")
    print("  uvr mdx --help")
    print("  uvr demucs --help")
    print("  uvr vr --help")


def print_info():
    """Print system information."""
    print_banner()
    print("System Information:")
    print("===================")

    # Python version
    print(f"Python: {sys.version.split()[0]}")

    # PyTorch version and CUDA
    try:
        import torch
        print(f"PyTorch: {torch.__version__}")
        cuda_available = torch.cuda.is_available()
        print(f"CUDA Available: {'Yes' if cuda_available else 'No'}")
        if cuda_available:
            print(f"CUDA Version: {torch.version.cuda}")
            print(f"GPU Device: {torch.cuda.get_device_name(0)}")
            print(f"GPU Count: {torch.cuda.device_count()}")
    except ImportError:
        print("PyTorch: Not installed")

    # DirectML
    try:
        import torch_directml
        print(f"DirectML: Available")
    except ImportError:
        print(f"DirectML: Not available")

    # MPS (Apple Silicon)
    try:
        import torch
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print("MPS (Apple Silicon): Available")
    except (ImportError, AttributeError):
        pass

    # Model directory
    models_dir = os.environ.get('UVR_MODELS_DIR', os.path.join(os.path.expanduser('~'), '.uvr_models'))
    print(f"\nModel Directory: {models_dir}")

    # Check model counts
    if os.path.isdir(models_dir):
        print("\nInstalled Models:")
        mdx_dir = os.path.join(models_dir, 'MDX_Net_Models')
        if os.path.isdir(mdx_dir):
            count = len([f for f in os.listdir(mdx_dir) 
                        if f.endswith(('.onnx', '.ckpt'))])
            print(f"  MDX-Net: {count} models")

        demucs_dir = os.path.join(models_dir, 'Demucs_Models')
        if os.path.isdir(demucs_dir):
            count = 0
            for root, dirs, files in os.walk(demucs_dir):
                count += len([f for f in files if f.endswith(('.th', '.yaml'))])
            print(f"  Demucs: {count} files")

        vr_dir = os.path.join(models_dir, 'VR_Models')
        if os.path.isdir(vr_dir):
            count = len([f for f in os.listdir(vr_dir) 
                        if f.endswith('.pth')])
            print(f"  VR: {count} models")
    else:
        print(f"\nModel directory not found. Models will be downloaded on first use.")

    # Proxy status
    try:
        from model_downloader import is_proxy_configured
        print(f"\nProxy: {'Configured' if is_proxy_configured() else 'Not configured'}")
    except ImportError:
        pass

    print()


def cmd_list(args):
    """Handle 'uvr list' subcommand."""
    arch = args[0] if args else "all"

    if arch == "mdx":
        sys.argv = ["uvr-mdx", "--list"]
        return _run_runner("mdx_headless_runner")
    elif arch == "demucs":
        sys.argv = ["uvr-demucs", "--list"]
        return _run_runner("demucs_headless_runner")
    elif arch == "vr":
        sys.argv = ["uvr-vr", "--list"]
        return _run_runner("vr_headless_runner")
    elif arch == "all":
        print("=== MDX-Net Models ===")
        sys.argv = ["uvr-mdx", "--list"]
        _run_runner("mdx_headless_runner", suppress_errors=True)

        print()
        print("=== Demucs Models ===")
        sys.argv = ["uvr-demucs", "--list"]
        _run_runner("demucs_headless_runner", suppress_errors=True)

        print()
        print("=== VR Models ===")
        sys.argv = ["uvr-vr", "--list"]
        _run_runner("vr_headless_runner", suppress_errors=True)
        return 0
    else:
        print(f"Unknown architecture: {arch}")
        print("Valid options: mdx, demucs, vr, all")
        return 1


def cmd_download(args):
    """Handle 'uvr download' subcommand."""
    if not args:
        print("Error: Model name required")
        print('Usage: uvr download <model-name> --arch <mdx|demucs|vr>')
        return 1

    model_name = args[0]
    rest_args = args[1:]

    # Parse --arch flag
    arch = None
    i = 0
    while i < len(rest_args):
        if rest_args[i] in ("--arch", "-a") and i + 1 < len(rest_args):
            arch = rest_args[i + 1]
            i += 2
        else:
            i += 1

    if not arch:
        print("Error: Architecture required")
        print('Usage: uvr download <model-name> --arch <mdx|demucs|vr>')
        return 1

    if arch == "mdx":
        sys.argv = ["uvr-mdx", "--download", model_name]
        return _run_runner("mdx_headless_runner")
    elif arch == "demucs":
        sys.argv = ["uvr-demucs", "--download", model_name]
        return _run_runner("demucs_headless_runner")
    elif arch == "vr":
        sys.argv = ["uvr-vr", "--download", model_name]
        return _run_runner("vr_headless_runner")
    else:
        print(f"Unknown architecture: {arch}")
        print("Valid options: mdx, demucs, vr")
        return 1


def main():
    """Unified CLI entry point — dispatches to the appropriate runner."""
    if len(sys.argv) < 2:
        print_usage()
        return 0

    command = sys.argv[1]
    remaining_args = sys.argv[2:]

    if command == "mdx":
        sys.argv = ["uvr-mdx"] + remaining_args
        return _run_runner("mdx_headless_runner")

    elif command == "demucs":
        sys.argv = ["uvr-demucs"] + remaining_args
        return _run_runner("demucs_headless_runner")

    elif command == "vr":
        sys.argv = ["uvr-vr"] + remaining_args
        return _run_runner("vr_headless_runner")

    elif command == "list":
        return cmd_list(remaining_args)

    elif command == "download":
        return cmd_download(remaining_args)

    elif command == "info":
        print_info()
        return 0

    elif command in ("help", "--help", "-h"):
        print_usage()
        return 0

    elif command in ("version", "--version", "-v"):
        print(f"uvr version {VERSION}")
        return 0

    else:
        print(f"Error: Unknown command '{command}'")
        print()
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
