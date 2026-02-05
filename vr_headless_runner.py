#!/usr/bin/env python3
"""
VR Architecture Headless Runner
严格复制 UVR GUI 的 VR Architecture 行为

Usage:
    python vr_headless_runner.py --model model.pth --input input.wav --output output/

================================================================================
IMPORTANT: FORENSIC REVERSE-ENGINEERING MODE
================================================================================
This code MUST be behavior-identical to UVR GUI.
Do NOT:
  - Invent logic
  - Optimize
  - Refactor  
  - Simplify
  - "Improve" architecture
  
ONLY reproduce what UVR actually does.
If UVR code does something ugly, redundant, or unintuitive — we do the same.
================================================================================
"""

# Suppress deprecation warnings from librosa's pkg_resources usage
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="librosa")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")

import os
import sys
import json
import math
import hashlib
import time
import torch
import argparse
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
from separate import SeperateVR, prepare_mix
from lib_v5.vr_network.model_param_init import ModelParameters
from model_downloader import ModelDownloader
from gui_data.constants import (
    VR_ARCH_TYPE,
    VOCAL_STEM,
    INST_STEM,
    DEFAULT,
    CUDA_DEVICE,
    CPU,
    secondary_stem,
    NON_ACCOM_STEMS,
    NO_STEM,
    WOOD_INST_MODEL_HASH,
    WOOD_INST_PARAMS,
    IS_KARAOKEE,
    IS_BV_MODEL,
    IS_BV_MODEL_REBAL,
    CHOOSE_MODEL,
    NO_MODEL,
    DEF_OPT
)

# 设备检测（与 UVR 完全一致）
mps_available = torch.backends.mps.is_available() if hasattr(torch.backends, 'mps') else False
cuda_available = torch.cuda.is_available()
cpu = torch.device('cpu')

# ============================================================================
# 默认路径 - 与 UVR.py 完全一致
# ============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, 'models')
VR_MODELS_DIR = os.path.join(MODELS_DIR, 'VR_Models')
VR_HASH_DIR = os.path.join(VR_MODELS_DIR, 'model_data')
VR_HASH_JSON = os.path.join(VR_MODELS_DIR, 'model_data', 'model_data.json')
VR_PARAM_DIR = os.path.join(SCRIPT_DIR, 'lib_v5', 'vr_network', 'modelparams')

# ============================================================================
# 全局哈希缓存 - 与 UVR.py line 315 完全一致
# ============================================================================
model_hash_table = {}


# ============================================================================
# 模型下载和注册表功能
# ============================================================================

def get_model_downloader(verbose: bool = True) -> ModelDownloader:
    """获取模型下载器实例"""
    downloader = ModelDownloader(base_path=SCRIPT_DIR, verbose=verbose)
    downloader.sync_registry()
    return downloader


def list_models(show_installed_only: bool = False, show_uninstalled_only: bool = False, verbose: bool = True) -> list:
    """
    列出所有可用的 VR 模型
    
    Args:
        show_installed_only: 仅显示已安装的模型
        show_uninstalled_only: 仅显示未安装的模型
        verbose: 是否显示详细信息
        
    Returns:
        模型列表
    """
    downloader = get_model_downloader(verbose=verbose)
    models = downloader.list_models('vr', show_installed=True)
    
    if show_installed_only:
        models = [m for m in models if m['installed']]
    elif show_uninstalled_only:
        models = [m for m in models if not m['installed']]
    
    return models


def get_model_info(model_name: str, verbose: bool = True) -> dict:
    """
    获取指定模型的详细信息
    
    Args:
        model_name: 模型名称
        verbose: 是否显示详细信息
        
    Returns:
        模型信息字典
    """
    downloader = get_model_downloader(verbose=verbose)
    return downloader.get_model_info(model_name, 'vr')


def download_model(model_name: str, verbose: bool = True) -> tuple:
    """
    下载指定的 VR 模型
    
    Args:
        model_name: 模型名称
        verbose: 是否显示详细信息
        
    Returns:
        (成功与否, 消息)
    """
    downloader = get_model_downloader(verbose=verbose)
    return downloader.download_model(model_name, 'vr')


