from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from story_narrative import render_story
from narrative_expression import EXPRESSION_VERSION, express


SYSTEM = Path(__file__).resolve().parent.parent / "mingli-system"
KNOWLEDGE_PATH = SYSTEM / "wisdom_knowledge.json"
NARRATIVE_REFERENCE_DATE = "2026-09-20"


@lru_cache(maxsize=1)
def load_wisdom() -> dict[str, Any]:
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_youth() -> dict[str, Any]:
    return json.loads((SYSTEM / "youth_topics.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_early_childhood() -> dict[str, Any]:
    return json.loads((SYSTEM / "early_childhood_stories.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_teen() -> dict[str, Any]:
    return json.loads((SYSTEM / "teen_stories.json").read_text(encoding="utf-8"))


def render_youth_story(seed: str, context: dict[str, Any]) -> dict[str, Any]:
    early_childhood = context["age"] < 6
    teen = context["age"] >= 13
    knowledge = load_early_childhood() if early_childhood else load_teen() if teen else load_youth()
    topic = knowledge["topics"][context["id"]]
    selected = sorted(topic["arcs"], key=lambda arc: hashlib.sha256(f"{seed}|{arc['id']}".encode()).digest())[:2]
    arcs = [{"id": arc["id"], **{role: express(arc[role], seed, f"{arc['id']}:{role}") for role in ("scene", "tension", "choice", "reflection")}} for arc in selected]
    return {
        "title": topic["title"],
        "summary": arcs[0]["reflection"],
        "scenes": [text for arc in arcs for text in (arc["scene"], arc["tension"])],
        "insight": arcs[1]["reflection"],
        "listTitle": "可以一起试的小事",
        "items": [arc["choice"] for arc in arcs],
        "narrativeVoice": "成长场景",
        "narrativeLayout": "paired_arcs",
        "narrativeEvidence": {
            "knowledgeVersion": knowledge["version"],
            "expressionVersion": EXPRESSION_VERSION,
            "cardId": f"youth:{context['id']}",
            "fragmentIds": [f"{arc['id']}:{role}" for arc in arcs for role in ("scene", "tension", "choice", "reflection")],
            "sourceIds": sorted({source for arc in selected for source in arc.get("sourceIds", [])}),
            "evidenceType": "editorial_hypothesis",
            "selectionBasis": {"audience": "youth", "method": "age_appropriate_examples",
                               "developmentalBand": "early_childhood" if early_childhood else "teen" if teen else "school_age",
                               "reader": "caregiver" if early_childhood else "young_person_and_caregiver"},
            "interpretationBasis": "以实际年龄选择成长主题，不用出生盘给儿童定型。",
            "counterEvidence": "应以孩子的实际发展、感受与所需支持为准；不能用出生信息替代专业评估或预设成长结果。",
        },
    }


def render_wisdom_section(seed: str, context: dict[str, Any], used_groups: set[str] | None = None) -> dict[str, Any]:
    section = render_youth_story(seed, context) if context["age"] < 18 else render_story(seed, context, used_groups=used_groups)
    if context["id"] == "turning-points" and context["events"]:
        # Supplied events are observations, never generated predictions.
        events = "；".join(f"{item['date']} {item['type']}：{item['summary']}" for item in context["events"][:3])
        section["scenes"].append(f"你提供的经历记录是：{events}。这是已知经历，不是报告事先预测的结果。")
    return section


def render_followthrough(sections: list[dict[str, Any]], priority: list[str]) -> dict[str, Any]:
    """Recap actual earlier advice; do not introduce a new closing storyline."""
    by_id = {section["id"]: section for section in sections}
    selected = []
    for section_id in [*priority, "wellbeing", "relationships", "career"]:
        if section_id in by_id and section_id not in selected:
            selected.append(section_id)
        if len(selected) == 3:
            break
    sources = [by_id[section_id] for section_id in selected]
    fragments = [source["narrativeEvidence"]["fragmentIds"][2] for source in sources]
    return {
        "title": "接下来，从一件事开始",
        "summary": "",
        "scenes": [],
        "insight": "",
        "listTitle": "先选与你眼下最贴近的一项",
        "items": [source["items"][0] for source in sources],
        "narrativeVoice": "承接前文",
        "narrativeLayout": "linked_actions",
        "narrativeEvidence": {
            "knowledgeVersion": "followthrough-v3",
            "expressionVersion": EXPRESSION_VERSION,
            "cardId": "actions",
            "fragmentIds": fragments,
            "sourceIds": sorted({value for source in sources for value in source["narrativeEvidence"]["sourceIds"]}),
            "evidenceType": "editorial_hypothesis",
            "selectionBasis": {"method": "earlier_chapter_action_recap", "audience": "adult"},
            "linkedActions": [{"sectionId": source["id"], "itemIndex": 0,
                               "fragmentId": fragment} for source, fragment in zip(sources, fragments)],
            "interpretationBasis": "行动直接取自前文已解释的情境，不新增经历、预测或成功承诺。",
            "counterEvidence": "先核对实际处境；不适用的建议可以放下，实际效果比报告的措辞更重要。",
        },
    }
