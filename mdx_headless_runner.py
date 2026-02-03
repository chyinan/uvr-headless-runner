#!/usr/bin/env python3
"""
MDX-Net Headless Runner
Run MDX-Net model separation without GUI

Usage:
    python mdx_headless_runner.py --model model.ckpt --input input.wav --output output/
    
    # Use JSON config file (for non-standard models)
    python mdx_headless_runner.py --model model.ckpt --json config.json --input input.wav --output output/
"""

import os
import sys
import json
import math
import hashlib
import torch
import argparse
import yaml
from pathlib import Path
from types import SimpleNamespace

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入必需的模块
from separate import SeperateMDX, SeperateMDXC, prepare_mix
from gui_data.constants import (
    MDX_ARCH_TYPE,
    VOCAL_STEM,
    INST_STEM,
    DEFAULT,
    CUDA_DEVICE,
    CPU,
    secondary_stem,
    ALL_STEMS,
    DRUM_STEM,
    BASS_STEM,
    OTHER_STEM
)

# ml_collections 替代
try:
    from ml_collections import ConfigDict
except ImportError:
    # 如果没有 ml_collections，使用简单的 dict 包装
    class ConfigDict(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for key, value in self.items():
                if isinstance(value, dict):
                    self[key] = ConfigDict(value)
        
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                raise AttributeError(key)
        
        def __setattr__(self, key, value):
            self[key] = value

# 设备检测
mps_available = torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False
cuda_available = torch.cuda.is_available()
cpu = torch.device('cpu')

# 默认路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL_DATA_JSON = os.path.join(SCRIPT_DIR, 'models', 'MDX_Net_Models', 'model_data', 'model_data.json')
DEFAULT_MDX_C_CONFIG_PATH = os.path.join(SCRIPT_DIR, 'models', 'MDX_Net_Models', 'model_data', 'mdx_c_configs')


def get_model_hash(model_path):
    """
    计算模型文件的 MD5 哈希（与 UVR 完全一致）
    
    UVR 读取文件的最后 10MB（10000 * 1024 字节）来计算哈希。
    如果文件小于 10MB，则读取整个文件。
    """
    try:
        with open(model_path, 'rb') as f:
            # 与 UVR.py get_model_hash() 完全一致：读取最后 10MB
            try:
                f.seek(-10000 * 1024, 2)  # 从文件末尾向前 10MB
                return hashlib.md5(f.read()).hexdigest()
            except OSError:
                # 文件小于 10MB，读取整个文件
                f.seek(0)
                return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        print(f"Warning: Cannot compute model hash: {e}")
        return None


def load_model_data_json(json_path=None, model_path=None):
    """
    加载 model_data.json
    
    优先从模型文件所在目录的 model_data 子目录查找，
    这与 UVR GUI 的行为一致。
    """
    paths_to_try = [json_path] if json_path else []
    
    # 如果提供了模型路径，从模型目录派生 model_data.json 路径
    if model_path:
        model_dir = os.path.dirname(model_path)
        paths_to_try.append(os.path.join(model_dir, 'model_data', 'model_data.json'))
    
    # 添加默认路径
    paths_to_try.extend([
        DEFAULT_MODEL_DATA_JSON,
        os.path.join(os.path.dirname(sys.executable), 'models', 'MDX_Net_Models', 'model_data', 'model_data.json'),
        # UVR 常见安装路径
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs', 
                     'Ultimate Vocal Remover', 'models', 'MDX_Net_Models', 'model_data', 'model_data.json'),
    ])
    
    for path in paths_to_try:
        if path and os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f), path
            except Exception as e:
                print(f"Warning: Cannot load {path}: {e}")
    return {}, None