def resolve_model_path(model_identifier: str, verbose: bool = True, progress_callback=None) -> str:
    """
    解析模型标识符并返回本地模型路径
    
    如果模型标识符是一个存在的文件路径，直接返回。
    如果模型标识符是模型名称且本地不存在，尝试从远程下载。
    
    Args:
        model_identifier: 模型路径或模型名称
        verbose: 是否显示详细信息
        progress_callback: 可选的下载进度回调函数 (current, total, filename)
        
    Returns:
        模型文件的本地路径
        
    Raises:
        FileNotFoundError: 如果模型无法找到或下载失败
    """
    # 1. 如果是完整路径且文件存在
    if os.path.isfile(model_identifier):
        if verbose:
            print(f"使用本地模型文件: {model_identifier}")
        return model_identifier
    
    # 2. 尝试在 VR_MODELS_DIR 中查找
    if not model_identifier.endswith('.pth'):
        model_filename = f"{model_identifier}.pth"
    else:
        model_filename = model_identifier
    
    local_path = os.path.join(VR_MODELS_DIR, model_filename)
    if os.path.isfile(local_path):
        if verbose:
            print(f"找到本地模型: {local_path}")
        return local_path
    
    # 3. 尝试通过模型名称在远程注册表中查找
    downloader = get_model_downloader(verbose=verbose)
    
    # 移除 .pth 后缀进行搜索
    model_name = model_identifier.replace('.pth', '')
    model_info = downloader.get_model_info(model_name, 'vr')
    
    if model_info:
        if model_info.get('installed'):
            # 模型已安装，返回本地路径
            if model_info.get('is_multi_file'):
                # VR 通常是单文件，但处理多文件情况
                for f in model_info['files'].keys():
                    path = os.path.join(VR_MODELS_DIR, f)
                    if os.path.isfile(path):
                        return path
            else:
                return model_info['local_path']
        else:
            # 模型未安装，下载
            if verbose:
                print(f"模型 '{model_name}' 未安装，正在下载...")
            
            success, result = downloader.ensure_model(model_name, 'vr', progress_callback=progress_callback)
            if success:
                if verbose:
                    print(f"下载完成: {result}")
                return result
            else:
                raise FileNotFoundError(f"下载模型失败: {result}")
    
    # 4. 没有找到匹配的模型
    raise FileNotFoundError(
        f"无法找到模型: {model_identifier}\n"
        f"搜索路径:\n"
        f"  - {model_identifier} (完整路径)\n"
        f"  - {local_path} (VR模型目录)\n"
        f"  - 远程模型注册表 (名称: {model_name})\n"
        f"\n提示: 使用 --list 查看所有可用模型"
    )


# ============================================================================
# IMPORTANT: 以下函数严格复制 UVR.py 的行为
# ============================================================================

def load_model_hash_data(dictionary):
    """
    加载模型哈希字典
    
    与 UVR.py line 194-197 完全一致
    """
    with open(dictionary, 'r') as d:
        return json.load(d)


def get_model_hash(model_path):
    """
    计算模型文件的 MD5 哈希
    
    与 UVR.py ModelData.get_model_hash() line 779-803 完全一致：
    1. 先检查 model_hash_table 缓存
    2. 如果没有，计算哈希（读取最后 10MB）
    3. 缓存结果
    """
    global model_hash_table
    model_hash = None
    
    if not os.path.isfile(model_path):
        return None
    
    # 步骤 1: 检查缓存（UVR.py line 786-790）
    if model_hash_table:
        for (key, value) in model_hash_table.items():
            if model_path == key:
                model_hash = value
                break
    
    # 步骤 2: 如果没有缓存，计算哈希（UVR.py line 792-801）
    if not model_hash:
        try:
            with open(model_path, 'rb') as f:
                # 与 UVR.py 完全一致：读取最后 10MB
                try:
                    f.seek(-10000 * 1024, 2)  # 从文件末尾向前 10MB
                    model_hash = hashlib.md5(f.read()).hexdigest()
                except OSError:
                    # 文件小于 10MB，读取整个文件
                    f.seek(0)
                    model_hash = hashlib.md5(f.read()).hexdigest()
            
            # 步骤 3: 缓存结果（UVR.py line 800-801）
            table_entry = {model_path: model_hash}
            model_hash_table.update(table_entry)
        except Exception as e:
            pass
    
    return model_hash


def get_model_data(model_hash, model_hash_dir, hash_mapper):
    """
    根据模型哈希获取模型配置
    
    与 UVR.py ModelData.get_model_data() line 740-751 完全一致的回退链：
    1. 检查 {hash}.json 单独文件
    2. 检查 hash_mapper 中的哈希映射
    3. 返回 get_model_data_from_popup() 的结果（headless 模式返回 None）
    """
    # 步骤 1: 检查 {hash}.json 单独文件（UVR.py line 741-745）
    model_settings_json = os.path.join(model_hash_dir, f"{model_hash}.json")
    
    if os.path.isfile(model_settings_json):
        with open(model_settings_json, 'r') as json_file:
            return json.load(json_file)
    else:
        # 步骤 2: 检查 hash_mapper（UVR.py line 746-749）
        for hash_key, settings in hash_mapper.items():
            if model_hash in hash_key:
                return settings
        
        # 步骤 3: headless 模式下没有弹窗，返回 None（UVR.py line 751 会调用 popup）
        return None


