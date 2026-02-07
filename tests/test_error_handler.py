"""
Tests for error_handler.py

这些测试验证错误分类、消息格式化和文件验证逻辑。
不需要 GPU、模型文件或音频文件 —— 纯逻辑测试。
"""

import os
import sys
import tempfile
import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from error_handler import (
    ErrorCategory,
    classify_error,
    format_error_message,
    handle_gpu_error,
    safe_run,
    validate_audio_file,
    validate_output_directory,
)


# ============================================================================
# classify_error
# ============================================================================

class TestClassifyError:
    """错误分类测试 —— 确保各种异常被正确归类"""

    def test_cuda_oom_classified_as_gpu(self):
        """CUDA OOM 应该被归类为 GPU 错误且可恢复"""
        err = RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.GPU
        assert info["recoverable"] is True
        assert "GPU memory" in info["message"]

    def test_cuda_generic_error(self):
        """通用 CUDA error 应该被归类为 GPU 错误"""
        err = RuntimeError("CUDA error: device-side assert triggered")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.GPU
        assert info["recoverable"] is True

    def test_directml_error(self):
        """DirectML 错误应该被归类为 GPU 错误"""
        err = RuntimeError("DirectML device creation failed")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.GPU

    def test_file_not_found(self):
        """文件未找到应该被归类为文件系统错误"""
        err = FileNotFoundError("No such file or directory: '/path/to/model.ckpt'")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.FILE_SYSTEM
        assert info["recoverable"] is False

    def test_permission_denied(self):
        """权限错误应该被归类为文件系统错误"""
        err = PermissionError("Permission denied: '/root/output'")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.FILE_SYSTEM

    def test_invalid_model(self):
        """无效模型应该被归类为模型错误"""
        err = RuntimeError("Invalid model format")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.MODEL

    def test_audio_format_error(self):
        """音频格式错误应该被归类为音频错误"""
        err = Exception("Unsupported format: .xyz")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.AUDIO

    def test_network_timeout(self):
        """网络超时应该被归类为网络错误"""
        err = ConnectionError("Connection timed out")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.NETWORK

    def test_ssl_error(self):
        """SSL 错误应该被归类为网络错误"""
        err = Exception("SSL: CERTIFICATE_VERIFY_FAILED")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.NETWORK

    def test_unknown_error_fallback(self):
        """未知错误应该被归类为 UNKNOWN"""
        err = ValueError("some completely random error xyz123")
        info = classify_error(err)
        assert info["category"] == ErrorCategory.UNKNOWN
        assert info["recoverable"] is False

    def test_classify_always_returns_required_keys(self):
        """无论什么错误，返回值都应该包含必要的 key"""
        for err in [RuntimeError("test"), ValueError("test"), Exception("test")]:
            info = classify_error(err)
            assert "category" in info
            assert "message" in info
            assert "suggestion" in info
            assert "recoverable" in info
            assert "original" in info
            assert "type" in info


# ============================================================================
# format_error_message
# ============================================================================

class TestFormatErrorMessage:
    """错误消息格式化测试"""

    def test_basic_format(self):
        """基本格式化应该包含 ERROR 标记和消息"""
        info = classify_error(RuntimeError("CUDA out of memory"))
        msg = format_error_message(info)
        assert "ERROR" in msg
        assert "GPU memory" in msg

    def test_verbose_includes_details(self):
        """verbose 模式应该包含技术细节"""
        info = classify_error(RuntimeError("CUDA out of memory, tried 2GB"))
        msg = format_error_message(info, verbose=True)
        assert "Technical details" in msg
        assert "Type:" in msg

    def test_non_verbose_omits_details(self):
        """非 verbose 模式不应该包含技术细节"""
        info = classify_error(RuntimeError("CUDA out of memory"))
        msg = format_error_message(info, verbose=False)
        assert "Technical details" not in msg

    def test_includes_suggestion(self):
        """应该包含建议信息"""
        info = classify_error(RuntimeError("CUDA out of memory"))
        msg = format_error_message(info)
        assert "Suggestion" in msg


# ============================================================================
# safe_run
# ============================================================================

class TestSafeRun:
    """safe_run 包装函数测试"""

    def test_success_returns_true(self):
        """成功执行应该返回 (True, result)"""
        success, result = safe_run(lambda: 42, verbose=False)
        assert success is True
        assert result == 42

    def test_failure_returns_false(self):
        """异常应该返回 (False, error_info)"""
        def fail():
            raise ValueError("test error")
        
        success, result = safe_run(fail, verbose=False)
        assert success is False


# ============================================================================
# validate_audio_file
# ============================================================================

class TestValidateAudioFile:
    """音频文件验证测试"""

    def test_nonexistent_file(self):
        """不存在的文件应该验证失败"""
        valid, msg = validate_audio_file("/nonexistent/path/audio.wav")
        assert valid is False
        assert "not found" in msg

    def test_empty_file(self):
        """空文件应该验证失败"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"")
            tmp_path = f.name
        try:
            valid, msg = validate_audio_file(tmp_path)
            assert valid is False
            assert "empty" in msg
        finally:
            os.unlink(tmp_path)

    def test_too_small_file(self):
        """过小的文件应该验证失败"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"x" * 100)
            tmp_path = f.name
        try:
            valid, msg = validate_audio_file(tmp_path)
            assert valid is False
            assert "small" in msg
        finally:
            os.unlink(tmp_path)

    def test_unsupported_extension(self):
        """不支持的文件格式应该验证失败"""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"x" * 2048)
            tmp_path = f.name
        try:
            valid, msg = validate_audio_file(tmp_path)
            assert valid is False
            assert "Unsupported" in msg
        finally:
            os.unlink(tmp_path)

    def test_valid_wav_file(self):
        """足够大的 .wav 文件应该验证通过"""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"x" * 2048)
            tmp_path = f.name
        try:
            valid, msg = validate_audio_file(tmp_path)
            assert valid is True
        finally:
            os.unlink(tmp_path)

    def test_valid_extensions(self):
        """所有支持的扩展名都应该通过格式检查"""
        for ext in [".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".aiff"]:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(b"x" * 2048)
                tmp_path = f.name
            try:
                valid, _ = validate_audio_file(tmp_path)
                assert valid is True, f"Extension {ext} should be valid"
            finally:
                os.unlink(tmp_path)


# ============================================================================
# validate_output_directory
# ============================================================================

class TestValidateOutputDirectory:
    """输出目录验证测试"""

    def test_existing_writable_dir(self):
        """已存在的可写目录应该验证通过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid, msg = validate_output_directory(tmpdir)
            assert valid is True

    def test_creates_new_dir(self):
        """不存在的目录应该被自动创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "new_output_dir")
            valid, msg = validate_output_directory(new_dir)
            assert valid is True
            assert os.path.isdir(new_dir)

    def test_path_is_file_not_dir(self):
        """路径是文件而非目录时应该验证失败"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmp_path = f.name
        try:
            valid, msg = validate_output_directory(tmp_path)
            assert valid is False
            assert "not a directory" in msg
        finally:
            os.unlink(tmp_path)
