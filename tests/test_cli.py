"""
Tests for cli.py (Unified CLI entry point)

测试统一 CLI 的命令分发、help 输出、错误处理。
不导入 runner 模块（可能缺少依赖），只测试 cli.py 自身逻辑。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import (
    VERSION,
    print_banner,
    print_usage,
    print_info,
    main,
)


class TestCLIBasics:
    """CLI 基础功能测试"""

    def test_version_string(self):
        """VERSION 应该是合法的版本字符串"""
        parts = VERSION.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_help_returns_zero(self):
        """'uvr help' 应该返回 0"""
        sys.argv = ["uvr", "help"]
        result = main()
        assert result == 0

    def test_version_command_returns_zero(self):
        """'uvr version' 应该返回 0"""
        sys.argv = ["uvr", "version"]
        result = main()
        assert result == 0

    def test_no_args_shows_help(self):
        """无参数时应该显示帮助并返回 0"""
        sys.argv = ["uvr"]
        result = main()
        assert result == 0

    def test_unknown_command_returns_nonzero(self):
        """未知命令应该返回非零退出码"""
        sys.argv = ["uvr", "nonexistent_command"]
        result = main()
        assert result == 1

    def test_info_returns_zero(self):
        """'uvr info' 应该返回 0"""
        sys.argv = ["uvr", "info"]
        result = main()
        assert result == 0

    def test_dash_help_returns_zero(self):
        """'uvr --help' 应该返回 0"""
        sys.argv = ["uvr", "--help"]
        result = main()
        assert result == 0

    def test_dash_version_returns_zero(self):
        """'uvr --version' 应该返回 0"""
        sys.argv = ["uvr", "--version"]
        result = main()
        assert result == 0


class TestCLIHelp:
    """CLI help 输出内容测试"""

    def test_print_usage_contains_commands(self, capsys):
        """help 输出应该包含所有子命令"""
        print_usage()
        captured = capsys.readouterr()
        assert "mdx" in captured.out
        assert "demucs" in captured.out
        assert "vr" in captured.out
        assert "list" in captured.out
        assert "download" in captured.out
        assert "info" in captured.out

    def test_print_usage_contains_examples(self, capsys):
        """help 输出应该包含使用示例"""
        print_usage()
        captured = capsys.readouterr()
        assert "Examples:" in captured.out
        assert "uvr mdx" in captured.out

    def test_print_banner_contains_version(self, capsys):
        """banner 应该包含版本号"""
        print_banner()
        captured = capsys.readouterr()
        assert VERSION in captured.out

    def test_print_info_shows_python(self, capsys):
        """info 应该显示 Python 版本"""
        print_info()
        captured = capsys.readouterr()
        assert "Python:" in captured.out


class TestCLIRunnerDispatch:
    """Runner 分发测试（不依赖实际 runner 模块）"""

    def test_mdx_with_missing_deps_returns_error(self):
        """当依赖缺失时，mdx 命令应该返回错误码而非崩溃"""
        sys.argv = ["uvr", "mdx", "--help"]
        result = main()
        # 如果依赖已安装，argparse --help 返回 0
        # 如果依赖缺失，_run_runner 返回 1
        assert result in (0, 1)

    def test_demucs_with_missing_deps_returns_error(self):
        """当依赖缺失时，demucs 命令应该优雅处理"""
        sys.argv = ["uvr", "demucs", "--help"]
        result = main()
        assert result in (0, 1)

    def test_vr_with_missing_deps_returns_error(self):
        """当依赖缺失时，vr 命令应该优雅处理"""
        sys.argv = ["uvr", "vr", "--help"]
        result = main()
        assert result in (0, 1)


class TestCLIDownload:
    """Download 子命令参数解析测试"""

    def test_download_without_model_name(self, capsys):
        """download 没有模型名时应该报错"""
        sys.argv = ["uvr", "download"]
        result = main()
        captured = capsys.readouterr()
        assert result == 1
        assert "Model name required" in captured.out

    def test_download_without_arch(self, capsys):
        """download 没有 --arch 时应该报错"""
        sys.argv = ["uvr", "download", "some-model"]
        result = main()
        captured = capsys.readouterr()
        assert result == 1
        assert "Architecture required" in captured.out

    def test_download_invalid_arch(self, capsys):
        """download 使用无效架构时应该报错"""
        sys.argv = ["uvr", "download", "some-model", "--arch", "invalid"]
        result = main()
        captured = capsys.readouterr()
        assert result == 1
        assert "Unknown architecture" in captured.out


class TestCLIList:
    """List 子命令测试"""

    def test_list_invalid_arch(self, capsys):
        """list 使用无效架构时应该报错"""
        sys.argv = ["uvr", "list", "invalid"]
        result = main()
        captured = capsys.readouterr()
        assert result == 1
        assert "Unknown architecture" in captured.out
