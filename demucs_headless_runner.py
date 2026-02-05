#!/usr/bin/env python3
"""
Demucs Headless Runner
用于在没有 GUI 的情况下运行 Demucs 模型分离

使用方法:
    # 使用 v4 htdemucs 模型
    python demucs_headless_runner.py --model htdemucs --input input.wav --output output/
    
    # 使用 6-stem 模型
    python demucs_headless_runner.py --model htdemucs_6s --input input.wav --output output/
    
    # 使用模型名称（自动下载）
    python demucs_headless_runner.py -m "htdemucs_ft" -i input.wav -o output/ --gpu
    
    # 列出可用模型
    python demucs_headless_runner.py --list
    
    # 仅下载模型
    python demucs_headless_runner.py --download "htdemucs_ft"
"""

# Suppress deprecation warnings from librosa's pkg_resources usage
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")

import os
import sys
import time
import argparse
import torch
from pathlib import Path
from types import SimpleNamespace

# Import progress system
from progress import (
    ProgressManager, ProgressStage,
    create_progress_callbacks, create_download_progress_callback
)

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入必需的模块
from separate import SeperateDemucs, prepare_mix
from gui_data.constants import (
    DEMUCS_ARCH_TYPE,
    DEMUCS_V1, DEMUCS_V2, DEMUCS_V3, DEMUCS_V4,
    DEMUCS_V1_TAG, DEMUCS_V2_TAG, DEMUCS_V3_TAG, DEMUCS_V4_TAG,
    DEMUCS_VERSION_MAPPER,
    DEMUCS_2_SOURCE, DEMUCS_4_SOURCE,
    DEMUCS_2_SOURCE_MAPPER, DEMUCS_4_SOURCE_MAPPER, DEMUCS_6_SOURCE_MAPPER,
    DEMUCS_4_SOURCE_LIST, DEMUCS_6_SOURCE_LIST,
    DEMUCS_UVR_MODEL,
    VOCAL_STEM, INST_STEM, DRUM_STEM, BASS_STEM, OTHER_STEM, GUITAR_STEM, PIANO_STEM,
    DEFAULT, CUDA_DEVICE, CPU, ALL_STEMS,
    secondary_stem,
    PRIMARY_STEM
)

# 设备检测
mps_available = torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False
cuda_available = torch.cuda.is_available()
cpu = torch.device('cpu')

# 默认路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DEMUCS_DIR = os.path.join(SCRIPT_DIR, 'models', 'Demucs_Models')
DEFAULT_DEMUCS_V3_V4_DIR = os.path.join(DEFAULT_DEMUCS_DIR, 'v3_v4_repo')

# 模型下载器 (lazy import to avoid circular imports)
_downloader = None

def _get_downloader():
    """Get or create model downloader instance."""
    global _downloader
    if _downloader is None:
        from model_downloader import ModelDownloader
        _downloader = ModelDownloader(base_path=SCRIPT_DIR, verbose=True)
    return _downloader


# ============================================================================
# Model Registry Functions (Phase 2)
# ============================================================================

def list_models(show_installed_only: bool = False, show_uninstalled_only: bool = False) -> list:
    """
    List available Demucs models from official UVR registry.
    
    Args:
        show_installed_only: If True, only show installed models
        show_uninstalled_only: If True, only show uninstalled models
        
    Returns:
        List of model info dictionaries
    """
    downloader = _get_downloader()
    downloader.sync_registry()
    
    models = downloader.list_models('demucs', show_installed=True)
    
    if show_installed_only:
        models = [m for m in models if m['installed']]
    elif show_uninstalled_only:
        models = [m for m in models if not m['installed']]
    
    return models


def get_model_info(model_name: str) -> dict:
    """
    Get detailed information about a specific Demucs model.
    
    Args:
        model_name: Model name or display name
        
    Returns:
        Model info dictionary or None if not found
    """
    downloader = _get_downloader()
    downloader.sync_registry()
    return downloader.get_model_info(model_name, 'demucs')


