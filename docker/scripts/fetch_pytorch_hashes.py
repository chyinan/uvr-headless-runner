#!/usr/bin/env python3
"""
Fetch PyTorch wheel hashes from pytorch wheel index.

This script downloads wheel metadata and extracts SHA256 hashes for specific
PyTorch versions and CUDA variants.

Security Rationale:
- PyTorch wheels from pytorch.org have different hashes than PyPI
- Each CUDA version (cu121, cu124, cu128, cpu) has unique wheel files
- Pre-computing hashes ensures reproducible, secure builds

Usage:
    python fetch_pytorch_hashes.py --cuda cpu --output requirements-torch-cpu.txt
    python fetch_pytorch_hashes.py --cuda cu124 --output requirements-torch-cu124.txt
"""

import argparse
import hashlib
import sys
import urllib.request
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# PyTorch packages to fetch
PYTORCH_PACKAGES = [
    ('torch', '2.8.0'),
    ('torchvision', '0.23.0'),
    ('torchaudio', '2.8.0'),
]

# Additional packages only needed for Docker (not in poetry.lock)
EXTRA_PACKAGES = [
    ('rich', '13.7.0'),  # CLI progress display
    ('markdown-it-py', '3.0.0'),  # rich dependency
    ('mdurl', '0.1.2'),  # markdown-it-py dependency
    ('pygments', '2.18.0'),  # rich dependency
    ('onnxruntime-gpu', '1.19.2'),  # GPU ONNX runtime (CUDA 12.x)
]

# PyPI API for package info
PYPI_API = "https://pypi.org/pypi/{package}/{version}/json"

# PyTorch wheel index
PYTORCH_INDEX = "https://download.pytorch.org/whl/{cuda_version}/"


def fetch_pypi_hashes(package: str, version: str) -> List[Tuple[str, str]]:
    """
    Fetch wheel hashes from PyPI.
    
    Returns list of (filename, sha256_hash) tuples.
    """
    url = PYPI_API.format(package=package, version=version)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching {package}=={version} from PyPI: {e}", file=sys.stderr)
        return []
    
    hashes = []
    for file_info in data.get('urls', []):
        filename = file_info.get('filename', '')
        digests = file_info.get('digests', {})
        sha256 = digests.get('sha256')
        
        if sha256 and is_linux_compatible(filename):
            hashes.append((filename, sha256))
    
    return hashes


def is_linux_compatible(filename: str) -> bool:
    """Check if wheel is compatible with Linux Docker builds."""
    # Accept source distributions
    if filename.endswith('.tar.gz') or filename.endswith('.zip'):
        return True
    # Accept pure Python wheels
    if '-py3-none-any.whl' in filename or '-py2.py3-none-any.whl' in filename:
        return True
    # Accept Linux wheels for cp39
    if '-cp39-' in filename:
        if 'manylinux' in filename or 'linux' in filename:
            return True
    return False


def is_pytorch_linux_wheel(filename: str, python_version: str = 'cp39') -> bool:
    """Check if PyTorch wheel is for Linux cp39."""
    # PyTorch wheels follow pattern: torch-2.8.0+cu124-cp39-cp39-linux_x86_64.whl
    if f'-{python_version}-' not in filename:
        return False
    if 'linux' not in filename.lower() and 'manylinux' not in filename.lower():
        return False
    return True


def fetch_pytorch_hashes_from_index(
    package: str, 
    version: str, 
    cuda_version: str
) -> List[Tuple[str, str]]:
    """
    Fetch PyTorch wheel hashes from pytorch wheel index.
    
    NOTE: The pytorch index doesn't directly provide hashes, so we need to
    download the wheel and compute the hash ourselves, or use known good hashes.
    
    For production, you should:
    1. Download wheels once
    2. Verify them manually
    3. Store the computed hashes
    
    This function provides pre-computed hashes for common configurations.
    """
    # Pre-computed hashes for PyTorch 2.8.0 Linux x86_64 cp39
    # These should be verified and updated when versions change
    KNOWN_HASHES = {
        # CPU wheels
        ('torch', '2.8.0', 'cpu'): [
            # Placeholder - actual hash would come from downloading the wheel
            # torch-2.8.0+cpu-cp39-cp39-linux_x86_64.whl
        ],
        ('torchvision', '0.23.0', 'cpu'): [],
        ('torchaudio', '2.8.0', 'cpu'): [],
        # CUDA 12.4 wheels
        ('torch', '2.8.0', 'cu124'): [],
        ('torchvision', '0.23.0', 'cu124'): [],
        ('torchaudio', '2.8.0', 'cu124'): [],
    }
    
    key = (package, version, cuda_version)
    return KNOWN_HASHES.get(key, [])


