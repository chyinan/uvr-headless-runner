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

import os
import sys
import json
import math
import hashlib
import torch
import argparse
from pathlib import Path
from types import SimpleNamespace

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入必需的模块
from separate import SeperateVR, prepare_mix
from lib_v5.vr_network.model_param_init import ModelParameters
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


def create_process_data(audio_file, export_path, audio_file_base=None):
    """
    创建 process_data 字典
    
    与 UVR 的 process_data 结构完全一致
    """
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    def noop_progress(step=0, inference_iterations=0):
        pass
    
    def write_console(progress_text='', base_text=''):
        # UVR GUI 会写入控制台，headless 也打印
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
    **kwargs
):
    """
    Headless VR Architecture 运行器主函数
    
    直接使用 UVR 原有的 SeperateVR 类，行为与 GUI 完全一致
    """
    # 验证输入文件
    if not os.path.isfile(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    if not os.path.isdir(export_path):
        os.makedirs(export_path, exist_ok=True)
    
    # 加载哈希映射（与 UVR.py line 1712 一致）
    if os.path.isfile(VR_HASH_JSON):
        vr_hash_MAPPER = load_model_hash_data(VR_HASH_JSON)
    else:
        vr_hash_MAPPER = {}
    
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
    
    # 检查 model_status（与 UVR 行为一致）
    if not model_data.model_status:
        # UVR GUI 在这种情况下不会运行分离，只是静默返回
        # 但 headless 需要通知用户
        print(f"Error: Model status is False for {model_path}")
        print(f"Model hash: {model_data.model_hash}")
        if not hasattr(model_data, 'vr_model_param') or model_data.vr_model_param is None:
            print(f"Model hash not found in database. Please provide --param and --primary-stem arguments.")
            print(f"Example: --param 4band_v3 --primary-stem Vocals")
            if os.path.isdir(VR_PARAM_DIR):
                params = [os.path.splitext(f)[0] for f in os.listdir(VR_PARAM_DIR) if f.endswith('.json')]
                print(f"Available params: {', '.join(sorted(params))}")
        return False
    
    # 创建 process_data
    if audio_file_base is None:
        audio_file_base = os.path.splitext(os.path.basename(audio_file))[0]
    
    process_data = create_process_data(
        audio_file,
        export_path,
        audio_file_base
    )
    process_data['model_data'] = model_data
    
    # 打印信息
    print("=" * 60)
    print("VR Architecture Headless Runner")
    print("=" * 60)
    print(f"Model: {model_data.model_path}")
    print(f"Input: {audio_file}")
    print(f"Output: {export_path}")
    print(f"Device: {'GPU' if model_data.is_gpu_conversion >= 0 else 'CPU'}")
    print(f"VR 5.1 Model: {model_data.is_vr_51_model}")
    print(f"Model Capacity: {model_data.model_capacity}")
    print(f"Sample Rate: {model_data.model_samplerate}")
    print(f"Primary Stem: {model_data.primary_stem}")
    print(f"Secondary Stem: {model_data.secondary_stem}")
    print(f"Window Size: {model_data.window_size}")
    print(f"Aggression: {model_data.aggression_setting * 100:.0f}%")
    print(f"TTA: {model_data.is_tta}")
    print(f"Post Process: {model_data.is_post_process}")
    print(f"High End Process: {model_data.is_high_end_process}")
    print(f"Output Format: {model_data.wav_type_set}")
    print("=" * 60)
    
    # 运行分离 - 使用 UVR 原有的类
    separator = SeperateVR(model_data, process_data)
    print(f"Actual device: {separator.device}")
    separator.seperate()
    
    print(f"\nProcessing complete!")
    print(f"Output: {export_path}")
    
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
  
  # 指定模型参数（如果模型不在数据库中）
  python vr_headless_runner.py -m model.pth --param 4band_v3 --primary-stem Vocals -i input.wav -o output/
  
  # 使用 GPU
  python vr_headless_runner.py -m model.pth -i input.wav -o output/ --gpu
  
  # VR 5.1 模型
  python vr_headless_runner.py -m model.pth --param 4band_v3 --primary-stem Vocals --nout 48 --nout-lstm 128 -i input.wav -o output/
  
  # 只输出 vocals
  python vr_headless_runner.py -m model.pth -i input.wav -o output/ --primary-only

Available model params:
""" + '\n'.join(f"  - {p}" for p in list_available_params())
    )
    
    parser.add_argument('--model', '-m', required=True, help='Model file path (.pth)')
    parser.add_argument('--input', '-i', required=True, help='Input audio file path')
    parser.add_argument('--output', '-o', required=True, help='Output directory path')
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
    
    args = parser.parse_args()
    
    # 列出参数并退出
    if args.list_params:
        print("Available model params:")
        for p in list_available_params():
            print(f"  - {p}")
        return 0
    
    # 互斥检查
    if args.primary_only and args.secondary_only:
        parser.error("Cannot specify both --primary-only and --secondary-only")
    
    # GPU 设置
    use_gpu = None
    if args.cpu:
        use_gpu = False
    elif args.gpu:
        use_gpu = True
    
    try:
        success = run_vr_headless(
            model_path=args.model,
            audio_file=args.input,
            export_path=args.output,
            audio_file_base=args.name,
            use_gpu=use_gpu,
            device_set=args.device,
            is_use_directml=args.directml,
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
            is_secondary_stem_only=args.secondary_only
        )
        
        return 0 if success else 1
    except Exception as e:
        import traceback
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