def download_model(model_name: str) -> tuple:
    """
    Download a specific Demucs model.
    
    Args:
        model_name: Model name or display name
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    downloader = _get_downloader()
    downloader.sync_registry()
    return downloader.download_model(model_name, 'demucs')


def resolve_model_path(model_identifier: str, model_dir: str = None, verbose: bool = True, progress_callback=None) -> str:
    """
    Resolve a model identifier to a local file path.
    
    If the identifier is a path to an existing file, return it.
    If it's a model name, look it up in the registry and download if needed.
    
    Args:
        model_identifier: File path or model name
        model_dir: Optional model directory override
        verbose: Whether to print progress
        progress_callback: Optional download progress callback (current, total, filename)
        
    Returns:
        Local file path to the model
        
    Raises:
        FileNotFoundError: If model cannot be found or downloaded
    """
    # First try the original find_demucs_model_path function
    local_path = find_demucs_model_path(model_identifier, model_dir)
    if local_path:
        return local_path
    
    # Try model downloader
    downloader = _get_downloader()
    if verbose:
        print(f"Looking up model in registry: {model_identifier}")
    
    success, result = downloader.ensure_model(model_identifier, 'demucs', progress_callback=progress_callback)
    
    if success:
        if verbose:
            print(f"Model path: {result}")
        # For Demucs, we need to return the directory containing the yaml/th files
        # The result is the path to one of the files, we need to return the yaml path for v3/v4
        result_dir = os.path.dirname(result)
        result_base = os.path.splitext(os.path.basename(result))[0]
        
        # Check for yaml file (v3/v4 models)
        yaml_path = os.path.join(result_dir, f"{result_base}.yaml")
        if os.path.isfile(yaml_path):
            return yaml_path
        
        return result
    else:
        raise FileNotFoundError(f"Model not found: {model_identifier}. Error: {result}")


def get_demucs_version(model_name):
    """根据模型名称确定 Demucs 版本"""
    for version, tag in DEMUCS_VERSION_MAPPER.items():
        if tag.strip(' | ') in model_name or tag in model_name:
            return version
    
    # 根据模型名称特征判断
    if 'htdemucs' in model_name.lower():
        return DEMUCS_V4
    elif 'hdemucs' in model_name.lower():
        return DEMUCS_V3
    elif model_name.endswith('.gz') or 'demucs' in model_name.lower():
        return DEMUCS_V2
    
    # 默认 v4
    return DEMUCS_V4


def get_demucs_sources(model_name):
    """根据模型名称确定源配置"""
    if DEMUCS_UVR_MODEL in model_name or '2stem' in model_name.lower():
        return DEMUCS_2_SOURCE, DEMUCS_2_SOURCE_MAPPER, 2
    elif '6s' in model_name.lower() or 'htdemucs_6s' in model_name.lower():
        return DEMUCS_6_SOURCE_LIST, DEMUCS_6_SOURCE_MAPPER, 6
    else:
        return DEMUCS_4_SOURCE, DEMUCS_4_SOURCE_MAPPER, 4


def find_demucs_model_path(model_name, model_dir=None):
    """查找 Demucs 模型路径"""
    search_dirs = []
    
    if model_dir:
        search_dirs.append(model_dir)
    
    # 默认搜索路径
    search_dirs.extend([
        DEFAULT_DEMUCS_V3_V4_DIR,
        DEFAULT_DEMUCS_DIR,
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs',
                     'Ultimate Vocal Remover', 'models', 'Demucs_Models', 'v3_v4_repo'),
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs',
                     'Ultimate Vocal Remover', 'models', 'Demucs_Models'),
    ])
    
    # 如果是完整路径
    if os.path.isfile(model_name):
        return model_name
    
    # 搜索模型文件
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        
        # 尝试 YAML 配置文件 (v3/v4)
        yaml_path = os.path.join(search_dir, f'{model_name}.yaml')
        if os.path.isfile(yaml_path):
            return yaml_path
        
        # 尝试 .th 文件
        th_path = os.path.join(search_dir, f'{model_name}.th')
        if os.path.isfile(th_path):
            return th_path
        
        # 尝试 .gz 文件 (v1)
        gz_path = os.path.join(search_dir, f'{model_name}.gz')
        if os.path.isfile(gz_path):
            return gz_path
        
        # 尝试 .pth 文件 (v2)
        pth_path = os.path.join(search_dir, f'{model_name}.pth')
        if os.path.isfile(pth_path):
            return pth_path
    
    return None


# ============================================================================
# IMPORTANT:
# This logic MUST stay behavior-identical to UVR GUI.
# Do NOT refactor, "optimize", or reinterpret unless UVR itself changes.
# ============================================================================
def create_demucs_model_data(model_path, **kwargs):
    """创建 Demucs 模型的 ModelData 对象 - 严格复制 UVR GUI 的 ModelData 结构"""
    model_data = SimpleNamespace()
    
    model_name = os.path.splitext(os.path.basename(model_path))[0]
    
    # ========== 基本信息 ==========
    model_data.model_path = model_path
    model_data.model_name = model_name
    model_data.model_basename = model_name
    model_data.process_method = DEMUCS_ARCH_TYPE
    
    # ========== Demucs 特定参数 ==========
    demucs_version = kwargs.get('demucs_version')
    model_data.demucs_version = demucs_version if demucs_version else get_demucs_version(model_name)
    
    source_list, source_map, stem_count = get_demucs_sources(model_name)
    model_data.demucs_source_list = kwargs.get('demucs_source_list', source_list)
    model_data.demucs_source_map = kwargs.get('demucs_source_map', source_map)
    model_data.demucs_stem_count = kwargs.get('demucs_stem_count', stem_count)
    
    model_data.demucs_stems = kwargs.get('demucs_stems', ALL_STEMS)
    model_data.is_chunk_demucs = kwargs.get('is_chunk_demucs', False)
    model_data.segment = kwargs.get('segment', 'Default')
    model_data.shifts = kwargs.get('shifts', 2)
    model_data.is_split_mode = kwargs.get('is_split_mode', True)
    model_data.is_demucs_combine_stems = kwargs.get('is_demucs_combine_stems', True)
    
    # ========== 设备设置 ==========
    use_gpu = kwargs.get('use_gpu', cuda_available)
    model_data.is_gpu_conversion = 0 if use_gpu else -1
    model_data.device_set = kwargs.get('device_set', '0')
    model_data.is_use_opencl = False
    model_data.is_use_directml = kwargs.get('is_use_directml', False)  # For AMD GPUs
    
    # ========== Stem 设置 ==========
    primary_only = kwargs.get('primary_only', False)
    secondary_only = kwargs.get('secondary_only', False)
    
    if primary_only and secondary_only:
        secondary_only = False
    
    model_data.is_primary_stem_only = primary_only
    model_data.is_secondary_stem_only = secondary_only
    
    # 设置 primary/secondary stem
    if model_data.demucs_stems == ALL_STEMS:
        model_data.primary_stem = PRIMARY_STEM
    else:
        model_data.primary_stem = model_data.demucs_stems
    model_data.secondary_stem = secondary_stem(model_data.primary_stem)
    model_data.primary_stem_native = model_data.primary_stem
    
    # ========== 输出设置 ==========
    model_data.wav_type_set = kwargs.get('wav_type_set', 'PCM_24')  # 默认 24-bit
    model_data.save_format = kwargs.get('save_format', 'WAV')
    model_data.mp3_bit_set = kwargs.get('mp3_bit_set', None)
    model_data.is_normalization = kwargs.get('is_normalization', True)
    
    # ========== 二级模型 ==========
    model_data.is_secondary_model_activated = False
    model_data.is_secondary_model = False
    model_data.secondary_model = None
    model_data.secondary_model_scale = None
    model_data.primary_model_primary_stem = None
    model_data.is_pre_proc_model = False
    model_data.pre_proc_model = None
    model_data.secondary_model_4_stem = [None, None, None, None]
    model_data.secondary_model_4_stem_scale = [None, None, None, None]
    
    # ========== Vocal Split ==========
    model_data.vocal_split_model = None
    model_data.is_vocal_split_model = False
    model_data.is_save_inst_vocal_splitter = False
    model_data.is_inst_only_voc_splitter = False
    model_data.is_save_vocal_only = False
    
    # ========== Denoise/Deverb ==========
    model_data.is_denoise = False
    model_data.is_denoise_model = False
    model_data.DENOISER_MODEL = None
    model_data.DEVERBER_MODEL = None
    model_data.is_deverb_vocals = False
    model_data.deverb_vocal_opt = None
    
    # ========== Pitch ==========
    model_data.is_pitch_change = False
    model_data.semitone_shift = 0.0
    model_data.is_match_frequency_pitch = False
    
    # ========== Ensemble ==========
    model_data.is_ensemble_mode = False
    model_data.ensemble_primary_stem = None
    model_data.ensemble_secondary_stem = None
    model_data.is_multi_stem_ensemble = False
    model_data.is_4_stem_ensemble = False
    
    # ========== 其他标志 ==========
    model_data.mixer_path = None
    model_data.model_samplerate = 44100
    model_data.is_invert_spec = kwargs.get('is_invert_spec', False)
    model_data.is_mixer_mode = False
    model_data.is_karaoke = False
    model_data.is_bv_model = False
    model_data.bv_model_rebalance = 0
    model_data.is_sec_bv_rebalance = False
    model_data.is_demucs_pre_proc_model_inst_mix = False
    model_data.overlap = kwargs.get('overlap', 0.25)
    model_data.overlap_mdx = kwargs.get('overlap_mdx', 0.25)
    model_data.overlap_mdx23 = kwargs.get('overlap_mdx23', 8)
    
    # ========== MDX 相关（Demucs 不使用，但 SeperateAttributes 需要） ==========
    model_data.is_mdx_combine_stems = False
    model_data.is_mdx_c = False
    model_data.mdx_c_configs = None
    model_data.mdxnet_stem_select = None
    model_data.model_capacity = (32, 128)
    model_data.is_vr_51_model = False
    model_data.is_target_instrument = False
    model_data.is_roformer = False
    
    return model_data


def create_process_data(audio_file, export_path, audio_file_base=None, 
                        progress_manager: ProgressManager = None, **kwargs):
    """
    创建 process_data 字典
    
    Args:
        audio_file: 输入音频文件路径
        export_path: 输出目录路径
        audio_file_base: 输出文件基名
        progress_manager: 进度管理器实例（可选）
        **kwargs: 其他参数
    """
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    verbose = kwargs.get('verbose', False)
    
    # 如果提供了 progress_manager，使用它创建回调
    if progress_manager is not None:
        callbacks = create_progress_callbacks(progress_manager, total_iterations=100)
        set_progress_bar = callbacks['set_progress_bar']
        write_to_console = callbacks['write_to_console']
        process_iteration = callbacks['process_iteration']
    else:
        def set_progress_bar(step=0, inference_iterations=0):
            pass
        
        def write_to_console(text, base_text=''):
            if verbose:
                msg = f"{base_text}{text}".strip()
                if msg:
                    print(msg)
        
        def process_iteration():
            pass
    
    return {
        'audio_file': audio_file,
        'export_path': export_path,
        'audio_file_base': audio_file_base,
        'set_progress_bar': set_progress_bar,
        'write_to_console': write_to_console,
        'process_iteration': process_iteration,
        'cached_source_callback': lambda *args, **kw: (None, None),
        'cached_model_source_holder': lambda *args, **kw: None,
        'list_all_models': [],
        'is_ensemble_master': False,
        'is_4_stem_ensemble': False,
        'is_multi_stem_ensemble': False,
    }


def run_demucs_headless(
    model_path,
    audio_file,
    export_path,
    audio_file_base=None,
    use_gpu=None,
    device_set='0',
    is_use_directml=False,
    demucs_version=None,
    segment='Default',
    shifts=2,
    overlap=0.25,
    wav_type_set='PCM_24',
    demucs_stems=ALL_STEMS,  # ALL_STEMS 或单个 stem 名称 (Vocals/Other/Bass/Drums/Guitar/Piano)
    primary_only=False,
    secondary_only=False,
    verbose=True,
    progress_manager: ProgressManager = None
):
    """
    运行 Demucs 分离的主函数（严格按照 GUI 行为）
    
    Args:
        model_path: 模型文件路径或模型名称
        audio_file: 输入音频文件路径
        export_path: 输出目录路径
        audio_file_base: 输出文件基名（可选）
        use_gpu: 是否使用 GPU（默认自动检测）
        device_set: GPU 设备 ID
        demucs_version: Demucs 版本 (v1/v2/v3/v4)
        segment: 分段大小
        shifts: 时间偏移次数
        overlap: 重叠率
        demucs_stems: ALL_STEMS（输出所有）或单个 stem 名称（只输出该 stem）
        primary_only: 只输出 primary stem
        secondary_only: 只输出 secondary stem
        verbose: 是否显示详细输出
        progress_manager: 进度管理器实例（可选）
    
    Returns:
        输出文件路径字典
    """
    start_time = time.time()
    
    # 如果没有提供 progress_manager，创建一个默认的
    pm = progress_manager or ProgressManager(verbose=verbose)
    pm.set_file_name(os.path.basename(audio_file))
    
    # 确保输出目录存在
    os.makedirs(export_path, exist_ok=True)
    
    # 处理音频文件基名
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    # 转换 wav_type 名称为 soundfile 格式
    wav_type_map = {
        'PCM_U8': 'PCM_U8',
        'PCM_16': 'PCM_16',
        'PCM_24': 'PCM_24',
        'PCM_32': 'PCM_32',
        'FLOAT': 'FLOAT',
        'DOUBLE': 'DOUBLE',
        '32-bit Float': 'FLOAT',
        '64-bit Float': 'DOUBLE'
    }
    wav_type = wav_type_map.get(wav_type_set, 'PCM_24')
    
    # 创建 model_data
    pm.start_stage(ProgressStage.LOADING_MODEL, "Loading Demucs model configuration")
    pm.set_model_name(os.path.basename(model_path))
    
    model_data = create_demucs_model_data(
        model_path,
        use_gpu=use_gpu if use_gpu is not None else cuda_available,
        device_set=device_set,
        is_use_directml=is_use_directml,
        demucs_version=demucs_version,
        segment=segment,
        shifts=shifts,
        overlap=overlap,
        wav_type_set=wav_type,
        demucs_stems=demucs_stems,
        primary_only=primary_only,
        secondary_only=secondary_only,
        verbose=False
    )
    pm.finish_stage("Model configuration loaded")
    
    # 创建 process_data
    process_data = create_process_data(
        audio_file, export_path, audio_file_base,
        progress_manager=pm, verbose=verbose
    )
    
    # 打印 header 信息
    device_str = 'CPU'
    if model_data.is_gpu_conversion >= 0:
        if is_use_directml:
            device_str = f"DirectML:{device_set}"
        elif cuda_available:
            device_str = f"CUDA:{device_set}"
    
    # Build output stems string for header
    output_stems = None
    if demucs_stems == ALL_STEMS:
        output_stems = "All Stems"
    elif model_data.primary_stem:
        if model_data.is_primary_stem_only:
            output_stems = model_data.primary_stem
        elif model_data.is_secondary_stem_only and model_data.secondary_stem:
            output_stems = model_data.secondary_stem
        elif model_data.secondary_stem:
            output_stems = f"{model_data.primary_stem}, {model_data.secondary_stem}"
        else:
            output_stems = model_data.primary_stem
    
    pm.print_header(
        model_name=os.path.basename(model_path),
        input_file=audio_file,
        output_path=export_path,
        device=device_str,
        arch_type=f"Demucs ({model_data.demucs_version})",
        output_stems=output_stems
    )
    
    # 运行分离（严格按照 GUI 行为，由 separate.py 控制输出）
    pm.start_stage(ProgressStage.INFERENCE, "Running Demucs separation", total=100)
    
    separator = SeperateDemucs(model_data, process_data)
    separator.seperate()
    
    pm.finish_stage("Audio separation complete")
    
    # 记录输出文件
    if demucs_stems == ALL_STEMS:
        for stem_name in model_data.demucs_source_map.keys():
            output_file = os.path.join(export_path, f"{audio_file_base}_({stem_name}).wav")
            if os.path.isfile(output_file):
                pm.add_output_file(output_file)
    else:
        for stem_name in [model_data.primary_stem, model_data.secondary_stem]:
            if stem_name:
                output_file = os.path.join(export_path, f"{audio_file_base}_({stem_name}).wav")
                if os.path.isfile(output_file):
                    pm.add_output_file(output_file)
    
    elapsed = time.time() - start_time
    if verbose:
        pm.write_message(f"\n✓ Total processing time: {elapsed:.1f}s", "green")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='Demucs Headless Runner - 使用 Demucs 模型进行音频分离（严格按照 GUI 行为）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 输出所有 stems（等同于 GUI "All Stems"）
    python demucs_headless_runner.py --model htdemucs --input song.wav --output ./output --gpu
    
    # 使用模型名称（自动下载）
    python demucs_headless_runner.py -m "htdemucs_ft" -i song.wav -o ./output --gpu
    
    # 选择 Vocals stem（输出 Vocals + Instrumental，等同于 GUI 选择 "Vocals"）
    python demucs_headless_runner.py --model htdemucs --input song.wav --output ./output --gpu --stem Vocals
    
    # 只输出 Vocals 一个文件（等同于 GUI 选择 "Vocals" + 勾选 "Primary Stem Only"）
    python demucs_headless_runner.py --model htdemucs --input song.wav --output ./output --gpu --stem Vocals --primary-only
    
    # 只输出伴奏（选择 Vocals 但只要 secondary = Instrumental）
    python demucs_headless_runner.py --model htdemucs --input song.wav --output ./output --gpu --stem Vocals --secondary-only
    
    # 列出可用模型
    python demucs_headless_runner.py --list
    
    # 下载模型
    python demucs_headless_runner.py --download "htdemucs_ft"

可用的 stem 选项:
    4-stem 模型: Vocals, Other, Bass, Drums
    6-stem 模型: Vocals, Other, Bass, Drums, Guitar, Piano

说明:
    --stem X              选择 stem X 为 primary，输出 X 和对应的 secondary
    --stem X --primary-only   只输出 stem X
    --stem X --secondary-only 只输出 stem X 的 secondary（互补）
"""
    )
    
    # Model registry and download options
    registry_group = parser.add_argument_group('Model Registry')
    registry_group.add_argument('--list', action='store_true', 
                                help='列出可用的 Demucs 模型')
    registry_group.add_argument('--list-installed', action='store_true',
                                help='只列出已安装的模型')
    registry_group.add_argument('--list-uninstalled', action='store_true',
                                help='只列出未安装的模型')
    registry_group.add_argument('--download', metavar='MODEL_NAME',
                                help='下载模型（不进行推理）')
    registry_group.add_argument('--model-info', metavar='MODEL_NAME',
                                help='显示模型详细信息')
    
    parser.add_argument('--model', '-m', help='模型名称或路径（支持自动下载）')
    parser.add_argument('--model-dir', help='模型目录路径')
    parser.add_argument('--input', '-i', help='输入音频文件路径')
    parser.add_argument('--output', '-o', help='输出目录路径')
    parser.add_argument('--name', '-n', help='输出文件基名')
    
    parser.add_argument('--gpu', action='store_true', help='使用 GPU')
    parser.add_argument('--cpu', action='store_true', help='强制使用 CPU')
    parser.add_argument('--directml', action='store_true', help='使用 DirectML (AMD GPU)')
    parser.add_argument('--device', '-d', default='0', help='GPU 设备 ID (默认: 0)')
    
    parser.add_argument('--shifts', type=int, default=2, help='时间偏移次数 (默认: 2)')
    parser.add_argument('--overlap', type=float, default=0.25, help='重叠率 (默认: 0.25)')
    parser.add_argument('--segment', default='Default', help='分段大小 (默认: Default)')
    parser.add_argument('--wav-type', default='PCM_24',
                        choices=['PCM_U8', 'PCM_16', 'PCM_24', 'PCM_32', 'FLOAT', 'DOUBLE'],
                        help='输出音频位深度 (默认: PCM_24)')
    
    parser.add_argument('--stem', help='只输出指定 stem (Vocals/Other/Bass/Drums，6-stem 模型还有 Guitar/Piano)，不指定则输出全部')
    parser.add_argument('--primary-only', action='store_true', help='只输出 primary stem')
    parser.add_argument('--secondary-only', action='store_true', help='只输出 secondary stem')
    
    parser.add_argument('--quiet', '-q', action='store_true', help='安静模式')
    
    args = parser.parse_args()
    
    # Handle model registry operations first
    if args.list or args.list_installed or args.list_uninstalled:
        try:
            models = list_models(
                show_installed_only=args.list_installed,
                show_uninstalled_only=args.list_uninstalled
            )
            
            label = "Installed" if args.list_installed else "Uninstalled" if args.list_uninstalled else "Available"
            print(f"\n{label} Demucs Models:")
            print("=" * 60)
            
            if not models:
                print(f"  No {label.lower()} models found.")
            else:
                for model in models:
                    status = "Y" if model['installed'] else "N"
                    print(f"  [{status}] {model['name']}")
                print(f"\nTotal: {len(models)} models")
            
            return 0
        except Exception as e:
            print(f"Error listing models: {e}", file=sys.stderr)
            return 1
    
    if args.download:
        try:
            print(f"下载模型: {args.download}")
            success, message = download_model(args.download)
            print(message)
            return 0 if success else 1
        except Exception as e:
            print(f"下载模型时出错: {e}", file=sys.stderr)
            return 1
    
    if args.model_info:
        try:
            info = get_model_info(args.model_info)
            if info:
                print(f"\n模型信息: {info['name']}")
                print("=" * 60)
                print(f"  显示名称: {info['display_name']}")
                print(f"  已安装: {'是' if info['installed'] else '否'}")
                print(f"  目录: {info['subdir']}")
                if info.get('is_multi_file'):
                    print(f"  文件:")
                    for f in info['files'].keys():
                        print(f"    - {f}")
            else:
                print(f"未找到模型: {args.model_info}")
                return 1
            return 0
        except Exception as e:
            print(f"获取模型信息时出错: {e}", file=sys.stderr)
            return 1
    
    # Import error handler
    from error_handler import (
        classify_error, format_error_message, ErrorCategory,
        validate_audio_file, validate_output_directory
    )
    
    # Validate required arguments for inference
    if not args.model:
        parser.error("--model is required for inference (or use --list/--download for model management)")
    if not args.input:
        parser.error("--input is required for inference")
    if not args.output:
        parser.error("--output is required for inference")
    
    # Validate input file
    is_valid, msg = validate_audio_file(args.input)
    if not is_valid:
        print(f"Error: {msg}", file=sys.stderr)
        return 1
    
    # Validate output directory
    is_valid, msg = validate_output_directory(args.output)
    if not is_valid:
        print(f"Error: {msg}", file=sys.stderr)
        return 1
    
    # 确定 GPU 使用
    if args.cpu:
        use_gpu = False
    elif args.gpu:
        use_gpu = True
    else:
        use_gpu = cuda_available
    
    # 确定 stems 选择（严格按照 GUI：ALL_STEMS 或单个 stem）
    demucs_stems = ALL_STEMS
    if args.stem:
        demucs_stems = args.stem
    
    # Try GPU first, fall back to CPU on GPU errors
    gpu_fallback_attempted = False
    current_use_gpu = use_gpu
    
    # Use ProgressManager for beautiful CLI output
    with ProgressManager(verbose=not args.quiet) as pm:
        # 查找模型路径（支持自动下载，包含进度显示）
        try:
            from progress import create_download_progress_callback
            download_callback = create_download_progress_callback(pm)
            model_path = resolve_model_path(
                args.model, args.model_dir, 
                verbose=not args.quiet,
                progress_callback=download_callback
            )
        except FileNotFoundError as e:
            pm.write_message(f"错误: {e}", "red")
            pm.write_message(f"搜索的目录:", "yellow")
            pm.write_message(f"  - {DEFAULT_DEMUCS_V3_V4_DIR}")
            pm.write_message(f"  - {DEFAULT_DEMUCS_DIR}")
            return 1
        while True:
            try:
                run_demucs_headless(
                    model_path=model_path,
                    audio_file=args.input,
                    export_path=args.output,
                    audio_file_base=args.name,
                    use_gpu=current_use_gpu,
                    device_set=args.device,
                    is_use_directml=args.directml if not gpu_fallback_attempted else False,
                    shifts=args.shifts,
                    overlap=args.overlap,
                    segment=args.segment,
                    wav_type_set=args.wav_type,
                    demucs_stems=demucs_stems,
                    primary_only=args.primary_only,
                    secondary_only=args.secondary_only,
                    verbose=not args.quiet,
                    progress_manager=pm
                )
                
                return 0
                
            except Exception as e:
                error_info = classify_error(e)
                
                # Check if GPU error and can fall back to CPU
                if (error_info["category"] == ErrorCategory.GPU 
                    and error_info["recoverable"] 
                    and not gpu_fallback_attempted
                    and current_use_gpu is not False):
                    
                    pm.write_message(format_error_message(error_info, verbose=not args.quiet), "yellow")
                    pm.write_message("Attempting to fall back to CPU mode...\n", "yellow")
                    
                    gpu_fallback_attempted = True
                    current_use_gpu = False
                    
                    # Clear GPU memory if possible
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except:
                        pass
                    
                    continue  # Retry with CPU
                
                # Non-recoverable error or already tried fallback
                pm.write_message(format_error_message(error_info, verbose=not args.quiet), "red")
                
                if not args.quiet:
                    import traceback
                    traceback.print_exc()
                
                return 1


if __name__ == '__main__':
    sys.exit(main())
