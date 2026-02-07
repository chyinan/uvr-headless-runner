"""
Tests for progress.py

测试进度系统的枚举、数据类和计算逻辑。
不需要 rich/tqdm —— 测试纯逻辑部分。
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from progress import ProgressStage, StageProgress, STAGE_DESCRIPTIONS, STAGE_COLORS


# ============================================================================
# ProgressStage enum
# ============================================================================

class TestProgressStage:
    """进度阶段枚举测试"""

    def test_all_stages_have_descriptions(self):
        """每个阶段都应该有对应的描述"""
        for stage in ProgressStage:
            assert stage in STAGE_DESCRIPTIONS, f"Stage {stage} missing description"

    def test_all_stages_have_colors(self):
        """每个阶段都应该有对应的颜色"""
        for stage in ProgressStage:
            assert stage in STAGE_COLORS, f"Stage {stage} missing color"

    def test_expected_stages_exist(self):
        """应该包含关键的处理阶段"""
        expected = [
            "INITIALIZING", "DOWNLOADING_MODEL", "LOADING_MODEL",
            "INFERENCE", "COMPLETE", "ERROR"
        ]
        stage_names = [s.name for s in ProgressStage]
        for name in expected:
            assert name in stage_names, f"Missing stage: {name}"


# ============================================================================
# StageProgress
# ============================================================================

class TestStageProgress:
    """阶段进度数据类测试"""

    def test_percentage_basic(self):
        """百分比计算应该正确"""
        sp = StageProgress(current=50, total=100)
        assert sp.percentage == 50.0

    def test_percentage_zero_total(self):
        """total=0 时百分比应该是 0"""
        sp = StageProgress(current=0, total=0)
        assert sp.percentage == 0.0

    def test_percentage_capped_at_100(self):
        """百分比不应该超过 100"""
        sp = StageProgress(current=150, total=100)
        assert sp.percentage == 100.0

    def test_elapsed_time(self):
        """elapsed 应该返回正数"""
        sp = StageProgress()
        time.sleep(0.05)
        assert sp.elapsed >= 0.04

    def test_eta_returns_none_when_no_progress(self):
        """没有进度时 ETA 应该返回 None"""
        sp = StageProgress(current=0, total=100)
        assert sp.eta is None

    def test_eta_returns_value_when_progressing(self):
        """有进度时 ETA 应该返回正数"""
        sp = StageProgress(current=50, total=100)
        # 手动设置 start_time 到 10 秒前
        sp.start_time = time.time() - 10.0
        eta = sp.eta
        assert eta is not None
        assert eta > 0

    def test_speed_calculation(self):
        """速度计算应该返回合理的值"""
        sp = StageProgress(current=100, total=200)
        sp.start_time = time.time() - 10.0  # 10 秒前开始
        assert sp.speed > 0  # 100 items in 10 seconds = ~10/s

    def test_default_values(self):
        """默认值应该合理"""
        sp = StageProgress()
        assert sp.current == 0
        assert sp.total == 100
        assert sp.description == ""
