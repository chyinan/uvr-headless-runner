"""Tests for case-insensitive command and architecture handling in cli.py."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli import cmd_download, cmd_list, main


class TestCaseInsensitiveCommand:
    """Command and --arch names should be case-insensitive."""

    def test_uppercase_version_command(self, capsys):
        sys.argv = ["uvr", "VERSION"]
        assert main() == 0
        assert "uvr-headless-runner" in capsys.readouterr().out

    def test_uppercase_help_command(self, capsys):
        sys.argv = ["uvr", "HELP"]
        assert main() == 0
        assert "Usage" in capsys.readouterr().out

    @patch("cli._run_runner", return_value=0)
    def test_list_uppercase_arch(self, mock_run):
        assert cmd_list(["MDX"]) == 0
        mock_run.assert_called_once_with("mdx_headless_runner")

    @patch("cli._run_runner", return_value=0)
    def test_download_uppercase_arch(self, mock_run):
        assert cmd_download(["some-model", "--arch", "MDX"]) == 0
        mock_run.assert_called_once_with("mdx_headless_runner")
