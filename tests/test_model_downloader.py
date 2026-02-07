"""
Tests for model_downloader.py

测试模型下载器的纯逻辑部分：fuzzy matching、代理检测、文件验证等。
这些测试不需要网络连接或真实模型文件。
"""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model_downloader import (
    fuzzy_match_model,
    format_bytes,
    is_valid_model_file,
    get_proxy_status,
    is_proxy_configured,
    MIN_MODEL_FILE_SIZE,
)


# ============================================================================
# fuzzy_match_model
# ============================================================================

class TestFuzzyMatchModel:
    """模糊匹配模型名测试 —— 这是用户体验的关键功能"""

    SAMPLE_MODELS = [
        "UVR-MDX-NET Inst HQ 1",
        "UVR-MDX-NET Inst HQ 2",
        "UVR-MDX-NET Inst HQ 3",
        "UVR-MDX-NET Voc FT",
        "UVR-De-Echo-Normal",
        "UVR-De-Echo-Aggressive",
        "htdemucs",
        "htdemucs_ft",
        "htdemucs_6s",
        "hdemucs_mmi",
    ]

    def test_exact_substring_match(self):
        """精确子串应该被匹配"""
        results = fuzzy_match_model("Inst HQ 3", self.SAMPLE_MODELS)
        assert "UVR-MDX-NET Inst HQ 3" in results

    def test_case_insensitive(self):
        """匹配应该忽略大小写"""
        results = fuzzy_match_model("inst hq 3", self.SAMPLE_MODELS)
        assert "UVR-MDX-NET Inst HQ 3" in results

    def test_partial_match_returns_similar(self):
        """部分匹配应该返回相似的模型"""
        results = fuzzy_match_model("UVR-MDX Inst HQ", self.SAMPLE_MODELS)
        # 应该返回所有 HQ 模型
        assert len(results) >= 1
        assert all("HQ" in r for r in results[:3])

    def test_no_match_returns_empty(self):
        """完全不相关的查询应该返回空列表"""
        results = fuzzy_match_model("zzzzz_nonexistent_model_xyz", self.SAMPLE_MODELS)
        assert len(results) == 0

    def test_demucs_match(self):
        """Demucs 模型名应该被正确匹配"""
        results = fuzzy_match_model("htdemucs", self.SAMPLE_MODELS)
        assert "htdemucs" in results

    def test_echo_models_match(self):
        """Echo 模型名应该被正确匹配"""
        results = fuzzy_match_model("De-Echo", self.SAMPLE_MODELS)
        echo_results = [r for r in results if "Echo" in r]
        assert len(echo_results) >= 2

    def test_results_sorted_by_similarity(self):
        """结果应该按相似度排序（最相似的在前）"""
        results = fuzzy_match_model("UVR-MDX-NET Inst HQ 3", self.SAMPLE_MODELS)
        assert results[0] == "UVR-MDX-NET Inst HQ 3"

    def test_empty_model_list(self):
        """空模型列表应该返回空结果"""
        results = fuzzy_match_model("anything", [])
        assert results == []

    def test_threshold_controls_strictness(self):
        """高阈值应该返回更少的结果"""
        loose = fuzzy_match_model("UVR MDX", self.SAMPLE_MODELS, threshold=0.3)
        strict = fuzzy_match_model("UVR MDX", self.SAMPLE_MODELS, threshold=0.9)
        assert len(loose) >= len(strict)


# ============================================================================
# format_bytes
# ============================================================================

class TestFormatBytes:
    """文件大小格式化测试"""

    def test_bytes(self):
        assert "B" in format_bytes(500)

    def test_kilobytes(self):
        result = format_bytes(1024)
        assert "KB" in result or "K" in result

    def test_megabytes(self):
        result = format_bytes(1024 * 1024 * 50)
        assert "MB" in result or "M" in result

    def test_gigabytes(self):
        result = format_bytes(1024 * 1024 * 1024 * 2)
        assert "GB" in result or "G" in result

    def test_zero(self):
        result = format_bytes(0)
        assert "0" in result


# ============================================================================
# is_valid_model_file
# ============================================================================

class TestIsValidModelFile:
    """模型文件有效性检测测试"""

    def test_nonexistent_file_is_invalid(self):
        """不存在的文件应该是无效的"""
        assert is_valid_model_file("/nonexistent/model.ckpt") is False

    def test_empty_file_is_invalid(self):
        """空文件应该是无效的"""
        with tempfile.NamedTemporaryFile(suffix=".ckpt", delete=False) as f:
            tmp_path = f.name
        try:
            assert is_valid_model_file(tmp_path) is False
        finally:
            os.unlink(tmp_path)

    def test_too_small_file_is_invalid(self):
        """小于最小大小的文件应该是无效的"""
        with tempfile.NamedTemporaryFile(suffix=".ckpt", delete=False) as f:
            f.write(b"x" * (MIN_MODEL_FILE_SIZE - 1))
            tmp_path = f.name
        try:
            assert is_valid_model_file(tmp_path) is False
        finally:
            os.unlink(tmp_path)

    def test_valid_size_file(self):
        """足够大的文件应该是有效的"""
        with tempfile.NamedTemporaryFile(suffix=".ckpt", delete=False) as f:
            f.write(b"x" * (MIN_MODEL_FILE_SIZE + 1))
            tmp_path = f.name
        try:
            assert is_valid_model_file(tmp_path) is True
        finally:
            os.unlink(tmp_path)


# ============================================================================
# Proxy detection
# ============================================================================

class TestProxyDetection:
    """代理检测测试"""

    def test_no_proxy_when_env_empty(self, monkeypatch):
        """没有设置代理环境变量时应该返回 False"""
        for var in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy', 
                     'NO_PROXY', 'no_proxy']:
            monkeypatch.delenv(var, raising=False)
        assert is_proxy_configured() is False

    def test_proxy_detected_when_http_set(self, monkeypatch):
        """设置 HTTP_PROXY 时应该检测到代理"""
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
        assert is_proxy_configured() is True

    def test_proxy_detected_when_https_set(self, monkeypatch):
        """设置 HTTPS_PROXY 时应该检测到代理"""
        for var in ['HTTP_PROXY', 'http_proxy']:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy:8080")
        assert is_proxy_configured() is True

    def test_proxy_status_returns_dict(self, monkeypatch):
        """get_proxy_status 应该返回正确结构的字典"""
        for var in ['HTTP_PROXY', 'http_proxy', 'HTTPS_PROXY', 'https_proxy',
                     'NO_PROXY', 'no_proxy']:
            monkeypatch.delenv(var, raising=False)
        status = get_proxy_status()
        assert isinstance(status, dict)
        assert 'http_proxy' in status
        assert 'https_proxy' in status
        assert 'no_proxy' in status

    def test_proxy_status_reflects_env(self, monkeypatch):
        """代理状态应该反映环境变量"""
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
        monkeypatch.setenv("NO_PROXY", "localhost")
        for var in ['HTTPS_PROXY', 'https_proxy']:
            monkeypatch.delenv(var, raising=False)
        
        status = get_proxy_status()
        assert status['http_proxy'] is True
        assert status['no_proxy'] is True