def check_if_karaokee_model(model_data_obj, model_data_dict):
    """
    检查是否为卡拉OK模型
    
    与 UVR.py ModelData.check_if_karaokee_model() line 685-691 完全一致
    使用常量而非字符串字面量
    """
    if IS_KARAOKEE in model_data_dict.keys():
        model_data_obj.is_karaoke = model_data_dict[IS_KARAOKEE]
    if IS_BV_MODEL in model_data_dict.keys():
        model_data_obj.is_bv_model = model_data_dict[IS_BV_MODEL]
    if IS_BV_MODEL_REBAL in model_data_dict.keys() and model_data_obj.is_bv_model:
        model_data_obj.bv_model_rebalance = model_data_dict[IS_BV_MODEL_REBAL]


# ============================================================================
# ModelData 创建 - 严格复制 UVR.py ModelData.__init__() 中 VR_ARCH_TYPE 分支
# ============================================================================

def create_vr_model_data(model_name, vr_hash_MAPPER, **kwargs):
    """
    创建完全兼容 UVR 的 VR ModelData 对象
    
    严格按照 UVR.py ModelData.__init__() line 490-523 实现
    
    注意：此函数的签名模拟 UVR 的行为：
    - model_name: 模型名称（不含扩展名）
    - vr_hash_MAPPER: 从 model_data.json 加载的哈希映射
    
    Args:
        model_name: 模型名称（不含路径和扩展名）
        vr_hash_MAPPER: 哈希映射字典
        **kwargs: 可选参数覆盖（模拟 GUI 变量）
        
    Returns:
        SimpleNamespace: 包含所有必需属性的对象
    """
    model_data = SimpleNamespace()
    
    # ========== UVR.py line 420-422 ==========
    model_data.model_name = model_name
    model_data.process_method = VR_ARCH_TYPE
    model_data.model_status = False if model_name == CHOOSE_MODEL or model_name == NO_MODEL else True
    
    # ========== UVR.py line 423-424 ==========
    model_data.primary_stem = None
    model_data.secondary_stem = None
    
    # ========== 初始化默认值（UVR.py line 425-464）==========
    model_data.is_ensemble_mode = False
    model_data.ensemble_primary_stem = None
    model_data.ensemble_secondary_stem = None
    model_data.is_secondary_model = kwargs.get('is_secondary_model', False)
    model_data.is_pre_proc_model = kwargs.get('is_pre_proc_model', False)
    model_data.is_karaoke = False
    model_data.is_bv_model = False
    model_data.bv_model_rebalance = 0
    model_data.is_sec_bv_rebalance = False
    model_data.model_hash_dir = None
    model_data.is_secondary_model_activated = False
    model_data.is_multi_stem_ensemble = False
    model_data.is_4_stem_ensemble = False
    model_data.is_vr_51_model = False
    
    # ========== VR 特定参数（UVR.py line 491-500）==========
    # 这些模拟 root.xxx_var.get() 的值
    model_data.is_secondary_model_activated = False  # headless 不支持二级模型
    model_data.aggression_setting = float(int(kwargs.get('aggression_setting', 5)) / 100)  # UVR: int(root.aggression_setting_var.get())/100
    model_data.is_tta = kwargs.get('is_tta', False)
    model_data.is_post_process = kwargs.get('is_post_process', False)
    model_data.window_size = int(kwargs.get('window_size', 512))  # VR_WINDOW[1] = '512'
    model_data.batch_size = 1 if kwargs.get('batch_size', DEF_OPT) == DEF_OPT else int(kwargs.get('batch_size', 1))  # UVR.py line 496
    model_data.crop_size = int(kwargs.get('crop_size', 256))
    model_data.is_high_end_process = 'mirroring' if kwargs.get('is_high_end_process', False) else 'None'
    model_data.post_process_threshold = float(kwargs.get('post_process_threshold', 0.2))
    model_data.model_capacity = 32, 128  # UVR.py line 500 默认值
    
    # ========== 构建模型路径（UVR.py line 501）==========
    model_data.model_path = os.path.join(VR_MODELS_DIR, f"{model_name}.pth")
    
    # ========== 设备设置（从 kwargs 获取，模拟 GUI）==========
    use_gpu = kwargs.get('use_gpu', cuda_available)
    model_data.is_gpu_conversion = 0 if use_gpu else -1
    model_data.device_set = kwargs.get('device_set', DEFAULT)
    model_data.is_use_directml = kwargs.get('is_use_directml', False)
    
    # ========== 输出设置 ==========
    model_data.wav_type_set = kwargs.get('wav_type_set', 'PCM_16')
    model_data.save_format = kwargs.get('save_format', 'WAV')
    model_data.mp3_bit_set = kwargs.get('mp3_bit_set', '320k')
    model_data.is_normalization = kwargs.get('is_normalization', False)
    
    # ========== 输出控制（UVR.py line 387-388）==========
    model_data.is_primary_stem_only = kwargs.get('is_primary_stem_only', False)
    model_data.is_secondary_stem_only = kwargs.get('is_secondary_stem_only', False)
    model_data.is_primary_model_primary_stem_only = False
    model_data.is_primary_model_secondary_stem_only = False
    
    # ========== 二级模型（headless 不支持）==========
    model_data.secondary_model = None
    model_data.secondary_model_scale = None
    model_data.primary_model_primary_stem = None
    
    # ========== Vocal Split（headless 不支持）==========
    model_data.vocal_split_model = None
    model_data.is_vocal_split_model = kwargs.get('is_vocal_split_model', False)
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
    
    # ========== 其他标志 ==========
    model_data.mixer_path = None
    model_data.model_samplerate = 44100  # 默认值，会被 vr_model_param 覆盖
    model_data.is_invert_spec = kwargs.get('is_invert_spec', False)
    model_data.is_mixer_mode = False
    model_data.is_demucs_pre_proc_model_inst_mix = False
    model_data.overlap = 0.25
    model_data.overlap_mdx = 0.25
    model_data.overlap_mdx23 = 8
    
    # ========== MDX 相关（VR 不使用，但 SeperateAttributes 需要）==========
    model_data.is_mdx_combine_stems = False
    model_data.is_mdx_c = False
    model_data.mdx_c_configs = None
    model_data.mdxnet_stem_select = None
    model_data.is_target_instrument = False
    model_data.is_roformer = False
    
    # ========== 获取模型哈希（UVR.py line 502）==========
    model_data.model_hash = get_model_hash(model_data.model_path)
    
    # ========== 如果文件不存在，model_status = False（UVR.py line 782-784）==========
    if not os.path.isfile(model_data.model_path):
        model_data.model_status = False
    
    # ========== UVR.py line 503-523: 哈希查找和配置加载 ==========
    if model_data.model_hash:
        # UVR.py line 504: 无条件打印哈希
        print(model_data.model_hash)
        
        # UVR.py line 505: 设置 model_hash_dir
        model_data.model_hash_dir = os.path.join(VR_HASH_DIR, f"{model_data.model_hash}.json")
        
        # UVR.py line 509: 获取模型配置（WOOD_INST_MODEL_HASH 特殊处理）
        if model_data.model_hash == WOOD_INST_MODEL_HASH:
            model_data.model_data = WOOD_INST_PARAMS
        else:
            model_data.model_data = get_model_data(model_data.model_hash, VR_HASH_DIR, vr_hash_MAPPER)
        
        # UVR.py line 510-520: 如果找到配置，加载参数
        if model_data.model_data:
            # UVR.py line 511
            vr_model_param = os.path.join(VR_PARAM_DIR, "{}.json".format(model_data.model_data["vr_model_param"]))
            # UVR.py line 512
            model_data.primary_stem = model_data.model_data["primary_stem"]
            # UVR.py line 513
            model_data.secondary_stem = secondary_stem(model_data.primary_stem)
            # UVR.py line 514
            model_data.vr_model_param = ModelParameters(vr_model_param)
            # UVR.py line 515
            model_data.model_samplerate = model_data.vr_model_param.param['sr']
            # UVR.py line 516
            model_data.primary_stem_native = model_data.primary_stem
            # UVR.py line 517-519
            if "nout" in model_data.model_data.keys() and "nout_lstm" in model_data.model_data.keys():
                model_data.model_capacity = model_data.model_data["nout"], model_data.model_data["nout_lstm"]
                model_data.is_vr_51_model = True
            # UVR.py line 520
            check_if_karaokee_model(model_data, model_data.model_data)
        else:
            # UVR.py line 522-523: 配置未找到
            model_data.model_status = False
    else:
        # 哈希为 None（文件不存在或无法读取）
        model_data.model_status = False
    
    # ========== 设置 model_basename（UVR.py line 616）==========
    if model_data.model_status:
        model_data.model_basename = os.path.splitext(os.path.basename(model_data.model_path))[0]
    else:
        model_data.model_basename = model_name
    
    return model_data


