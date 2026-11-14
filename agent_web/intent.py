"""User-message intent checks. These gate TaskService actions; the prompt is not enough."""

from __future__ import annotations

ADJUSTMENT_MARKERS = (
    "换个",
    "换一",
    "换模型",
    "另一个模型",
    "别的模型",
    "残留",
    "比较",
    "对比",
    "调整",
    "再干净",
    "干净一点",
    "再来一版",
    "再出一版",
    "另一版",
    "换一版",
    "再试",
    "试试别的",
    "不够干净",
    "失真",
    "齿音",
    "混响",
    "新方案",
    "another model",
    "compare",
    "cleaner",
    "residual",
)

FULL_MARKERS = (
    "整首",
    "全曲",
    "整曲",
    "全长",
    "跑整首",
    "导出整首",
    "完整导出",
    "whole song",
    "full song",
    "entire song",
)


def message_requests_adjustment(text: str) -> bool:
    raw = text or ""
    folded = raw.lower()
    for marker in ADJUSTMENT_MARKERS:
        if marker.lower() in folded:
            return True
    return False


def message_requests_full(text: str) -> bool:
    raw = text or ""
    folded = raw.lower()
    # "先选方案" only stores a selection unless the same message also asks to process.
    select_only = ("先选" in raw or "只选" in raw) and not any(
        marker.lower() in folded for marker in ("整首", "全曲", "整曲", "全长", "whole song", "full song")
    )
    if select_only:
        return False
    return any(marker.lower() in folded for marker in FULL_MARKERS)