def find_mdx_c_config_path(config_yaml, model_path=None):
    """
    查找 MDX-C 配置文件
    
    优先从模型文件所在目录的 model_data/mdx_c_configs 子目录查找，
    这与 UVR GUI 的行为一致。
    """
    paths_to_try = []
    
    # 如果提供了模型路径，从模型目录派生配置路径
    if model_path:
        model_dir = os.path.dirname(model_path)
        paths_to_try.append(os.path.join(model_dir, 'model_data', 'mdx_c_configs', config_yaml))
    
    paths_to_try.extend([
        os.path.join(DEFAULT_MDX_C_CONFIG_PATH, config_yaml),
        os.path.join(os.path.dirname(sys.executable), 'models', 'MDX_Net_Models', 'model_data', 'mdx_c_configs', config_yaml),
        # UVR 常见安装路径
        os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs', 
                     'Ultimate Vocal Remover', 'models', 'MDX_Net_Models', 'model_data', 'mdx_c_configs', config_yaml),
    ])
    
    for path in paths_to_try:
        if os.path.isfile(path):
            return path
    return None


def create_model_data(model_path, **kwargs):
    """
    创建完全兼容 UVR 的 ModelData 对象
    
    Args:
        model_path: 模型文件路径 (.ckpt 或 .onnx)
        **kwargs: 可选参数覆盖
        
    Returns:
        SimpleNamespace: 包含所有必需属性的对象
    """
    verbose = kwargs.get('verbose', False)
    model_json_path = kwargs.get('model_json_path')
    
    model_data = SimpleNamespace()
    
    # ========== 基本信息 ==========
    model_data.model_path = model_path
    model_data.model_name = os.path.splitext(os.path.basename(model_path))[0]
    model_data.model_basename = model_data.model_name
    model_data.process_method = MDX_ARCH_TYPE
    model_data.is_mdx_ckpt = model_path.endswith('.ckpt')
    model_data.is_mdx_c = False
    model_data.is_roformer = False  # Roformer support
    model_data.is_target_instrument = False  # MDX-C target instrument mode
    model_data.mdx_c_configs = None
    model_data.mdx_model_stems = []
    model_data.mdx_stem_count = 1
    
    # ========== 设备设置 ==========
    use_gpu = kwargs.get('use_gpu', cuda_available)
    model_data.is_gpu_conversion = 0 if use_gpu else -1
    model_data.device_set = kwargs.get('device_set', '0')
    model_data.is_use_opencl = False
    model_data.is_use_directml = kwargs.get('is_use_directml', False)  # For AMD GPUs
    
    # ========== 处理参数 ==========
    model_data.mdx_segment_size = kwargs.get('mdx_segment_size', 256)
    model_data.overlap_mdx = kwargs.get('overlap_mdx', 0.25)
    model_data.overlap_mdx23 = kwargs.get('overlap_mdx23', 2)  # GUI 默认是 2
    model_data.mdx_batch_size = kwargs.get('mdx_batch_size', 1)
    model_data.margin = kwargs.get('margin', 0)
    model_data.chunks = kwargs.get('chunks', 0)
    model_data.overlap = 0.25
    
    # ========== 输出设置 ==========
    model_data.wav_type_set = kwargs.get('wav_type_set', 'PCM_24')  # 默认 24-bit
    model_data.save_format = kwargs.get('save_format', 'WAV')
    model_data.mp3_bit_set = kwargs.get('mp3_bit_set', None)
    model_data.is_normalization = kwargs.get('is_normalization', True)
    
    # ========== 输出控制 ==========
    primary_only = kwargs.get('primary_only', False)
    secondary_only = kwargs.get('secondary_only', False)
    
    # Alias 支持
    if kwargs.get('dry_only', False) or kwargs.get('vocals_only', False):
        primary_only = True
    if kwargs.get('no_dry_only', False) or kwargs.get('instrumental_only', False):
        secondary_only = True
    
    if primary_only and secondary_only:
        secondary_only = False
        if verbose:
            print("Warning: Both primary-only and secondary-only specified, using primary-only")
    
    model_data.is_primary_stem_only = primary_only
    model_data.is_secondary_stem_only = secondary_only
    
    # ========== 二级模型和预处理 ==========
    model_data.is_secondary_model_activated = False
    model_data.is_secondary_model = False
    model_data.secondary_model = None
    model_data.secondary_model_scale = None
    model_data.primary_model_primary_stem = None
    model_data.is_pre_proc_model = False
    model_data.is_primary_model_primary_stem_only = False
    model_data.is_primary_model_secondary_stem_only = False
    
    # ========== Vocal Split ==========
    model_data.vocal_split_model = None
    model_data.is_vocal_split_model = False
    model_data.is_save_inst_vocal_splitter = False
    model_data.is_inst_only_voc_splitter = False
    model_data.is_save_vocal_only = False
    
    # ========== Denoise/Deverb ==========
    model_data.is_denoise = kwargs.get('is_denoise', False)
    model_data.is_denoise_model = kwargs.get('is_denoise_model', False)
    model_data.DENOISER_MODEL = kwargs.get('denoiser_model', None)
    model_data.DEVERBER_MODEL = kwargs.get('deverber_model', None)
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
    model_data.model_capacity = (32, 128)
    model_data.is_vr_51_model = False
    model_data.mdxnet_stem_select = kwargs.get('mdxnet_stem_select', ALL_STEMS)
    model_data.is_mdx_combine_stems = kwargs.get('is_mdx_combine_stems', False)
    model_data.is_invert_spec = kwargs.get('is_invert_spec', False)
    model_data.is_mixer_mode = False
    model_data.is_karaoke = False
    model_data.is_bv_model = False
    model_data.bv_model_rebalance = 0
    model_data.is_sec_bv_rebalance = False
    model_data.is_demucs_pre_proc_model_inst_mix = False
    model_data.is_mdx_c_seg_def = kwargs.get('is_mdx_c_seg_def', True)
    
    # MDX 参数默认值（可能被后续加载覆盖）
    model_data.compensate = kwargs.get('compensate', 1.035)
    model_data.mdx_dim_f_set = kwargs.get('mdx_dim_f_set', 3072)
    model_data.mdx_dim_t_set = kwargs.get('mdx_dim_t_set', 8)
    model_data.mdx_n_fft_scale_set = kwargs.get('mdx_n_fft_scale_set', 6144)
    model_data.primary_stem = None
    model_data.primary_stem_native = None
    model_data.secondary_stem = None
    
    # ========== 加载模型参数 ==========
    _load_model_config(model_data, model_path, **kwargs)
    
    return model_data