def create_vr_model_data_with_user_params(model_path, vr_hash_MAPPER, user_params, **kwargs):
    """
    创建 VR ModelData，当哈希查找失败时使用用户提供的参数
    
    这模拟 UVR 的 get_model_data_from_popup() 行为，但用 CLI 参数替代弹窗
    
    Args:
        model_path: 完整模型路径
        vr_hash_MAPPER: 哈希映射字典
        user_params: 用户通过 CLI 提供的参数 {'vr_model_param': ..., 'primary_stem': ..., 'nout': ..., 'nout_lstm': ...}
        **kwargs: 其他参数
    """
    model_name = os.path.splitext(os.path.basename(model_path))[0]
    
    # 先尝试正常流程
    model_data = create_vr_model_data(model_name, vr_hash_MAPPER, **kwargs)
    
    # 如果模型路径不是默认路径，更新它
    if model_path != model_data.model_path:
        model_data.model_path = model_path
        model_data.model_hash = get_model_hash(model_path)
        
        if model_data.model_hash:
            print(model_data.model_hash)  # UVR.py line 504: 无条件打印
            model_data.model_hash_dir = os.path.join(VR_HASH_DIR, f"{model_data.model_hash}.json")
            
            if model_data.model_hash == WOOD_INST_MODEL_HASH:
                model_data.model_data = WOOD_INST_PARAMS
            else:
                model_data.model_data = get_model_data(model_data.model_hash, VR_HASH_DIR, vr_hash_MAPPER)
            
            if model_data.model_data:
                vr_model_param = os.path.join(VR_PARAM_DIR, "{}.json".format(model_data.model_data["vr_model_param"]))
                model_data.primary_stem = model_data.model_data["primary_stem"]
                model_data.secondary_stem = secondary_stem(model_data.primary_stem)
                model_data.vr_model_param = ModelParameters(vr_model_param)
                model_data.model_samplerate = model_data.vr_model_param.param['sr']
                model_data.primary_stem_native = model_data.primary_stem
                if "nout" in model_data.model_data.keys() and "nout_lstm" in model_data.model_data.keys():
                    model_data.model_capacity = model_data.model_data["nout"], model_data.model_data["nout_lstm"]
                    model_data.is_vr_51_model = True
                check_if_karaokee_model(model_data, model_data.model_data)
                model_data.model_status = True
            else:
                model_data.model_status = False
        else:
            model_data.model_status = False
    
    # 如果 model_status 为 False 且用户提供了参数，使用用户参数
    # 这模拟 UVR 的 get_model_data_from_popup() 返回用户输入
    if not model_data.model_status and user_params:
        user_vr_model_param = user_params.get('vr_model_param')
        user_primary_stem = user_params.get('primary_stem')
        
        if user_vr_model_param and user_primary_stem:
            vr_model_param_path = os.path.join(VR_PARAM_DIR, f"{user_vr_model_param}.json")
            
            if os.path.isfile(vr_model_param_path):
                # 模拟弹窗返回的数据结构
                model_data.model_data = {
                    "vr_model_param": user_vr_model_param,
                    "primary_stem": user_primary_stem
                }
                
                model_data.vr_model_param = ModelParameters(vr_model_param_path)
                model_data.primary_stem = user_primary_stem
                model_data.secondary_stem = secondary_stem(user_primary_stem)
                model_data.model_samplerate = model_data.vr_model_param.param['sr']
                model_data.primary_stem_native = user_primary_stem
                
                # 用户提供的 nout/nout_lstm
                user_nout = user_params.get('nout')
                user_nout_lstm = user_params.get('nout_lstm')
                if user_nout is not None and user_nout_lstm is not None:
                    model_data.model_capacity = (user_nout, user_nout_lstm)
                    model_data.is_vr_51_model = True
                
                model_data.model_status = True
                model_data.model_basename = os.path.splitext(os.path.basename(model_path))[0]
    
    return model_data


