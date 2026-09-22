from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


TARGET = 0.06


class NarrativeDiversityError(ValueError):
    pass


def body_text(sections: list[dict[str, Any]]) -> str:
    parts = []
    for section in sections:
        parts.extend([section.get("summary", ""), *section.get("scenes", []), section.get("insight", "")])
        parts.extend(section.get("items", []))
    return re.sub(r"\s+", "", "".join(parts))


def shingles(text: str) -> set[str]:
    return {text[index:index + 7] for index in range(max(0, len(text) - 6))}


def jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, len(left | right))


def validate_draft(
    sections: list[dict[str, Any]],
    references: Iterable[str],
) -> dict[str, Any]:
    """Audit a canonical draft; history must never choose different prose."""
    reference_sets = [shingles(text) for text in references if text]
    draft = shingles(body_text(sections))
    maximum = max((jaccard(draft, other) for other in reference_sets), default=0.0)
    if maximum >= TARGET:
        raise NarrativeDiversityError(
            f"本次正文尚未通过差异化检查（最高重合{maximum:.2%}）。"
            "未保存未达标报告，也不会改变研判依据或重新抽稿来凑差异；需要继续补充适用的叙事素材。"
        )
    return {"metric": "body-jaccard-7", "threshold": TARGET, "maxSimilarity": maximum,
            "referenceCount": len(reference_sets), "draftRevision": 0, "attempts": 1,
            "generationPolicy": "input_deterministic_history_audit_only",
            "scope": "个性化正文的字面重合，不是语义差异或预测准确率"}
