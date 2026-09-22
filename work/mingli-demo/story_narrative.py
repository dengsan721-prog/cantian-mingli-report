from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from narrative_expression import EXPRESSION_VERSION, express


TOPICS = Path(__file__).resolve().parent.parent / "mingli-system" / "story_topics"
COUNTER_AXIS = {"自主驱动": "规则责任", "规则责任": "自主驱动", "表达创造": "学习内化",
                "学习内化": "表达创造", "资源经营": "规则责任"}


@lru_cache(maxsize=10)
def load_topic(topic: str) -> dict[str, Any]:
    return json.loads((TOPICS / f"{topic}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_applicability() -> dict[str, Any]:
    return json.loads((TOPICS.parent / "story_applicability.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=10)
def load_variants(topic: str) -> dict[str, Any]:
    path = TOPICS.parent / "story_variants" / f"{topic}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def render_story(seed: str, context: dict[str, Any], used_groups: set[str] | None = None) -> dict[str, Any]:
    topic = load_topic(context["id"])
    # Each aligned row is one complete arc; never attach another row's advice.
    applicability = load_applicability()
    tags = applicability["topics"][context["id"]]
    axis_tag = applicability["axes"].get(context.get("axisDrive"))
    counter_tag = applicability["axes"].get(COUNTER_AXIS.get(context.get("axisDrive")))
    matching = [index for index, values in enumerate(tags) if axis_tag in values]
    contrast = [index for index, values in enumerate(tags) if counter_tag in values]
    eligible = matching or list(range(len(topic["scene"])))
    entry_rows = topic.get("entryRows")
    if entry_rows is not None:
        eligible = [index for index in eligible if index in entry_rows] or entry_rows
    groups = [set() for _ in tags]
    for group, members in applicability.get("overlapGroups", {}).items():
        for member in members:
            topic_id, row = member.rsplit(":", 1)
            if topic_id == context["id"]:
                groups[int(row)].add(group)
    seen = set(used_groups or ())
    # Respect topic eligibility first; disclose a conflict if that pool is exhausted.
    fresh = [index for index in eligible if not groups[index] & seen]
    excluded = [len(eligible) - len(fresh) if fresh else 0]
    eligible = fresh or eligible
    first = min(eligible, key=lambda index: hashlib.sha256(f"{seed}|{context['id']}|arc|{index}".encode()).digest())
    reused = groups[first] & seen
    seen.update(groups[first])
    question = next((group for group in topic.get("questionGroups", [])
                     if any(first in rows for rows in group["angles"].values())), None)
    question_angles = {index: angle for angle, rows in question["angles"].items() for index in rows} if question else {}
    if question:
        counterparts = [index for index, angle in question_angles.items() if angle != question_angles[first]]
    else:
        counterparts = [index for index in contrast if index != first] or [index for index in range(len(topic["scene"])) if index != first]
    secondary_rows = topic.get("secondaryRows")
    if secondary_rows is not None:
        counterparts = [index for index in counterparts if index in secondary_rows]
        if not counterparts:
            raise ValueError(f"No eligible secondary story for {context['id']} row {first}")
    families = topic.get("families", [])
    distinct = [index for index in counterparts if families[index] != families[first]] if families else []
    if distinct:
        counterparts = distinct
    fresh = [index for index in counterparts if not groups[index] & seen]
    excluded.append(len(counterparts) - len(fresh) if fresh else 0)
    counterparts = fresh or counterparts
    # Different question angles already provide contrast; do not collapse them to one axis.
    second = min(counterparts, key=lambda index: hashlib.sha256(f"{seed}|{context['id']}|counter|{index}".encode()).digest())
    reused.update(groups[second] & seen)
    indices = [first, second]
    # Preserve selection identities; stage order only controls how whole arcs are read.
    angle_order = question.get("angleOrder", []) if question else []
    reading_order = sorted(range(2), key=lambda position: angle_order.index(question_angles[indices[position]])) if angle_order else [0, 1]
    variants = load_variants(context["id"])
    arcs, variants_used = [], {}
    for index in indices:
        arc = {}
        for role in ("scene", "tension", "choice", "reflection"):
            fragment_id = f"{context['id']}:{role}:{index}"
            choices = [topic[role][index], *(variants["rows"][index].get(role, []) if variants else [])]
            # Option indices are append-only IDs, so new options cannot reshuffle old scores.
            selected = min(range(len(choices)), key=lambda option: hashlib.sha256(
                f"{seed}|{fragment_id}|paragraph-option|{option}".encode()).digest())
            arc[role] = express(choices[selected], seed, fragment_id)
            variants_used[fragment_id] = selected
        arcs.append(arc)
    return {
        "title": question["title"] if question else topic.get("title", context["title"]),
        "summary": arcs[0]["reflection"],
        "scenes": [paragraph for arc in arcs for paragraph in (arc["scene"], arc["tension"])],
        "insight": arcs[1]["reflection"],
        "listTitle": "可以亲手尝试的一步",
        "items": [arc["choice"] for arc in arcs],
        "narrativeVoice": "双场景对照",
        "narrativeLayout": "paired_arcs",
        "narrativeArcOrder": reading_order,
        "narrativeEvidence": {
            "knowledgeVersion": "story-topics-v47",
            "readingOrder": {"version": "decision-stages-v1", "applied": bool(angle_order),
                             "scope": "同一问题的编辑阅读顺序，不代表用户经历的时间线，也不计作新增情境"},
            "applicabilityVersion": applicability["version"],
            "expressionVersion": EXPRESSION_VERSION,
            "paragraphVariantVersion": variants.get("version"),
            "paragraphSelectionVersion": "append-only-rendezvous-v1",
            "pairSelectionVersion": "question-angle-rendezvous-v2",
            "paragraphVariants": variants_used,
            "cardId": context["id"],
            "fragmentIds": [f"{context['id']}:{role}:{index}" for index in indices for role in ("scene", "tension", "choice", "reflection")],
            "sourceIds": ["MBTI_PREFERENCES", "VIA_BALANCE"],
            "evidenceType": "editorial_hypothesis",
            "selectionBasis": {"method": "traditional_axis_editorial_topic_tags", "audience": "adult",
                               "axis": context.get("axisDrive"), "axisTag": axis_tag,
                               "counterAxis": COUNTER_AXIS.get(context.get("axisDrive")), "counterTag": counter_tag,
                               "counterAxisApplied": counter_tag is not None and counter_tag in tags[second],
                               "counterpartPolicy": "same_question_other_angle" if question else "traditional_counter_axis_fallback",
                               "questionLink": {"version": topic.get("questionVersion"), "applied": bool(question),
                                                "id": question["id"] if question else None,
                                                "question": question["question"] if question else None,
                                                "angles": [question_angles[index] for index in indices] if question else [],
                                                "scope": topic.get("questionScope")},
                               "selectedTags": [tags[index] for index in indices],
                               "eligibleCount": len(eligible), "counterpartCount": len(counterparts),
                               "entryScope": topic.get("entryScope"), "entryRestricted": entry_rows is not None,
                               "secondaryScope": topic.get("secondaryScope"), "secondaryRestricted": secondary_rows is not None,
                               "reportContrast": {"version": applicability.get("overlapVersion"),
                                                  "selectedGroups": sorted(groups[first] | groups[second]),
                                                  "excludedCandidateCounts": excluded,
                                                  "reusedGroups": sorted(reused),
                                                  "scope": applicability.get("overlapScope")},
                               "familyContrast": {"version": topic.get("familyVersion"), "applied": bool(distinct),
                                                  "selected": [families[index] for index in indices] if families else [],
                                                  "scope": "编辑情境组用于阅读编排，不代表语义互异或预测验证"},
                               "matchScope": "一个相关主题场景加一个补充视角；不代表本人实际经历或经过验证的人格特征"},
            "outline": {"hypothesis": context["core"], "tension": context["tension"], "counter": context["counter"]},
            "interpretationBasis": context["evidence"],
            "counterEvidence": context["counter"],
        },
    }