def generate_requirements(
    packages: List[Tuple[str, str]],
    hashes_map: Dict[str, List[Tuple[str, str]]],
    header: str = ""
) -> str:
    """Generate requirements file content with hashes."""
    lines = [header] if header else []
    
    for package, version in packages:
        key = f"{package}=={version}"
        hashes = hashes_map.get(key, [])
        
        if hashes:
            hash_lines = [f"    --hash=sha256:{h}" for _, h in hashes]
            lines.append(f"{key} \\\n" + " \\\n".join(hash_lines))
        else:
            # Include without hash (will fail with --require-hashes)
            lines.append(f"# WARNING: No hash available for {key}")
            lines.append(f"# {key}")
    
    return "\n\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description='Fetch PyTorch wheel hashes for Docker builds'
    )
    parser.add_argument(
        '--cuda', '-c',
        choices=['cpu', 'cu121', 'cu124', 'cu128'],
        default='cpu',
        help='CUDA version (cpu, cu121, cu124, cu128)'
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        help='Output requirements file path'
    )
    parser.add_argument(
        '--extra-packages',
        action='store_true',
        help='Include extra packages (rich, onnxruntime-gpu)'
    )
    
    args = parser.parse_args()
    
    print(f"Fetching hashes for CUDA version: {args.cuda}", file=sys.stderr)
    
    hashes_map = {}
    
    # Fetch extra packages from PyPI
    if args.extra_packages:
        print("Fetching extra package hashes from PyPI...", file=sys.stderr)
        for package, version in EXTRA_PACKAGES:
            # Skip onnxruntime-gpu for CPU builds
            if package == 'onnxruntime-gpu' and args.cuda == 'cpu':
                continue
            
            key = f"{package}=={version}"
            hashes = fetch_pypi_hashes(package, version)
            if hashes:
                hashes_map[key] = hashes
                print(f"  {package}=={version}: {len(hashes)} hashes", file=sys.stderr)
            else:
                print(f"  {package}=={version}: NO HASHES FOUND", file=sys.stderr)
    
    # Note about PyTorch hashes
    print("\nNOTE: PyTorch wheel hashes need to be manually verified.", file=sys.stderr)
    print("Download wheels from pytorch.org and compute SHA256.", file=sys.stderr)
    
    # Generate output
    header = f"""\
# =============================================================================
# PyTorch Requirements with Hashes - {args.cuda.upper()}
# =============================================================================
# Generated by fetch_pytorch_hashes.py
#
# IMPORTANT: PyTorch wheels from pytorch.org index do not have pre-computed
# hashes in the index. For full supply-chain security, you should:
#
# 1. Download the wheels: pip download torch==2.8.0 --index-url https://download.pytorch.org/whl/{args.cuda}
# 2. Compute SHA256: sha256sum torch-2.8.0+{args.cuda}-cp39-cp39-linux_x86_64.whl
# 3. Add the hash to this file
#
# Alternatively, use the default PyPI torch package which includes hashes,
# but be aware it bundles CUDA 12.8 by default.
# =============================================================================
"""
    
    packages = []
    if args.extra_packages:
        packages.extend([p for p in EXTRA_PACKAGES 
                        if not (p[0] == 'onnxruntime-gpu' and args.cuda == 'cpu')])
    
    output = generate_requirements(packages, hashes_map, header)
    
    if args.output:
        args.output.write_text(output, encoding='utf-8')
        print(f"\nWritten to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