def create_process_data(audio_file, export_path, audio_file_base=None, 
                        progress_manager: ProgressManager = None, **kwargs):
    """
    创建 process_data 字典
    
    与 UVR 的 process_data 结构完全一致
    
    Args:
        audio_file: 输入音频文件路径
        export_path: 输出目录路径
        audio_file_base: 输出文件基名
        progress_manager: 进度管理器实例（可选）
        **kwargs: 其他参数
    """
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    verbose = kwargs.get('verbose', True)
    
    # 如果提供了 progress_manager，使用它创建回调
    if progress_manager is not None:
        callbacks = create_progress_callbacks(progress_manager, total_iterations=100)
        set_progress_bar = callbacks['set_progress_bar']
        write_to_console = callbacks['write_to_console']
        process_iteration = callbacks['process_iteration']
    else:
        def set_progress_bar(step=0, inference_iterations=0):
            pass
        
        def write_to_console(progress_text='', base_text=''):
            if verbose:
                msg = f"{base_text}{progress_text}".strip()
                if msg:
                    print(msg)
        
        def process_iteration():
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
        'set_progress_bar': set_progress_bar,
        'write_to_console': write_to_console,
        'process_iteration': process_iteration,
        'cached_source_callback': noop_cache_callback,
        'cached_model_source_holder': noop_cache_holder,
        'list_all_models': [],
        'is_ensemble_master': False,
        'is_4_stem_ensemble': False
    }