# ============================================================================
# IMPORTANT:
# This logic MUST stay behavior-identical to UVR GUI.
# Do NOT refactor, "optimize", or reinterpret unless UVR itself changes.
# ============================================================================
def _load_model_config(model_data, model_path, **kwargs):
    """
    加载模型配置 - 完全复制 UVR GUI 的 pop_up_mdx_model() 行为
    
    回退链（与 GUI 完全一致）:
    1. 用户提供的配置文件（--json）
    2. 哈希查找（model_data.json + hash_mapper）
    3. 从模型文件自动检测（.ckpt → hyper_parameters / .onnx → tensor shape）
    4. CLI 参数覆盖
    5. UVR GUI 默认值
    """
    verbose = kwargs.get('verbose', False)
    model_json_path = kwargs.get('model_json_path')
    
    # 计算模型哈希（与 UVR.py get_model_hash() 完全一致）
    model_hash = get_model_hash(model_path)
    if verbose and model_hash:
        print(f"Model hash: {model_hash}")
    
    # ========== 步骤 1: 用户提供的配置文件（--json）==========
    if model_json_path and os.path.isfile(model_json_path):
        try:
            if model_json_path.endswith('.yaml') or model_json_path.endswith('.yml'):
                # YAML 配置（MDX-C/Roformer 模型）
                with open(model_json_path, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.load(f, Loader=yaml.FullLoader)
                
                model_data.is_mdx_c = True
                model_data.is_mdx_ckpt = False
                model_data.mdx_c_configs = ConfigDict(yaml_config)
                
                if verbose:
                    print(f"Loaded config from YAML: {model_json_path}")
                
                training = model_data.mdx_c_configs.get('training', {})
                if training.get('target_instrument'):
                    target = training['target_instrument']
                    model_data.mdx_model_stems = [target]
                    model_data.primary_stem = target
                else:
                    instruments = training.get('instruments', ['Vocals', 'Instrumental'])
                    model_data.mdx_model_stems = instruments
                    model_data.mdx_stem_count = len(instruments)
                    model_data.primary_stem = instruments[0] if instruments else VOCAL_STEM
                
                model_data.primary_stem_native = model_data.primary_stem
                model_data.secondary_stem = secondary_stem(model_data.primary_stem)
                return
            else:
                # JSON 配置
                with open(model_json_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                if verbose:
                    print(f"Loaded config from JSON: {model_json_path}")
                
                _apply_config(model_data, config, kwargs, verbose, model_path)
                return
        except Exception as e:
            print(f"Warning: Cannot load from config file: {e}")
    
    # ========== 步骤 2: 哈希查找（与 UVR get_model_data() 一致）==========
    # 2a: 首先检查单独的 {hash}.json 文件（UVR.py 第 741-744 行）
    if model_hash:
        model_dir = os.path.dirname(model_path)
        hash_json_paths = [
            os.path.join(model_dir, 'model_data', f'{model_hash}.json'),
            os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Programs',
                         'Ultimate Vocal Remover', 'models', 'MDX_Net_Models', 'model_data', f'{model_hash}.json'),
        ]
        
        for hash_json_path in hash_json_paths:
            if os.path.isfile(hash_json_path):
                try:
                    with open(hash_json_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    if verbose:
                        print(f"Loaded config from hash JSON: {os.path.basename(hash_json_path)}")
                    _apply_config(model_data, config, kwargs, verbose, model_path)
                    return
                except Exception as e:
                    print(f"Warning: Cannot load {hash_json_path}: {e}")
    
    # 2b: 检查 model_data.json 中的哈希映射
    model_data_db, db_path = load_model_data_json(model_path=model_path)
    
    if model_hash and model_hash in model_data_db:
        config = model_data_db[model_hash]
        if verbose:
            print(f"Loaded config from model_data.json (hash: {model_hash[:8]}...)")
        
        _apply_config(model_data, config, kwargs, verbose, model_path)
        return
    
    # ========== 步骤 3: 从模型文件自动检测（pop_up_mdx_model 的核心逻辑）==========
    auto_detected = _auto_detect_from_model_file(model_data, model_path, kwargs, verbose)
    
    if auto_detected:
        return
    
    # ========== 步骤 4: 使用 CLI 参数和 UVR GUI 默认值 ==========
    if verbose:
        print("Using CLI arguments + UVR GUI defaults")
    
    # 使用 CLI 参数覆盖，否则使用 UVR GUI 的默认值
    model_data.mdx_dim_f_set = kwargs.get('mdx_dim_f_set', 3072)
    model_data.mdx_dim_t_set = kwargs.get('mdx_dim_t_set', 8)
    model_data.mdx_n_fft_scale_set = kwargs.get('mdx_n_fft_scale_set', 6144)
    model_data.compensate = kwargs.get('compensate', 1.035)
    model_data.primary_stem = kwargs.get('primary_stem', VOCAL_STEM)
    model_data.primary_stem_native = model_data.primary_stem
    model_data.secondary_stem = secondary_stem(model_data.primary_stem)


def _auto_detect_from_model_file(model_data, model_path, kwargs, verbose=False):
    """
    从模型文件自动检测参数 - 完全复制 UVR pop_up_mdx_model() 逻辑
    
    .ckpt: 加载 hyper_parameters 获取 dim_f, dim_t, n_fft, target_name
    .onnx: 从 tensor shape 推断 dim_f, dim_t，n_fft 使用默认值 6144
    
    返回 True 表示成功检测，False 表示需要回退到默认值
    """
    is_ckpt = model_path.endswith('.ckpt')
    is_onnx = model_path.endswith('.onnx')
    
    if is_ckpt:
        # ===== .ckpt 模型: 与 pop_up_mdx_model() 第 4615-4626 行完全一致 =====
        try:
            checkpoint = torch.load(model_path, map_location=lambda storage, loc: storage)
            
            if 'hyper_parameters' not in checkpoint:
                # 没有 hyper_parameters，可能是 MDX-C 模型
                if verbose:
                    print("Detected .ckpt without hyper_parameters, may need YAML config")
                return False
            
            params = checkpoint['hyper_parameters']
            
            if verbose:
                print("Auto-detected parameters from checkpoint hyper_parameters")
            
            # 与 UVR 完全一致的参数提取
            model_data.mdx_dim_f_set = params.get('dim_f', 3072)
            
            # dim_t: UVR 使用 int(math.log(model_params['dim_t'], 2))
            dim_t_raw = params.get('dim_t', 256)
            model_data.mdx_dim_t_set = int(math.log(dim_t_raw, 2)) if dim_t_raw > 0 else 8
            
            model_data.mdx_n_fft_scale_set = params.get('n_fft', 6144)
            
            # 允许 CLI 参数覆盖 compensate
            model_data.compensate = kwargs.get('compensate', 1.035)
            
            # 与 UVR 第 4623-4625 行完全一致: 从 target_name 推断 primary_stem
            target_name = params.get('target_name', '').lower()
            primary_stem = VOCAL_STEM  # 默认值
            
            # STEM_SET_MENU 的检查（简化版，覆盖常见情况）
            stem_mapping = {
                'vocals': VOCAL_STEM,
                'instrumental': INST_STEM,
                'drums': DRUM_STEM,
                'bass': BASS_STEM,
                'other': INST_STEM,  # UVR: "INST_STEM if model_params['target_name'] == OTHER_STEM.lower() else stem"
            }
            
            for key, stem in stem_mapping.items():
                if key in target_name:
                    primary_stem = stem
                    break
            
            # 允许 CLI 参数覆盖 primary_stem
            model_data.primary_stem = kwargs.get('primary_stem', primary_stem)
            model_data.primary_stem_native = model_data.primary_stem
            model_data.secondary_stem = secondary_stem(model_data.primary_stem)
            
            if verbose:
                print(f"  dim_f={model_data.mdx_dim_f_set}, dim_t={2**model_data.mdx_dim_t_set}, "
                      f"n_fft={model_data.mdx_n_fft_scale_set}, primary_stem={model_data.primary_stem}")
            
            return True
            
        except Exception as e:
            if verbose:
                print(f"Warning: Cannot auto-detect from checkpoint: {e}")
            return False
    
    elif is_onnx:
        # ===== .onnx 模型: 与 pop_up_mdx_model() 第 4608-4613 行完全一致 =====
        try:
            import onnx
            model = onnx.load(model_path)
            
            # 与 UVR 完全一致: 从输入 tensor shape 获取 dim_f, dim_t
            model_shapes = [[d.dim_value for d in _input.type.tensor_type.shape.dim] 
                           for _input in model.graph.input][0]
            
            dim_f = model_shapes[2]
            dim_t = int(math.log(model_shapes[3], 2))
            n_fft = 6144  # UVR 对 ONNX 使用硬编码默认值 '6144'
            
            if verbose:
                print("Auto-detected parameters from ONNX tensor shape")
            
            model_data.mdx_dim_f_set = dim_f
            model_data.mdx_dim_t_set = dim_t
            model_data.mdx_n_fft_scale_set = kwargs.get('mdx_n_fft_scale_set', n_fft)
            model_data.compensate = kwargs.get('compensate', 1.035)
            
            # ONNX 无法从模型推断 primary_stem，使用 CLI 参数或默认值
            model_data.primary_stem = kwargs.get('primary_stem', VOCAL_STEM)
            model_data.primary_stem_native = model_data.primary_stem
            model_data.secondary_stem = secondary_stem(model_data.primary_stem)
            
            if verbose:
                print(f"  dim_f={dim_f}, dim_t={2**dim_t}, n_fft={n_fft}, primary_stem={model_data.primary_stem}")
            
            return True
            
        except ImportError:
            if verbose:
                print("Warning: onnx package not installed, cannot auto-detect ONNX model parameters")
            return False
        except Exception as e:
            if verbose:
                print(f"Warning: Cannot auto-detect from ONNX: {e}")
            return False
    
    return False


def _apply_config(model_data, config, kwargs, verbose=False, model_path=None):
    """应用配置到 model_data"""
    
    # 检查是否是 MDX-C / Roformer 模型
    if 'config_yaml' in config:
        model_data.is_mdx_c = True
        config_yaml = config['config_yaml']
        config_path = find_mdx_c_config_path(config_yaml, model_path)
        
        if config_path and os.path.isfile(config_path):
            with open(config_path, 'r') as f:
                # 使用 FullLoader 与 UVR.py 保持一致（支持 !!python/tuple 等标签）
                yaml_config = yaml.load(f, Loader=yaml.FullLoader)
                model_data.mdx_c_configs = ConfigDict(yaml_config)
            
            if verbose:
                print(f"Loaded MDX-C config: {config_yaml}")
            
            # 从 training 配置获取 stems
            training = model_data.mdx_c_configs.get('training', {})
            if training.get('target_instrument'):
                target = training['target_instrument']
                model_data.mdx_model_stems = [target]
                model_data.primary_stem = target
                model_data.is_target_instrument = True  # UVR.py line 553
            else:
                instruments = training.get('instruments', ['Vocals', 'Instrumental'])
                model_data.mdx_model_stems = instruments
                model_data.mdx_stem_count = len(instruments)
                model_data.primary_stem = instruments[0] if instruments else VOCAL_STEM
            
            model_data.primary_stem_native = model_data.primary_stem
            model_data.secondary_stem = secondary_stem(model_data.primary_stem)
            
            # 检查并设置是否是 Roformer 模型
            # 首先尝试从配置文件读取
            model_data.is_roformer = config.get('is_roformer', False)
            
            # 自动检测：如果 YAML 中有特定参数，则是 Roformer/SCNet 模型
            # 这与 separate.py 中的判断逻辑一致
            model_config = model_data.mdx_c_configs.get('model', {})
            if 'num_bands' in model_config or 'freqs_per_bands' in model_config:
                model_data.is_roformer = True
                if verbose and not config.get('is_roformer', False):
                    print("Auto-detected as Roformer model (based on YAML config)")
            elif 'band_SR' in model_config or 'sources' in model_config:
                # SCNet model detection
                model_data.is_roformer = True  # SCNet 也使用 is_roformer=True 的处理路径
                if verbose:
                    print("Auto-detected as SCNet model (based on YAML config)")
            
            if model_data.is_roformer:
                if verbose:
                    model_type = config.get('model_type', 'Roformer')
                    print(f"Model type: {model_type}")
        else:
            print(f"Warning: Config file not found: {config_yaml}")
            model_data.is_mdx_c = False
    else:
        # 标准 MDX-Net 模型
        model_data.mdx_dim_f_set = config.get('mdx_dim_f_set', 3072)
        model_data.mdx_dim_t_set = config.get('mdx_dim_t_set', 8)
        model_data.mdx_n_fft_scale_set = config.get('mdx_n_fft_scale_set', 6144)
        model_data.compensate = config.get('compensate', kwargs.get('compensate', 1.035))
        model_data.primary_stem = config.get('primary_stem', VOCAL_STEM)
        model_data.primary_stem_native = model_data.primary_stem
        model_data.secondary_stem = secondary_stem(model_data.primary_stem)
        model_data.is_karaoke = config.get('is_karaoke', False)


def create_process_data(audio_file, export_path, audio_file_base=None, **kwargs):
    """创建 process_data 字典"""
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    verbose = kwargs.get('verbose', False)
    
    def noop_progress(step=0, inference_iterations=0):
        pass
    
    def write_console(progress_text='', base_text=''):
        if verbose:
            msg = f"{base_text}{progress_text}".strip()
            if msg:
                print(msg)
    
    def noop_iteration():
        pass
    
    def noop_cache_callback(process_method, model_name=None):
        return (None, None)
    
    def noop_cache_holder(process_method, sources, model_name):
        pass
    
    return {
        'model_data': None,
        'export_path': export_path,
        'audio_file_base': audio_file_base,
        'audio_file': audio_file,
        'set_progress_bar': noop_progress,
        'write_to_console': write_console,
        'process_iteration': noop_iteration,
        'cached_source_callback': noop_cache_callback,
        'cached_model_source_holder': noop_cache_holder,
        'list_all_models': [],
        'is_ensemble_master': False,
        'is_4_stem_ensemble': False
    }


def run_mdx_headless(
    model_path,
    audio_file,
    export_path,
    audio_file_base=None,
    use_gpu=None,
    device_set='0',
    is_use_directml=False,
    mdx_segment_size=256,
    overlap_mdx=0.25,
    overlap_mdx23=2,
    mdx_batch_size=1,
    wav_type_set='PCM_24',
    model_json_path=None,
    primary_only=False,
    secondary_only=False,
    dry_only=False,
    no_dry_only=False,
    vocals_only=False,
    instrumental_only=False,
    stem=None,
    verbose=True,
    **kwargs
):
    """
    Headless MDX-Net 运行器主函数
    
    直接使用 UVR 原有的 SeperateMDX 和 SeperateMDXC 类
    """
    # 验证输入
    if not os.path.isfile(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    if not os.path.isfile(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    if not os.path.isdir(export_path):
        os.makedirs(export_path, exist_ok=True)
    
    # 处理 stem 参数
    mdxnet_stem_select = ALL_STEMS
    if stem:
        stem_map = {
            'all': ALL_STEMS,
            'vocals': VOCAL_STEM,
            'drums': DRUM_STEM,
            'bass': BASS_STEM,
            'other': OTHER_STEM
        }
        stem_lower = stem.lower()
        if stem_lower not in stem_map:
            raise ValueError(f"Invalid stem: {stem}")
        mdxnet_stem_select = stem_map[stem_lower]
    
    # 创建 ModelData
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
    
    model_data = create_model_data(
        model_path,
        use_gpu=use_gpu if use_gpu is not None else cuda_available,
        device_set=device_set,
        is_use_directml=is_use_directml,
        mdx_segment_size=mdx_segment_size,
        overlap_mdx=overlap_mdx,
        overlap_mdx23=overlap_mdx23,
        mdx_batch_size=mdx_batch_size,
        wav_type_set=wav_type,
        model_json_path=model_json_path,
        primary_only=primary_only,
        secondary_only=secondary_only,
        dry_only=dry_only,
        no_dry_only=no_dry_only,
        vocals_only=vocals_only,
        instrumental_only=instrumental_only,
        mdxnet_stem_select=mdxnet_stem_select,
        verbose=verbose,
        **kwargs
    )
    
    # 创建 process_data
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    process_data = create_process_data(
        audio_file,
        export_path,
        audio_file_base,
        verbose=verbose
    )
    process_data['model_data'] = model_data
    
    # 打印信息
    if verbose:
        print(f"=" * 50)
        print(f"MDX-Net Headless Runner")
        print(f"=" * 50)
        print(f"Model: {model_path}")
        print(f"Input: {audio_file}")
        print(f"Output: {export_path}")
        print(f"Device: {'GPU' if model_data.is_gpu_conversion >= 0 else 'CPU'}")
        print(f"Model Type: {'MDX-C/Roformer' if model_data.is_mdx_c else 'MDX-Net'}")
        print(f"Output Format: {model_data.wav_type_set}")
        print(f"Primary Stem: {model_data.primary_stem}")
        print(f"Secondary Stem: {model_data.secondary_stem}")
        if not model_data.is_mdx_c:
            print(f"Params: dim_f={model_data.mdx_dim_f_set}, dim_t={2**model_data.mdx_dim_t_set}, n_fft={model_data.mdx_n_fft_scale_set}")
        print(f"=" * 50)
    
    # 运行分离 - 使用 UVR 原有的类
    if model_data.is_mdx_c:
        separator = SeperateMDXC(model_data, process_data)
    else:
        separator = SeperateMDX(model_data, process_data)
    
    separator.seperate()
    
    if verbose:
        print(f"\nProcessing complete!")
        print(f"Output: {export_path}")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='MDX-Net Headless Runner - Audio source separation using UVR codebase',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python mdx_headless_runner.py -m model.ckpt -i input.wav -o output/
  
  # Use JSON config (for non-standard models like MelBand-Roformer)
  python mdx_headless_runner.py -m model.ckpt --json config.json -i input.wav -o output/
  
  # Output vocals only
  python mdx_headless_runner.py -m model.ckpt -i input.wav -o output/ --vocals-only
  
  # Use GPU
  python mdx_headless_runner.py -m model.ckpt -i input.wav -o output/ --gpu
"""
    )
    
    parser.add_argument('--model', '-m', required=True, help='Model file path (.ckpt)')
    parser.add_argument('--input', '-i', required=True, help='Input audio file path')
    parser.add_argument('--output', '-o', required=True, help='Output directory path')
    parser.add_argument('--name', '-n', help='Output filename base (optional)')
    parser.add_argument('--json', help='Model JSON config file path (required for non-standard models)')
    parser.add_argument('--gpu', action='store_true', help='Use GPU')
    parser.add_argument('--cpu', action='store_true', help='Force CPU')
    parser.add_argument('--directml', action='store_true', help='Use DirectML (AMD GPU)')
    parser.add_argument('--device', '-d', default='0', help='GPU device ID (default: 0)')
    parser.add_argument('--segment-size', type=int, default=256, help='Segment size (default: 256)')
    parser.add_argument('--overlap', type=float, default=0.25, help='MDX overlap (default: 0.25, range 0.25-0.99)')
    parser.add_argument('--overlap-mdxc', type=int, default=2, help='MDX-C/Roformer overlap (default: 2, range 2-50)')
    parser.add_argument('--batch-size', type=int, default=1, help='Batch size (default: 1)')
    parser.add_argument('--wav-type', default='PCM_24', 
                        choices=['PCM_U8', 'PCM_16', 'PCM_24', 'PCM_32', 'FLOAT', 'DOUBLE'],
                        help='Output audio bit depth (default: PCM_24)')
    
    # Output control
    output_group = parser.add_argument_group('Output Control')
    output_group.add_argument('--primary-only', action='store_true', help='Save primary stem only')
    output_group.add_argument('--secondary-only', action='store_true', help='Save secondary stem only')
    output_group.add_argument('--dry-only', action='store_true', help='Save Dry only (= --primary-only)')
    output_group.add_argument('--no-dry-only', action='store_true', help='Save No Dry only (= --secondary-only)')
    output_group.add_argument('--vocals-only', action='store_true', help='Save vocals only (= --primary-only)')
    output_group.add_argument('--instrumental-only', action='store_true', help='Save instrumental only (= --secondary-only)')
    
    parser.add_argument('--stem', choices=['all', 'vocals', 'drums', 'bass', 'other'],
                       help='Select stem to extract (MDX-C models only)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode')
    
    args = parser.parse_args()
    
    # 互斥检查
    primary_flags = [args.primary_only, args.dry_only, args.vocals_only]
    secondary_flags = [args.secondary_only, args.no_dry_only, args.instrumental_only]
    
    if any(primary_flags) and any(secondary_flags):
        parser.error("不能同时指定 primary-only 和 secondary-only 相关的参数")
    
    # GPU 设置
    use_gpu = None
    if args.cpu:
        use_gpu = False
    elif args.gpu:
        use_gpu = True
    
    try:
        run_mdx_headless(
            model_path=args.model,
            audio_file=args.input,
            export_path=args.output,
            audio_file_base=args.name,
            use_gpu=use_gpu,
            device_set=args.device,
            is_use_directml=args.directml,
            mdx_segment_size=args.segment_size,
            overlap_mdx=args.overlap,
            overlap_mdx23=args.overlap_mdxc,
            mdx_batch_size=args.batch_size,
            wav_type_set=args.wav_type,
            model_json_path=args.json,
            primary_only=args.primary_only,
            secondary_only=args.secondary_only,
            dry_only=args.dry_only,
            no_dry_only=args.no_dry_only,
            vocals_only=args.vocals_only,
            instrumental_only=args.instrumental_only,
            stem=args.stem,
            verbose=not args.quiet
        )
        
        return 0
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        if not args.quiet:
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