def run_vr_headless(
    model_path,
    audio_file,
    export_path,
    audio_file_base=None,
    use_gpu=None,
    device_set=DEFAULT,
    is_use_directml=False,
    window_size=512,
    aggression_setting=5,
    batch_size=DEF_OPT,
    is_tta=False,
    is_post_process=False,
    post_process_threshold=0.2,
    is_high_end_process=False,
    wav_type_set='PCM_16',
    user_vr_model_param=None,
    user_primary_stem=None,
    user_nout=None,
    user_nout_lstm=None,
    is_primary_stem_only=False,
    is_secondary_stem_only=False,
    verbose=True,
    progress_manager: ProgressManager = None,
    **kwargs
):
    """
    Headless VR Architecture 运行器主函数
    
    直接使用 UVR 原有的 SeperateVR 类，行为与 GUI 完全一致
    
    Args:
        model_path: 模型文件路径
        audio_file: 输入音频文件路径
        export_path: 输出目录路径
        progress_manager: 进度管理器实例（可选）
        ...
    """
    start_time = time.time()
    
    # 如果没有提供 progress_manager，创建一个默认的
    pm = progress_manager or ProgressManager(verbose=verbose)
    pm.set_file_name(os.path.basename(audio_file))
    pm.set_model_name(os.path.basename(model_path))
    
    # 验证输入文件
    if not os.path.isfile(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    if not os.path.isdir(export_path):
        os.makedirs(export_path, exist_ok=True)
    
    # 加载哈希映射（与 UVR.py line 1712 一致）
    pm.start_stage(ProgressStage.INITIALIZING, "Loading model database")
    if os.path.isfile(VR_HASH_JSON):
        vr_hash_MAPPER = load_model_hash_data(VR_HASH_JSON)
    else:
        vr_hash_MAPPER = {}
    pm.finish_stage("Model database loaded")
    
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
    wav_type = wav_type_map.get(wav_type_set, 'PCM_16')
    
    # 用户参数（模拟弹窗输入）
    user_params = {
        'vr_model_param': user_vr_model_param,
        'primary_stem': user_primary_stem,
        'nout': user_nout,
        'nout_lstm': user_nout_lstm
    } if user_vr_model_param or user_primary_stem else None
    
    # 创建 ModelData（严格按照 UVR 流程）
    pm.start_stage(ProgressStage.LOADING_MODEL, "Loading VR model configuration")
    model_data = create_vr_model_data_with_user_params(
        model_path,
        vr_hash_MAPPER,
        user_params,
        use_gpu=use_gpu if use_gpu is not None else cuda_available,
        device_set=device_set,
        is_use_directml=is_use_directml,
        window_size=window_size,
        aggression_setting=aggression_setting,
        batch_size=batch_size,
        is_tta=is_tta,
        is_post_process=is_post_process,
        post_process_threshold=post_process_threshold,
        is_high_end_process=is_high_end_process,
        wav_type_set=wav_type,
        is_primary_stem_only=is_primary_stem_only,
        is_secondary_stem_only=is_secondary_stem_only,
        **kwargs
    )
    pm.finish_stage("Model configuration loaded")
    
    # 检查 model_status（与 UVR 行为一致）
    if not model_data.model_status:
        pm.write_message(f"Error: Model status is False for {model_path}", "red")
        pm.write_message(f"Model hash: {model_data.model_hash}", "yellow")
        if not hasattr(model_data, 'vr_model_param') or model_data.vr_model_param is None:
            pm.write_message("Model hash not found in database. Please provide --param and --primary-stem arguments.", "yellow")
            pm.write_message("Example: --param 4band_v3 --primary-stem Vocals", "cyan")
            if os.path.isdir(VR_PARAM_DIR):
                params = [os.path.splitext(f)[0] for f in os.listdir(VR_PARAM_DIR) if f.endswith('.json')]
                pm.write_message(f"Available params: {', '.join(sorted(params))}")
        return False
    
    # 创建 process_data
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    process_data = create_process_data(
        audio_file,
        export_path,
        audio_file_base,
        progress_manager=pm,
        verbose=verbose
    )
    process_data['model_data'] = model_data
    
    # 打印 header 信息
    device_str = 'CPU'
    if model_data.is_gpu_conversion >= 0:
        if is_use_directml:
            device_str = f"DirectML:{device_set}"
        elif cuda_available:
            device_str = f"CUDA:{device_set}"
    
    # Build output stems string for header
    output_stems = None
    if model_data.primary_stem and model_data.secondary_stem:
        if model_data.is_primary_stem_only:
            output_stems = model_data.primary_stem
        elif model_data.is_secondary_stem_only:
            output_stems = model_data.secondary_stem
        else:
            output_stems = f"{model_data.primary_stem}, {model_data.secondary_stem}"
    
    pm.print_header(
        model_name=os.path.basename(model_path),
        input_file=audio_file,
        output_path=export_path,
        device=device_str,
        arch_type=f"VR Architecture {'(5.1)' if model_data.is_vr_51_model else ''}",
        output_stems=output_stems
    )
    
    # 运行分离 - 使用 UVR 原有的类
    pm.start_stage(ProgressStage.INFERENCE, "Running VR separation", total=100)
    
    separator = SeperateVR(model_data, process_data)
    separator.seperate()
    
    pm.finish_stage("Audio separation complete")
    
    # 记录输出文件
    for stem_name in [model_data.primary_stem, model_data.secondary_stem]:
        if stem_name:
            output_file = os.path.join(export_path, f"{audio_file_base}_({stem_name}).wav")
            if os.path.isfile(output_file):
                pm.add_output_file(output_file)
    
    elapsed = time.time() - start_time
    if verbose:
        pm.write_message(f"\n✓ Total processing time: {elapsed:.1f}s", "green")
    
    return True


def list_available_params():
    """列出所有可用的模型参数文件"""
    if os.path.isdir(VR_PARAM_DIR):
        params = [os.path.splitext(f)[0] for f in os.listdir(VR_PARAM_DIR) if f.endswith('.json')]
        return sorted(params)
    return []


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='VR Architecture Headless Runner - 严格复制 UVR GUI 行为',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 基本用法（如果模型在数据库中）
  python vr_headless_runner.py -m model.pth -i input.wav -o output/
  
  # 使用模型名称（支持自动下载）
  python vr_headless_runner.py -m "UVR-De-Echo-Normal" -i input.wav -o output/
  
  # 指定模型参数（如果模型不在数据库中）
  python vr_headless_runner.py -m model.pth --param 4band_v3 --primary-stem Vocals -i input.wav -o output/
  
  # 使用 GPU
  python vr_headless_runner.py -m model.pth -i input.wav -o output/ --gpu
  
  # VR 5.1 模型
  python vr_headless_runner.py -m model.pth --param 4band_v3 --primary-stem Vocals --nout 48 --nout-lstm 128 -i input.wav -o output/
  
  # 只输出 vocals
  python vr_headless_runner.py -m model.pth -i input.wav -o output/ --primary-only
  
  # 列出所有可用模型
  python vr_headless_runner.py --list
  
  # 列出未安装的模型
  python vr_headless_runner.py --list-uninstalled
  
  # 仅下载模型不推理
  python vr_headless_runner.py --download "UVR-De-Echo-Normal"

Available model params:
""" + '\n'.join(f"  - {p}" for p in list_available_params())
    )
    
    # 模型管理选项
    model_mgmt_group = parser.add_argument_group('Model Management')
    model_mgmt_group.add_argument('--list', action='store_true', help='列出所有可用模型')
    model_mgmt_group.add_argument('--list-installed', action='store_true', help='仅列出已安装的模型')
    model_mgmt_group.add_argument('--list-uninstalled', action='store_true', help='仅列出未安装的模型')
    model_mgmt_group.add_argument('--download', metavar='MODEL_NAME', help='下载指定模型（不运行推理）')
    model_mgmt_group.add_argument('--model-info', metavar='MODEL_NAME', help='显示指定模型的详细信息')
    
    parser.add_argument('--model', '-m', help='模型文件路径或名称（推理时必需）')
    parser.add_argument('--input', '-i', help='输入音频文件路径（推理时必需）')
    parser.add_argument('--output', '-o', help='输出目录路径（推理时必需）')
    parser.add_argument('--name', '-n', help='Output filename base (optional)')
    
    # 模型参数（当哈希查找失败时使用，模拟弹窗输入）
    param_group = parser.add_argument_group('Model Parameters (used when hash lookup fails)')
    param_group.add_argument('--param', help='Model param name (e.g., 4band_v3, 1band_sr44100_hl512)')
    param_group.add_argument('--primary-stem', help='Primary stem name (e.g., Vocals, Instrumental)')
    param_group.add_argument('--nout', type=int, help='VR 5.1 nout parameter')
    param_group.add_argument('--nout-lstm', type=int, help='VR 5.1 nout_lstm parameter')
    
    # 设备设置
    device_group = parser.add_argument_group('Device Settings')
    device_group.add_argument('--gpu', action='store_true', help='Use GPU')
    device_group.add_argument('--cpu', action='store_true', help='Force CPU')
    device_group.add_argument('--directml', action='store_true', help='Use DirectML (AMD GPU)')
    device_group.add_argument('--device', '-d', default=DEFAULT, help='GPU device ID (default: Default)')
    
    # VR 处理参数
    vr_group = parser.add_argument_group('VR Processing Parameters')
    vr_group.add_argument('--window-size', type=int, default=512, 
                         choices=[320, 512, 1024], help='Window size (default: 512)')
    vr_group.add_argument('--aggression', type=int, default=5,
                         help='Aggression setting (default: 5, presets: 0-50, supports custom values)')
    vr_group.add_argument('--batch-size', type=int, default=1, help='Batch size (default: 1)')
    vr_group.add_argument('--tta', action='store_true', help='Enable Test-Time Augmentation')
    vr_group.add_argument('--post-process', action='store_true', help='Enable post-processing')
    vr_group.add_argument('--post-process-threshold', type=float, default=0.2, 
                         help='Post-process threshold (default: 0.2)')
    vr_group.add_argument('--high-end-process', action='store_true', 
                         help='Enable high-end mirroring process')
    
    # 输出控制
    output_group = parser.add_argument_group('Output Control')
    output_group.add_argument('--primary-only', action='store_true', help='Save primary stem only')
    output_group.add_argument('--secondary-only', action='store_true', help='Save secondary stem only')
    output_group.add_argument('--wav-type', default='PCM_16',
                             choices=['PCM_U8', 'PCM_16', 'PCM_24', 'PCM_32', 'FLOAT', 'DOUBLE'],
                             help='Output audio bit depth (default: PCM_16)')
    
    parser.add_argument('--list-params', action='store_true', help='List available model params and exit')
    parser.add_argument('--quiet', '-q', action='store_true', help='静默模式（减少输出）')
    
    args = parser.parse_args()
    
    # 列出参数并退出
    if args.list_params:
        print("Available model params:")
        for p in list_available_params():
            print(f"  - {p}")
        return 0
    
    # 处理模型管理选项
    if args.list or args.list_installed or args.list_uninstalled:
        try:
            models = list_models(
                show_installed_only=args.list_installed,
                show_uninstalled_only=args.list_uninstalled,
                verbose=not args.quiet
            )
            
            label = "Installed" if args.list_installed else "Uninstalled" if args.list_uninstalled else "Available"
            print(f"\n{label} VR Models:")
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
            success, message = download_model(args.download, verbose=not args.quiet)
            print(message)
            return 0 if success else 1
        except Exception as e:
            print(f"下载模型时出错: {e}", file=sys.stderr)
            return 1
    
    if args.model_info:
        try:
            info = get_model_info(args.model_info, verbose=not args.quiet)
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
                    print(f"  文件名: {info.get('filename', 'N/A')}")
                    if info.get('url'):
                        print(f"  URL: {info['url']}")
            else:
                print(f"未找到模型: {args.model_info}")
                return 1
            return 0
        except Exception as e:
            print(f"获取模型信息时出错: {e}", file=sys.stderr)
            return 1
    
    # 验证推理所需的参数
    if not args.model:
        parser.error("--model 是推理所必需的参数（或使用 --list/--download 进行模型管理）")
    if not args.input:
        parser.error("--input 是推理所必需的参数")
    if not args.output:
        parser.error("--output 是推理所必需的参数")
    
    # 互斥检查
    if args.primary_only and args.secondary_only:
        parser.error("Cannot specify both --primary-only and --secondary-only")
    
    # Import error handler
    from error_handler import (
        classify_error, format_error_message, ErrorCategory,
        validate_audio_file, validate_output_directory
    )
    
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
    
    # GPU 设置
    use_gpu = None
    if args.cpu:
        use_gpu = False
    elif args.gpu:
        use_gpu = True
    
    # Try GPU first, fall back to CPU on GPU errors
    gpu_fallback_attempted = False
    current_use_gpu = use_gpu
    
    # Use ProgressManager for beautiful CLI output
    with ProgressManager(verbose=not args.quiet) as pm:
        # 解析模型路径（支持自动下载，包含进度显示）
        try:
            # Create a download progress callback from progress manager
            from progress import create_download_progress_callback
            download_callback = create_download_progress_callback(pm)
            model_path = resolve_model_path(
                args.model, 
                verbose=not args.quiet,
                progress_callback=download_callback
            )
        except FileNotFoundError as e:
            pm.write_message(f"错误: {e}", "red")
            return 1
        while True:
            try:
                success = run_vr_headless(
                    model_path=model_path,
                    audio_file=args.input,
                    export_path=args.output,
                    audio_file_base=args.name,
                    use_gpu=current_use_gpu,
                    device_set=args.device,
                    is_use_directml=args.directml if not gpu_fallback_attempted else False,
                    window_size=args.window_size,
                    aggression_setting=args.aggression,
                    batch_size=args.batch_size,
                    is_tta=args.tta,
                    is_post_process=args.post_process,
                    post_process_threshold=args.post_process_threshold,
                    is_high_end_process=args.high_end_process,
                    wav_type_set=args.wav_type,
                    user_vr_model_param=args.param,
                    user_primary_stem=args.primary_stem,
                    user_nout=args.nout,
                    user_nout_lstm=args.nout_lstm,
                    is_primary_stem_only=args.primary_only,
                    is_secondary_stem_only=args.secondary_only,
                    verbose=not args.quiet,
                    progress_manager=pm
                )
                
                return 0 if success else 1
                
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
