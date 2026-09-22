from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from narrative_diversity import TARGET, NarrativeDiversityError, body_text, validate_draft
from narrative_expression import EXPRESSION_VERSION, express
from narrative_engine import _ten_god_axis, narrative_similarity
from report_engine import generate_report
from server import connect, generate_and_save_report, list_reports
from story_narrative import TOPICS, load_applicability, load_topic, load_variants, render_story
from test_report_engine import exact_payload
from wisdom_narrative import load_early_childhood, load_teen, render_youth_story


@lru_cache(maxsize=1)
def archived_review_coverage():
    """Check preserved legacy material with an explicit archive-only pool override."""
    topic, bank = load_topic("review"), load_variants("review")
    roles = ("scene", "tension", "choice", "reflection")
    context = {"id": "review", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
               "core": "生活观察", "tension": "不是已知经历", "axisDrive": "综合承接"}
    cases = []
    for target in range(64):
        group = next(g for g in topic["questionGroups"] if any(target in rows for rows in g["angles"].values()))
        angle = next(a for a, rows in group["angles"].items() if target in rows)
        first = next(i for a, rows in group["angles"].items() if a != angle
                     for i in rows if i in topic["entryRows"])
        focused = deepcopy(topic)
        focused["entryRows"] = [first]
        focused.pop("secondaryRows")
        focused.pop("secondaryScope")
        selected = {role: set() for role in roles}
        with patch("story_narrative.load_topic", return_value=focused):
            for index in range(512):
                seed = f"review-question-coverage-{target}-{index}"
                story = render_story(seed, context)
                evidence = story["narrativeEvidence"]
                if evidence["fragmentIds"][4] != f"review:scene:{target}":
                    continue
                cases.append((seed, story))
                for role in roles:
                    selected[role].add(evidence["paragraphVariants"][f"review:{role}:{target}"])
                if all(selected[role] == set(range(1 + len(bank["rows"][target][role]))) for role in roles):
                    break
        if not all(selected[role] == set(range(1 + len(bank["rows"][target][role]))) for role in roles):
            raise AssertionError(f"Review row {target} has unreachable wordings: {selected}")
    return tuple(cases)


def variant_options(topic_id: str, row: int, role: str) -> set[int]:
    return set(range(1 + len(load_variants(topic_id)["rows"][row][role])))


class NarrativeDiversityTests(unittest.TestCase):
    def test_review_archive_keeps_complete_arcs_and_question_links(self):
        topic, bank = load_topic("review"), load_variants("review")
        roles = ("scene", "tension", "choice", "reflection")
        groups = {g["id"]: g for g in topic["questionGroups"]}
        for seed, story in archived_review_coverage():
            evidence = story["narrativeEvidence"]
            link = evidence["selectionBasis"]["questionLink"]
            self.assertNotEqual(*link["angles"])
            for position, offset in enumerate((0, 4)):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertIn(row, groups[link["id"]]["angles"][link["angles"][position]])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4], [f"review:{r}:{row}" for r in roles])
                values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                          story["items"][position], story["summary"] if position == 0 else story["insight"])
                for role, text in zip(roles, values):
                    fragment = f"review:{role}:{row}"
                    options = [topic[role][row], *bank["rows"][row][role]]
                    self.assertEqual(text, express(options[evidence["paragraphVariants"][fragment]], seed, fragment))

    def test_help_nouns_are_not_expanded_into_awkward_verb_phrases(self):
        source = "翻到一条求助消息和一份求助记录，查看求助信息、求助电话、求助信与求助渠道，尊重求助者。"
        for index in range(128):
            self.assertEqual(express(source, str(index), "help-nouns"), source)
        variants = {express("向朋友求助。", str(index), "help-verb") for index in range(128)}
        self.assertGreater(len(variants), 1)
        self.assertIn("向朋友请求支持。", variants)

    def test_memory_review_actions_allow_both_photos_and_site_observations(self):
        topic = load_topic("review")
        variants = load_variants("review")["rows"][112]
        # Every choice can follow every scene: no mandatory trip or invented evidence.
        choices = [topic["choice"][112], *variants["choice"]]
        self.assertEqual(len(choices), 4)
        for choice in choices:
            self.assertNotIn("重访一处旧地时", choice)
            self.assertNotIn("现场变化", choice)
            self.assertTrue(any(word in choice for word in ("材料", "证据", "凭证")))
            self.assertTrue(any(word in choice for word in ("留空", "疑问", "未知")))
        self.assertIn("受限区域", choices[-1])

    def test_expression_does_not_add_nested_attributive_markers(self):
        for index in range(128):
            source = "写出影响目标的具体问题，核对合作的具体条件，也听听对方的具体需要。"
            actual = express(source, str(index), "attributive-grammar")
            self.assertIn("影响目标的具体问题", actual)
            self.assertIn("对方的具体需要", actual)
            self.assertNotIn("的明确的", actual)
            self.assertNotIn("的眼前的", actual)
            self.assertTrue("合作的具体条件" in actual or "合作的实际条件" in actual)
        variants = {express("具体问题", str(index), "plain-noun") for index in range(128)}
        self.assertEqual(variants, {"具体问题", "明确的问题"})

    def test_revised_support_and_changed_arrangement_sentences_stay_grammatical(self):
        support = load_topic("wellbeing")["choice"][87]
        arrangement = load_variants("wealth")["rows"][31]["choice"][0]
        self.assertIn("对方遇到了什么困难", support)
        self.assertIn("旧安排哪里不再合适", arrangement)
        for index in range(128):
            for source in (support, arrangement):
                actual = express(source, str(index), "revised-grammar")
                self.assertNotIn("在困难什么", actual)
                self.assertNotIn("不适合的明确的条件", actual)
                self.assertNotIn("不适合的具体条件", actual)

    def test_six_percent_gate_is_strict_and_disclosed(self):
        self.assertEqual(TARGET, .06)
        sections = [{"summary": "一份完整而清楚的生活场景说明"}]
        with patch("narrative_diversity.jaccard", return_value=.059999):
            result = validate_draft(sections, ["另一份完整生活场景说明"])
            self.assertEqual(result["threshold"], .06)
        with patch("narrative_diversity.jaccard", return_value=.06):
            with self.assertRaises(NarrativeDiversityError):
                validate_draft(sections, ["另一份完整生活场景说明"])

    def test_similarity_cardinality_count_matches_original_set_formula(self):
        texts = ("", "短", "日常安排值得认真照顾", "日常安排值得适时调整",
                 "重复重复重复重复重复", "完整解释应当保留事实边界与实际条件" * 80)
        for width in (1, 5, 7, 30):
            for a in texts:
                for b in texts:
                    left = {a[i:i + width] for i in range(max(0, len(a) - width + 1))}
                    right = {b[i:i + width] for i in range(max(0, len(b) - width + 1))}
                    expected = len(left & right) / len(left | right) if left or right else 1.0
                    report_a = {"sections": [{"summary": a}]}
                    report_b = {"sections": [{"summary": b}]}
                    self.assertEqual(narrative_similarity(report_a, report_b, width), expected)

    def test_family_classification_does_not_count_rob_wealth_as_wealth(self):
        self.assertEqual(_ten_god_axis(["劫财"], exact=True)[0], "自主驱动")
        self.assertEqual(_ten_god_axis(["正印", "偏印", "正财"], exact=True)[0], "学习内化")
        self.assertEqual(_ten_god_axis(["正印", "正财"], exact=True)[0], "综合承接")

    def test_audit_never_changes_the_canonical_draft(self):
        repeated = [{"summary": "生活场景需要认真观察，不因为一句动听的话就放弃自主选择。"}]
        different = [{"summary": "下周整理书桌，归还借来的物品，把空余的星期天下午留给散步。"}]
        before = body_text(different)
        audit = validate_draft(different, [body_text(repeated)])
        self.assertEqual(body_text(different), before)
        self.assertEqual(audit["draftRevision"], 0)
        self.assertEqual(audit["attempts"], 1)
        self.assertEqual(audit["generationPolicy"], "input_deterministic_history_audit_only")
        self.assertLess(audit["maxSimilarity"], TARGET)
        with self.assertRaises(NarrativeDiversityError):
            validate_draft(repeated, [body_text(repeated)])

    def test_story_rows_are_complete_coherent_units(self):
        applicability = load_applicability()
        self.assertEqual(set(applicability["topics"]), {path.stem for path in TOPICS.glob("*.json")})
        for path in sorted(TOPICS.glob("*.json")):
            topic = load_topic(path.stem)
            variants = load_variants(path.stem)
            expected = {"relationships": 143, "turning-points": 128, "wealth": 128,
                        "portrait": 96, "character": 160, "review": 182, "actions": 96, "career": 128, "structure": 180, "wellbeing": 128}.get(path.stem, 32)
            self.assertEqual({len(topic[role]) for role in ("scene", "tension", "choice", "reflection")}, {expected})
            for role in ("scene", "tension", "choice", "reflection"):
                self.assertEqual(len(set(topic[role])), expected)
            if variants:
                self.assertEqual(len(variants["rows"]), len(topic["scene"]))
                for row, versions in enumerate(variants["rows"]):
                    self.assertTrue(set(versions).issubset({"scene", "tension", "choice", "reflection"}))
                    for role, options in versions.items():
                        single = (path.stem in {"character", "relationships", "turning-points"}
                                  or (path.stem == "review" and row < 64)
                                  or (path.stem in {"structure", "wealth", "wellbeing"} and row >= 32)
                                  or (path.stem in {"wealth", "structure"} and role in {"choice", "reflection"}))
                        if (path.stem == "structure" and row >= 96) or path.stem == "wellbeing":
                            single = False
                        if (path.stem == "character" and row >= 32) or (path.stem == "wealth" and row >= 32):
                            single = False
                        if path.stem == "relationships" and (row < 64 or row >= 96):
                            single = False
                        if (path.stem == "review" and 32 <= row < 64) or (path.stem == "turning-points" and row >= 64):
                            single = False
                        alternatives = 1 if single else 2
                        if (path.stem == "review" and row >= 64) or (path.stem == "actions" and (row < 32 or row >= 80)):
                            alternatives = 3
                        if path.stem == "review" and row >= 178:
                            alternatives = 1
                        if (path.stem == "portrait" and row >= 32) or (path.stem == "career" and 32 <= row < 64):
                            alternatives = 3
                        if path.stem == "wealth" and row < 32:
                            alternatives = 3 if role in {"scene", "tension"} else 2
                        if path.stem == "character" and (32 <= row < 64 or 96 <= row < 128):
                            alternatives = 3
                        expanded_rows = {
                            ("structure", 67): 3,
                            ("review", 88): 5,
                            ("relationships", 103): 4,
                            ("portrait", 70): 5,
                            ("career", 104): 4,
                            ("review", 116): 5,
                            ("character", 86): 4,
                            ("turning-points", 87): 4,
                            ("career", 74): 4,
                            ("character", 77): 4,
                            ("character", 124): 5,
                            ("actions", 66): 4,
                            ("wellbeing", 95): 4,
                            ("wellbeing", 109): 4,
                            ("wellbeing", 124): 4,
                            ("relationships", 54): 4,
                            ("character", 91): 6,
                            ("review", 53): 4,
                            ("wellbeing", 48): 4,
                            ("turning-points", 86): 4,
                            ("character", 118): 5,
                            ("character", 151): 4,
                            ("review", 104): 5,
                            ("career", 51): 5,
                            ("structure", 32): 4,
                            ("structure", 41): 3,
                            ("structure", 145): 4,
                            ("turning-points", 121): 4,
                            ("portrait", 21): 4,
                            ("portrait", 27): 4,
                            ("portrait", 41): 5,
                            ("portrait", 45): 5,
                            ("portrait", 51): 5,
                            ("portrait", 55): 5,
                            ("portrait", 56): 5,
                            ("portrait", 60): 5,
                            ("wellbeing", 50): 4,
                            ("structure", 150): 4,
                        }
                        alternatives = expanded_rows.get((path.stem, row), alternatives)
                        if path.stem == "structure" and 64 <= row < 96:
                            alternatives += 2
                        alternatives = max(alternatives, len(options))
                        self.assertEqual(len(options), alternatives)
                        self.assertEqual(len({topic[role][row], *options}), alternatives + 1)
                        self.assertTrue(all(len(option) > 20 for option in options))
            tags = applicability["topics"][path.stem]
            self.assertEqual(len(tags), len(topic["scene"]))
            for row in tags:
                self.assertTrue(row)
                self.assertEqual(len(set(row)), len(row))
                self.assertTrue(set(row).issubset(applicability["axes"].values()))
            for axis, tag in applicability["axes"].items():
                self.assertTrue(any(tag in row for row in tags), f"{path.stem}: {axis} has no applicable example")
            context = {"id": path.stem, "title": "测试", "evidence": "依据", "counter": "条件", "core": "观察", "tension": "待核实"}
            story = render_story("frozen-seed", context)
            ids = story["narrativeEvidence"]["fragmentIds"]
            rows = [int(ids[index].rsplit(":", 1)[1]) for index in (0, 4)]
            for position, row in enumerate(rows):
                for role, actual in (("scene", story["scenes"][2 * position]),
                                     ("tension", story["scenes"][2 * position + 1]),
                                     ("choice", story["items"][position]),
                                     ("reflection", story["summary"] if position == 0 else story["insight"])):
                    fragment_id = f"{path.stem}:{role}:{row}"
                    options = [topic[role][row], *(variants["rows"][row].get(role, []) if variants else [])]
                    chosen = story["narrativeEvidence"]["paragraphVariants"][fragment_id]
                    self.assertEqual(actual, express(options[chosen], "frozen-seed", fragment_id))

    def test_appended_wordings_never_switch_between_existing_options(self):
        transitions = set()
        for path in sorted(TOPICS.glob("*.json")):
            bank = load_variants(path.stem)
            for extra_count in (1, 2):
                expanded = deepcopy(bank)
                for row in expanded["rows"]:
                    for role in ("scene", "tension", "choice", "reflection"):
                        row[role].extend(f"新增验收表达{index}，仅用于测试选择稳定性，不代表实际资料。"
                                         for index in range(extra_count))
                for axis in (*load_applicability()["axes"], "综合承接"):
                    context = {"id": path.stem, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                               "core": "生活观察", "tension": "测试情境", "axisDrive": axis}
                    for index in range(24):
                        seed = f"append-stability-{index}"
                        before = render_story(seed, context)["narrativeEvidence"]
                        self.assertEqual(before["paragraphSelectionVersion"], "append-only-rendezvous-v1")
                        with patch("story_narrative.load_variants", return_value=expanded):
                            after = render_story(seed, context)["narrativeEvidence"]
                        self.assertEqual(before["fragmentIds"], after["fragmentIds"])
                        self.assertEqual(before["selectionBasis"], after["selectionBasis"])
                        for fragment, previous in before["paragraphVariants"].items():
                            _, role, row = fragment.split(":")
                            original_count = 1 + len(bank["rows"][int(row)][role])
                            current = after["paragraphVariants"][fragment]
                            self.assertIn(current, {previous, *range(original_count, original_count + extra_count)},
                                          (path.stem, axis, seed, fragment, previous, current))
                            transitions.add("retained" if current == previous else "appended")
        self.assertEqual(transitions, {"retained", "appended"})

    def test_appending_one_role_leaves_other_prose_unchanged(self):
        context = {"id": "career", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                   "core": "生活观察", "tension": "测试情境", "axisDrive": "学习内化"}
        bank = load_variants("career")
        for index in range(80):
            seed = f"single-role-append-{index}"
            before = render_story(seed, context)
            evidence = before["narrativeEvidence"]
            row = int(evidence["fragmentIds"][0].rsplit(":", 1)[1])
            expanded = deepcopy(bank)
            expanded["rows"][row]["scene"].append("这是一段只供验收选择机制使用的新增处境，不是实际生活经历。")
            with patch("story_narrative.load_variants", return_value=expanded):
                after = render_story(seed, context)
            self.assertEqual(before["scenes"][1:], after["scenes"][1:])
            for key in ("summary", "insight", "items"):
                self.assertEqual(before[key], after[key])
            target = f"career:scene:{row}"
            self.assertEqual(evidence["fragmentIds"], after["narrativeEvidence"]["fragmentIds"])
            for fragment, previous in evidence["paragraphVariants"].items():
                current = after["narrativeEvidence"]["paragraphVariants"][fragment]
                if fragment == target:
                    self.assertIn(current, {previous, 1 + len(bank["rows"][row]["scene"])})
                else:
                    self.assertEqual(current, previous)

    def test_paragraph_rewording_keeps_original_fragment_identity(self):
        context = {"id": "structure", "title": "测试", "evidence": "依据", "counter": "条件", "core": "观察", "tension": "待核实"}
        chosen = set()
        for index in range(30):
            story = render_story(str(index), context)
            evidence = story["narrativeEvidence"]
            self.assertEqual(set(evidence["paragraphVariants"]), set(evidence["fragmentIds"]))
            self.assertEqual(len(evidence["fragmentIds"]), 8)
            for fragment, version in evidence["paragraphVariants"].items():
                if ":scene:" in fragment or ":tension:" in fragment:
                    chosen.add(version)
                else:
                    row = int(fragment.rsplit(":", 1)[1])
                    role = fragment.split(":")[1]
                    self.assertIn(version, range(len(load_variants("structure")["rows"][row][role]) + 1))
        self.assertTrue({0, 1, 2} <= chosen <= {0, 1, 2, 3, 4})

    def test_expanded_stories_are_reachable_with_complete_original_arcs(self):
        for topic in ("character", "relationships", "review", "turning-points", "actions"):
            seen = set()
            for axis in load_applicability()["axes"]:
                context = {"id": topic, "title": "测试", "evidence": "依据", "counter": "条件",
                           "core": "观察", "tension": "待核实", "axisDrive": axis}
                for index in range(240):
                    story = render_story(f"coverage-{index}", context)
                    ids = story["narrativeEvidence"]["fragmentIds"]
                    for offset in (0, 4):
                        row = int(ids[offset].rsplit(":", 1)[1])
                        seen.add(row)
                        self.assertEqual(ids[offset:offset + 4],
                                         [f"{topic}:{role}:{row}" for role in ("scene", "tension", "choice", "reflection")])
            if topic == "review":
                seen.update(int(s["narrativeEvidence"]["fragmentIds"][4].rsplit(":", 1)[1])
                            for _, s in archived_review_coverage())
            self.assertEqual(seen & set(range(32, 64)), set(range(32, 64)))

    def test_generic_turning_examples_do_not_require_retirement_or_parenthood(self):
        topic = load_topic("turning-points")
        for row in (32, 39, 41, 57):
            for role in ("scene", "tension", "choice", "reflection"):
                self.assertNotIn("退休", topic[role][row])
                self.assertNotIn("孩子", topic[role][row])
        self.assertIn("固定职责", topic["scene"][39])
        self.assertIn("共同任务", topic["tension"][57])

    def test_expanded_topics_are_reachable_as_whole_arcs(self):
        for topic, count in (("relationships", 143), ("turning-points", 128), ("wealth", 128), ("portrait", 96), ("career", 128), ("structure", 180), ("actions", 96), ("wellbeing", 128), ("character", 160), ("review", 182)):
            seen = set()
            for axis in load_applicability()["axes"]:
                context = {"id": topic, "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                           "core": "生活观察", "tension": "不是既有经历", "axisDrive": axis}
                for index in range(600):
                    story = render_story(f"expanded-topic-{index}", context)
                    ids = story["narrativeEvidence"]["fragmentIds"]
                    for offset in (0, 4):
                        row = int(ids[offset].rsplit(":", 1)[1])
                        seen.add(row)
                        self.assertEqual(ids[offset:offset + 4],
                                         [f"{topic}:{role}:{row}" for role in ("scene", "tension", "choice", "reflection")])
            if topic == "review":
                self.assertEqual(seen, set(range(64, count)))
            else:
                self.assertEqual(seen, set(range(count)))

    def test_full_role_variants_keep_original_arcs_and_expose_all_choices(self):
        roles = ("scene", "tension", "choice", "reflection")
        for topic, choices in (("wellbeing", None), ("review", None), ("actions", {0, 1, 2, 3, 4}), ("character", None), ("relationships", None), ("turning-points", None)):
            with self.subTest(topic=topic):
                for row in load_variants(topic)["rows"]:
                    self.assertEqual(set(row), set(roles))
                selected = {role: set() for role in roles}
                context = {"id": topic, "title": "测试", "evidence": "文化解释", "counter": "需现实核对",
                           "core": "生活观察", "tension": "保留事实边界", "axisDrive": "规则责任"}
                for index in range(60):
                    story = render_story(f"{topic}-coverage-{index}", context)
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(story["narrativeVoice"], "双场景对照")
                    variant_version = {"character": 16, "review": 18, "actions": 6, "wellbeing": 13, "relationships": 10, "turning-points": 8}[topic]
                    self.assertEqual(evidence["paragraphVariantVersion"], f"{topic}-paragraph-variants-v{variant_version}")
                    for offset in (0, 4):
                        row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                        self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                         [f"{topic}:{role}:{row}" for role in roles])
                        for role in roles:
                            selected[role].add(evidence["paragraphVariants"][f"{topic}:{role}:{row}"])
                if choices is None:
                    choices = set().union(*(variant_options(topic, row, role) for row, variant_row in enumerate(load_variants(topic)["rows"]) for role in roles))
                for values in selected.values():
                    self.assertTrue(values.issubset(choices))
                    self.assertIn(0, values)

    def test_review_uses_practical_arcs_in_both_positions(self):
        topic = load_topic("review")
        bank = load_variants("review")
        roles = ("scene", "tension", "choice", "reflection")
        self.assertEqual(topic["version"], 10)
        self.assertEqual(topic["entryRows"], list(range(64, 182)))
        self.assertEqual(topic["secondaryRows"], list(range(64, 182)))
        self.assertEqual(bank["version"], "review-paragraph-variants-v18")
        for role in roles:
            self.assertEqual(len({row[role][0] for row in bank["rows"][64:]}), 118)
        self.assertIn("不自行拆试", topic["choice"][73])
        self.assertIn("不勉强继续有害接触", topic["choice"][77])
        self.assertIn("不擅自丢弃", bank["rows"][83]["choice"][0])
        self.assertIn("不擅自删减必要的安全措施", topic["choice"][86])
        self.assertIn("不临时改成功标准", topic["choice"][95])
        self.assertIn("不催促对方恢复原样", topic["choice"][98])
        self.assertIn("未经授权的私人信息", topic["choice"][117])
        self.assertIn("不追问无关隐私", bank["rows"][125]["choice"][0])
        self.assertIn("不继续自我审判", topic["choice"][127])
        selected = {role: set() for role in roles}
        first_seen, old_second_seen = set(), set()
        for axis in [*load_applicability()["axes"], "综合承接"]:
            context = {"id": "review", "title": "旧标题", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "不是已知经历", "axisDrive": axis}
            for index in range(600):
                seed = f"review-practical-{index}"
                story = render_story(seed, context)
                evidence = story["narrativeEvidence"]
                basis = evidence["selectionBasis"]
                first, second = (int(evidence["fragmentIds"][i].rsplit(":", 1)[1]) for i in (0, 4))
                self.assertEqual(story["title"], next(group["title"] for group in topic["questionGroups"]
                                                      if group["id"] == basis["questionLink"]["id"]))
                self.assertTrue(basis["entryRestricted"])
                self.assertEqual(basis["entryScope"], topic["entryScope"])
                self.assertGreaterEqual(first, 64)
                self.assertGreaterEqual(second, 64)
                self.assertTrue(basis["secondaryRestricted"])
                self.assertEqual(basis["secondaryScope"], topic["secondaryScope"])
                self.assertNotEqual(first, second)
                first_seen.add(first)
                if second < 64:
                    old_second_seen.add(second)
                if basis["axisTag"] is not None:
                    self.assertIn(basis["axisTag"], basis["selectedTags"][0])
                self.assertEqual(basis["counterAxisApplied"],
                                 basis["counterTag"] is not None and basis["counterTag"] in basis["selectedTags"][1])
                self.assertEqual(story, render_story(seed, context))
                for role in roles:
                    selected[role].add(evidence["paragraphVariants"][f"review:{role}:{first}"])
        self.assertEqual(first_seen, set(range(64, 182)))
        self.assertFalse(old_second_seen)
        for key, versions in selected.items():
            expected = set().union(*(variant_options("review", row, key) for row in range(64, 182)))
            self.assertTrue(versions.issubset(expected), key)
            self.assertIn(0, versions, key)

    def test_practical_review_wordings_preserve_roles_and_boundaries(self):
        roles = ("scene", "tension", "choice", "reflection")
        topic, bank = load_topic("review"), load_variants("review")
        boundaries = {64: "补救", 66: "食品安全", 67: "安全", 69: "低风险", 70: "受影响",
                      71: "不以补做加倍", 72: "不要求展示使用", 73: "停止自行拆试", 74: "不要求",
                      75: "安全", 76: "核对", 77: "安全且自愿", 78: "安全", 80: "不替别人",
                      81: "意愿", 82: "安全通道", 83: "物主同意", 84: "保留必要安全",
                      85: "不靠猜测", 86: "不擅自取消必要安全", 87: "负责人", 88: "专业帮助",
                      89: "必要职责", 90: "不只取有利片段", 91: "尊重明确边界", 93: "实际责任",
                      95: "原先成功标准", 96: "屏蔽或离开", 98: "不催促立即原谅",
                      99: "不以临时消失", 100: "不用催促", 102: "不要求无限承接",
                      103: "不把旧经验直接当作新机会保证", 105: "不为维持展示效果勉强身体",
                      106: "承诺先沟通", 108: "必要边界", 109: "专业支持", 110: "紧急风险",
                      111: "低风险", 112: "不用猜测", 113: "不试验危险情境", 114: "不把全部责任",
                      115: "及时更正", 116: "医疗帮助", 117: "未经授权的私人信息",
                      118: "明确结束", 119: "真实限制", 120: "不替他人推定动机", 121: "意愿",
                      122: "支持", 123: "必要标准", 124: "真实新条件", 125: "不追问无关隐私",
                      126: "不虚构", 127: "停止反复自我审判"}
        for row, phrase in boundaries.items():
            self.assertIn(phrase, "".join(bank["rows"][row][role][1] for role in roles), row)
        for role in roles:
            self.assertEqual(len({row[role][1] for row in bank["rows"][64:128]}), 64)
        selected = {(row, role): set() for row in range(64, 128) for role in roles}
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "review", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "编辑情境而非既有经历", "axisDrive": axis}
            for index in range(1200):
                seed = f"review-three-wordings-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"review:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"review:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        if 64 <= row < 128:
                            selected[row, role].add(version)
                        elif row >= 128:
                            self.assertIn(version, variant_options("review", row, role))
                        else:
                            self.assertIn(version, variant_options("review", row, role))
        for key, versions in selected.items():
            expected = variant_options("review", key[0], key[1])
            self.assertEqual(versions, expected, key)

    def test_review_fourth_wording_preserves_specific_boundaries(self):
        rows = load_variants("review")["rows"]
        boundaries = {
            96: "屏蔽或离开", 97: "不靠更生僻", 98: "不要求立即原谅", 99: "不用突然消失",
            100: "强迫", 101: "全部动机", 102: "不要求对方无限承接", 103: "新机会的保证",
            104: "不虚构成绩", 105: "不为维持展示效果勉强身体", 106: "既有承诺先沟通",
            107: "不可替代", 108: "必要边界", 109: "专业支持", 110: "紧急风险",
            111: "低风险", 112: "不靠猜测补齐过去", 113: "不试验危险情境",
            114: "不把所有影响都归咎于自己", 115: "不擅自删除他人记录",
            116: "不用命理作诊断", 117: "未经授权的私人信息", 118: "明确结束",
            119: "不把想象中的唯一结局当成已经发生的事实", 120: "不替他人推定动机",
            121: "双方意愿", 122: "合适支持", 123: "必要标准", 124: "真实新条件",
            125: "不代替未回应者编造意见", 126: "不虚构里程碑", 127: "停止反复自我审判",
        }
        self.assertEqual(set(boundaries), set(range(96, 128)))
        for row, phrase in boundaries.items():
            self.assertIn(phrase, rows[row]["choice"][2], row)
            for role in ("scene", "tension", "choice", "reflection"):
                expected_len = len(rows[row][role])
                self.assertGreaterEqual(expected_len, 3)
                self.assertEqual(len(rows[row][role]), expected_len)

    def test_structure_everyday_arcs_keep_all_wordings_and_practical_limits(self):
        topic, bank = load_topic("structure"), load_variants("structure")
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            128: ("共用空间先征求同意", "使用共有位置征求同意"),
            129: ("遵守场馆规则", "尊重现场规则"),
            130: ("未经授权", "未经许可"),
            131: ("不追问无关健康隐私", "不擅自判断"),
            132: ("允许提问或退出", "不用起哄逼人"),
            133: ("不勉强自行搬动", "危险搬运交给"),
            134: ("无授权的位置", "存放许可"),
            135: ("未知日期留空", "不猜定未知日期"),
            136: ("未获许可", "不擅自公开"),
            137: ("食品安全", "食品安全"),
            138: ("不公开未经同意", "未经同意的分享不外传"),
            139: ("不擅自替大家取消", "不因个人偏好擅自变更"),
            140: ("不以练习需要", "不把他人休息视为"),
            141: ("紧急安全", "紧急安全"),
            142: ("不公开接收者隐私", "保护相关人的隐私"),
            143: ("超出授权", "权限或安全"),
            144: ("不擅自失联", "有变化及时告知"),
            145: ("可靠运输说明", "运输限制"),
            146: ("录音前取得相关同意", "录制许可"),
            147: ("不替别人关闭账号", "不操作他人的账号"),
            148: ("危险工具", "高风险工具不凭猜测操作"),
            149: ("不用羞辱", "不拿失误给人贴标签"),
            150: ("不隐去他人贡献", "不把团队成果全记"),
            151: ("不虚构赞同人数", "不把沉默计成赞成"),
            152: ("不冒用身份", "不利用虚假身份"),
            153: ("不把他人的私人地址随意公开", "私人地址不擅自转发"),
            154: ("私人物品不擅自翻动", "不擅自挪动私人资料"),
            155: ("不用练习替代必要指导", "不自行突破安全要求"),
            156: ("需要交接的先说明", "合作先沟通"),
            157: ("不擅自永久改动", "不以试试看为由擅自"),
            158: ("不以仪式承诺转运", "不把象征性仪式"),
            159: ("不追问无关身体隐私", "不要求披露无关隐私"),
        }
        self.assertEqual(set(boundaries), set(range(128, 160)))
        for row, phrases in boundaries.items():
            for version, phrase in enumerate(phrases):
                actual = topic["choice"][row] if version == 0 else bank["rows"][row]["choice"][0]
                self.assertIn(phrase, actual, (row, version))
        reached = {(row, role): set() for row in range(128, 180) for role in roles}
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "structure", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "假设情境而非已知经历", "axisDrive": axis}
            for index in range(600):
                seed = f"structure-everyday-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if row < 128:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"structure:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"structure:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        reached[row, role].add(version)
        for target in range(128, 180):
            focused = deepcopy(topic)
            focused["entryRows"] = [target]
            with patch("story_narrative.load_topic", return_value=focused):
                for index in range(64):
                    seed = f"structure-everyday-direct-{target}-{index}"
                    story = render_story(seed, context)
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(evidence["fragmentIds"][0], f"structure:scene:{target}")
                    values = (*story["scenes"][:2], story["items"][0], story["summary"])
                    for role, actual in zip(roles, values):
                        fragment = f"structure:{role}:{target}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][target], *bank["rows"][target][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        reached[target, role].add(version)
        for key, values in reached.items():
            expected = variant_options("structure", key[0], key[1])
            self.assertEqual(values, expected, key)

    def test_practical_entry_restriction_preserves_tags_and_unclassified_fallback(self):
        roles = ("scene", "tension", "choice", "reflection")
        topic = {role: [f"旧情境{role}", f"新情境一{role}", f"新情境二{role}"] for role in roles}
        topic.update(entryRows=[1, 2], entryScope="生活情境", title="生活复盘")
        applicability = {"version": "test-v1", "axes": {"自主驱动": "A", "规则责任": "O"},
                         "topics": {"review": [["A"], ["O"], ["A"]]}}
        context = {"id": "review", "title": "原标题", "evidence": "依据", "counter": "条件",
                   "core": "观察", "tension": "待核实", "axisDrive": "自主驱动"}
        with patch("story_narrative.load_topic", return_value=topic), \
                patch("story_narrative.load_variants", return_value={}), \
                patch("story_narrative.load_applicability", return_value=applicability):
            story = render_story("entry-test", context)
            self.assertEqual(story["narrativeEvidence"]["fragmentIds"][0], "review:scene:2")
            self.assertEqual(story["narrativeEvidence"]["fragmentIds"][4], "review:scene:1")
            for axis in ("综合承接", "自主驱动"):
                applicability["topics"]["review"][2] = ["O"]
                context["axisDrive"] = axis
                for index in range(10):
                    story = render_story(str(index), context)
                    self.assertIn(story["narrativeEvidence"]["fragmentIds"][0],
                                  {"review:scene:1", "review:scene:2"})
            del topic["entryRows"]
            del topic["title"]
            story = render_story("entry-test", context)
            self.assertFalse(story["narrativeEvidence"]["selectionBasis"]["entryRestricted"])
            self.assertEqual(story["title"], "原标题")
            self.assertEqual(story["narrativeEvidence"]["fragmentIds"][0], "review:scene:0")

    def test_expanded_wellbeing_keeps_whole_arcs_and_practical_boundaries(self):
        topic = load_topic("wellbeing")
        bank = load_variants("wellbeing")
        roles = ("scene", "tension", "choice", "reflection")
        self.assertEqual(topic["version"], 4)
        self.assertEqual(bank["version"], "wellbeing-paragraph-variants-v13")
        self.assertEqual(len(bank["rows"]), 128)
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), set(roles))
            expected_len = 4 if index in {48, 50, 95, 109, 124} else (3 if index in {12, 62, 75} else 2)
            self.assertEqual({len(values) for values in row.values()}, {expected_len})
        for role in roles:
            self.assertEqual(len({row[role][0] for row in bank["rows"][32:]}), 96)
        self.assertIn("不应被当成对任何身体问题的诊断或处理", topic["tension"][43])
        self.assertIn("不必接管自我感受", topic["reflection"][61])
        self.assertIn("不用曲线推断病因", bank["rows"][61]["choice"][0])
        self.assertIn("不擅自中断必要职责", topic["choice"][65])
        self.assertIn("完成必要交接", bank["rows"][65]["choice"][0])
        self.assertIn("不在行车中操作手机", topic["choice"][90])
        self.assertIn("安全条件下", bank["rows"][90]["choice"][0])
        selected = {(band, role): set() for band in ("legacy", "expanded") for role in roles}
        context = {"id": "wellbeing", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "规则责任"}
        for index in range(240):
            story = render_story(f"wellbeing-expanded-{index}", context)
            evidence = story["narrativeEvidence"]
            self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"wellbeing:{role}:{row}" for role in roles])
                for role in roles:
                    selected[("legacy" if row < 64 else "expanded", role)].add(
                        evidence["paragraphVariants"][f"wellbeing:{role}:{row}"])
        for (band, role), values in selected.items():
            expected = set().union(*(variant_options("wellbeing", row, role) for row in range(64 if band == "expanded" else 0, 128 if band == "expanded" else 64)))
            self.assertTrue(values.issubset(expected))
            self.assertIn(0, values)

    def test_new_wellbeing_arcs_reach_every_role_and_keep_specific_boundaries(self):
        topic, bank = load_topic("wellbeing"), load_variants("wellbeing")
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            96: ("征得同意", "如期还书"), 97: ("安全", "他人的感受"),
            98: ("自动播放", "自动播放"), 99: ("安全", "安全"),
            100: ("预算", "不为展示"), 101: ("播放前", "协商"),
            102: ("不在行车中", "不边开车"), 103: ("不因倒计时", "不被限时"),
            104: ("不为补出", "不为修补"), 105: ("不追查", "不追踪"),
            106: ("预算", "预算"), 107: ("安全", "安全"),
            108: ("隐私", "私人内容"), 109: ("必要事务", "必要事项"),
            110: ("不擅自", "不自行"), 111: ("先商量", "协商"),
            112: ("保留拒绝", "保留不参加"), 113: ("可信", "可信"),
            114: ("不凭一时情绪", "不把心情起伏当作预兆"),
            115: ("不连续追问", "不用连发消息"),
            116: ("紧急联系", "急事能联系"), 117: ("不装作", "不以越过边界"),
            118: ("安全", "安全"), 119: ("不当场答应", "不仓促承诺"),
            120: ("必要职责", "应承担"), 121: ("不擅闯", "隐私边界"),
            122: ("预算", "不为追赶旧体验超支"),
            123: ("不赋予", "不把卡片"), 124: ("不随意混用", "不乱用"),
            125: ("安全", "安全"), 126: ("不擅自离队", "不私自脱队"),
            127: ("必要支持", "必要的沟通与支持"),
        }
        for row, (original, alternate) in boundaries.items():
            self.assertIn(original, topic["choice"][row])
            self.assertIn(alternate, bank["rows"][row]["choice"][0])
        selected = {(row, role): set() for row in range(96, 128) for role in roles}
        for axis in (*load_applicability()["axes"], None):
            context = {"id": "wellbeing", "title": "测试", "evidence": "文化解释", "counter": "核对实际条件",
                       "core": "生活观察", "tension": "不是既有经历", "axisDrive": axis}
            for index in range(1200):
                seed = f"wellbeing-new-life-{index}"
                story = render_story(seed, context)
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if row < 96:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"wellbeing:{role}:{row}" for role in roles])
                    values = (story["scenes"][2 * position], story["scenes"][2 * position + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"wellbeing:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        selected[row, role].add(version)
        for key, versions in selected.items():
            expected = variant_options("wellbeing", key[0], key[1])
            self.assertEqual(versions, expected, key)

    def test_points_reward_options_do_not_switch_to_coupons(self):
        topic, bank = load_topic("wealth"), load_variants("wealth")
        for role in ("scene", "tension", "choice", "reflection"):
            options = [topic[role][106], *bank["rows"][106][role]]
            self.assertEqual(len(options), 3)
            for text in options:
                self.assertNotIn("券", text)
            if role == "scene":
                self.assertTrue(all("积分" in text for text in options))
        self.assertIn("不为不需要", topic["choice"][106])
        self.assertTrue(all("不把待兑换奖励" in text for text in bank["rows"][106]["choice"]))

    def test_character_expansion_preserves_complete_arcs_and_personal_boundaries(self):
        topic = load_topic("character")
        bank = load_variants("character")
        roles = ("scene", "tension", "choice", "reflection")
        self.assertEqual(topic["version"], 4)
        self.assertEqual(bank["version"], "character-paragraph-variants-v16")
        self.assertEqual(len(bank["rows"]), 160)
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), set(roles))
            if index == 91:
                expected_len = 6
            elif index in {118, 124}:
                expected_len = 5
            elif index in {77, 86, 151}:
                expected_len = 4
            else:
                expected_len = 3 if 32 <= index < 64 or 96 <= index < 128 else 2 if index >= 64 else 1
                if index in {34, 67, 87}:
                    expected_len += 1
            self.assertTrue(all(len(row[role]) == expected_len for role in roles))
        for role in roles:
            self.assertEqual(len({row[role][0] for row in bank["rows"][64:]}), 96)
        self.assertIn("明确授权", topic["choice"][96])
        self.assertIn("征求当事人同意", topic["choice"][96])
        self.assertIn("现实支持", bank["rows"][106]["choice"][0])
        self.assertIn("不安全", topic["choice"][125])
        self.assertIn("保留拒绝的权利", bank["rows"][125]["choice"][0])
        selected = {role: set() for role in roles}
        context = {"id": "character", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "表达创造"}
        for index in range(240):
            story = render_story(f"character-expanded-{index}", context)
            evidence = story["narrativeEvidence"]
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"character:{role}:{row}" for role in roles])
                if row >= 64:
                    for role in roles:
                        selected[role].add(evidence["paragraphVariants"][f"character:{role}:{row}"])
        for versions in selected.values():
            self.assertTrue(versions.issubset(set().union(*(variant_options("character", row, role) for row in range(160)))))
            self.assertIn(0, versions)

    def test_character_new_wordings_cover_each_role_and_preserve_boundaries(self):
        topic, bank = load_topic("character"), load_variants("character")
        roles = ("scene", "tension", "choice", "reflection")
        rows = [*range(32, 64), *range(96, 128)]
        boundaries = {37: "重大不可逆", 42: "先征求同意", 50: "不当成事实传播",
                      58: "专业支持", 62: "重大、难逆", 96: "明确授权", 97: "隐私",
                      104: "专业支持", 105: "羞辱", 106: "胁迫", 107: "停止施压",
                      109: "不要求", 114: "核对", 117: "紧急危险", 119: "不", 120: "遮去隐私",
                      125: "拒绝权", 126: "不冒险操作"}
        for row, phrase in boundaries.items():
            self.assertIn(phrase, bank["rows"][row]["choice"][1], row)
        selected = {(row, role): set() for row in rows for role in roles}
        context = {"id": "character", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                   "core": "生活观察", "tension": "假设而非已知经历", "axisDrive": "综合承接"}
        for index in range(2400):
            seed = f"character-wording-v5-{index}"
            story = render_story(seed, context)
            self.assertEqual(story, render_story(seed, context))
            evidence = story["narrativeEvidence"]
            self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
            for position, offset in enumerate((0, 4)):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                if row not in rows:
                    continue
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"character:{role}:{row}" for role in roles])
                values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                          story["items"][position], story["summary"] if position == 0 else story["insight"])
                for role, actual in zip(roles, values):
                    fragment = f"character:{role}:{row}"
                    version = evidence["paragraphVariants"][fragment]
                    options = [topic[role][row], *bank["rows"][row][role]]
                    expected_count = len(options)
                    self.assertGreaterEqual(expected_count, 4)
                    self.assertEqual(len(set(options)), expected_count)
                    self.assertEqual(actual, express(options[version], seed, fragment))
                    selected[row, role].add(version)
        for key, versions in selected.items():
            expected = variant_options("character", key[0], key[1])
            self.assertEqual(versions, expected, key)

    def test_character_everyday_expansion_reaches_all_wordings_and_keeps_boundaries(self):
        topic, bank = load_topic("character"), load_variants("character")
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            128: ("未经同意", "征求本人同意"),
            129: ("不擅自转发", "不发布或合适遮挡"),
            130: ("不自行贴诊断标签", "寻找适当支持"),
            131: ("不擅自进入", "不打扰住户"),
            132: ("超出条件的承诺", "外部成绩"),
            133: ("拒绝的空间", "起哄换取配合"),
            134: ("不替过去编造", "保留原记录的真实样子"),
            135: ("超出条件的花费", "超出负担的承诺"),
            136: ("安全或规定", "安全与规定"),
            137: ("不为靠近体验触碰受限展品", "不违反场所规则"),
            138: ("不要求对方负责消除所有难过", "不勉强在不安全"),
            139: ("持续侵犯", "过去接受过并不等于"),
            140: ("妥善交接", "保护他人隐私"),
            141: ("不擅自处置", "擅自丢弃"),
            142: ("不据此作医疗、投资或其他重大决定", "不用巧合预测疾病"),
            143: ("不强迫", "不催促"),
            144: ("不嘲弄", "尊重别人"),
            145: ("可靠信息", "专业事项另作咨询"),
            146: ("不贬低第三人", "不以贬损别人反击"),
            147: ("明确约定", "不被恩情要求越过边界"),
            148: ("可承受", "实际条件"),
            149: ("不转述", "不借好奇追问"),
            150: ("尊重双方意愿", "征求意愿"),
            151: ("不为画面进入受限区域", "不以危险站位或侵犯隐私"),
            152: ("不强迫暴露隐私", "不靠编故事或透露私人细节"),
            153: ("提前说明并取得同意", "提前取得相关同意"),
            154: ("不盲目操作", "不擅自施加危险操作"),
            155: ("未获同意就保密", "不擅自转发私聊"),
            156: ("尊重现实责任", "不逃避已有责任"),
            157: ("不追赌", "不以追赌"),
            158: ("不催原谅", "不反复追问或绕过拒绝"),
            159: ("不隐瞒对外交付所需标准", "不把练习品包装成"),
        }
        self.assertEqual(set(boundaries), set(range(128, 160)))
        for row, phrases in boundaries.items():
            for version, phrase in enumerate(phrases):
                prose = "".join(topic[role][row] if version == 0 else bank["rows"][row][role][0]
                                for role in roles)
                self.assertIn(phrase, prose, (row, version))
        selected = {(row, role): set() for row in range(128, 160) for role in roles}
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "character", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "假设而非已知经历", "axisDrive": axis}
            for index in range(1200):
                seed = f"character-everyday-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                basis = evidence["selectionBasis"]
                self.assertNotEqual(*basis["familyContrast"]["selected"])
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if row < 128:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"character:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"character:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        selected[row, role].add(version)
        for key, versions in selected.items():
            expected = variant_options("character", key[0], key[1])
            self.assertEqual(versions, expected, key)

    def test_scene_families_are_complete_and_contrast_within_original_topic_pool(self):
        applicability = load_applicability()
        for topic_id, count in (("character", 160), ("wellbeing", 128), ("wealth", 128)):
            topic = load_topic(topic_id)
            version = 2 if topic_id in {"character", "wellbeing"} else 1
            self.assertEqual(topic["familyVersion"], f"{topic_id}-scene-families-v{version}")
            self.assertEqual(len(topic["families"]), count)
            self.assertTrue(all(isinstance(family, str) and family for family in topic["families"]))
            for axis in applicability["axes"]:
                context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                           "core": "生活观察", "tension": "不是既有经历", "axisDrive": axis}
                for index in range(120):
                    story = render_story(f"family-contrast-{index}", context)
                    evidence = story["narrativeEvidence"]
                    basis = evidence["selectionBasis"]
                    first, second = (int(evidence["fragmentIds"][i].rsplit(":", 1)[1]) for i in (0, 4))
                    contrast = basis["familyContrast"]
                    self.assertEqual(contrast["selected"], [topic["families"][i] for i in (first, second)])
                    self.assertTrue(contrast["applied"])
                    self.assertNotEqual(contrast["selected"][0], contrast["selected"][1])
                    self.assertIn(basis["axisTag"], basis["selectedTags"][0])
                    self.assertIn(basis["counterTag"], basis["selectedTags"][1])
                    self.assertEqual(story, render_story(f"family-contrast-{index}", context))

    def test_scene_family_fallback_preserves_topic_relevance_and_missing_metadata(self):
        roles = ("scene", "tension", "choice", "reflection")
        topic = {role: [f"情境一{role}", f"情境二{role}", f"情境三{role}"] for role in roles}
        topic.update(families=["shared", "shared", "different"], familyVersion="test-families-v1")
        applicability = {"version": "test-v1", "axes": {"自主驱动": "A", "规则责任": "O"},
                         "topics": {"character": [["A"], ["O"], ["O"]]}}
        context = {"id": "character", "title": "测试", "evidence": "依据", "counter": "条件",
                   "core": "观察", "tension": "待核实", "axisDrive": "自主驱动"}
        with patch("story_narrative.load_topic", return_value=topic), \
                patch("story_narrative.load_variants", return_value={}), \
                patch("story_narrative.load_applicability", return_value=applicability):
            story = render_story("family-fallback", context)
            self.assertEqual(story["narrativeEvidence"]["fragmentIds"][4], "character:scene:2")
            self.assertTrue(story["narrativeEvidence"]["selectionBasis"]["familyContrast"]["applied"])
            applicability["topics"]["character"][2] = ["L"]
            story = render_story("family-fallback", context)
            self.assertEqual(story["narrativeEvidence"]["fragmentIds"][4], "character:scene:1")
            self.assertFalse(story["narrativeEvidence"]["selectionBasis"]["familyContrast"]["applied"])
            del topic["families"]
            story = render_story("family-fallback", context)
            self.assertEqual(story["narrativeEvidence"]["fragmentIds"][4], "character:scene:1")
            self.assertEqual(story["narrativeEvidence"]["selectionBasis"]["familyContrast"]["selected"], [])

    def test_new_portrait_rewordings_preserve_advice_and_original_identity(self):
        bank = load_variants("portrait")
        self.assertEqual(bank["version"], "portrait-paragraph-variants-v13")
        self.assertEqual(len(bank["rows"]), 96)
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), {"scene", "tension", "choice", "reflection"})
            for role, options in row.items():
                expected = 5 if index in {41, 45, 51, 55, 56, 60, 70} else 4 if index in {21, 27} else 3 if index >= 32 else 2
                if index in {18, 52, 64, 65, 81}:
                    expected += 1
                self.assertEqual(len(options), expected)
        selected = {role: set() for role in ("scene", "tension", "choice", "reflection")}
        original = load_topic("portrait")
        context = {"id": "portrait", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "学习内化"}
        for index in range(120):
            story = render_story(f"portrait-variants-{index}", context)
            evidence = story["narrativeEvidence"]
            for position, offset in enumerate((0, 4)):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"portrait:{role}:{row}" for role in selected])
                for role in selected:
                    selected[role].add(evidence["paragraphVariants"][f"portrait:{role}:{row}"])
                for role, actual in (("choice", story["items"][position]),
                                     ("reflection", story["summary"] if position == 0 else story["insight"])):
                    fragment = f"portrait:{role}:{row}"
                    version = evidence["paragraphVariants"][fragment]
                    options = [original[role][row], *bank["rows"][row][role]]
                    self.assertEqual(actual, express(options[version], f"portrait-variants-{index}", fragment))
        for role, versions in selected.items():
            expected = set().union(*(variant_options("portrait", row, role) for row in range(96)))
            self.assertTrue({0, 1, 2, 3} <= versions <= expected)

    def test_portrait_expansion_keeps_learning_privacy_and_evidence_boundaries(self):
        topic = load_topic("portrait")
        bank = load_variants("portrait")
        roles = ("scene", "tension", "choice", "reflection")
        self.assertEqual(topic["version"], 7)
        for role in roles:
            self.assertEqual(len({row[role][0] for row in bank["rows"][64:]}), 32)
        self.assertIn("安全、可拆回", topic["tension"][65])
        self.assertIn("不必据此给自己定一种学习类型", bank["rows"][65]["tension"][0])
        self.assertIn("不能据此认定终身适用", bank["rows"][73]["tension"][0])
        self.assertIn("发布范围", topic["choice"][76])
        self.assertIn("不擅自转发", bank["rows"][76]["choice"][0])
        self.assertIn("不公开其中未经许可", bank["rows"][89]["choice"][0])
        self.assertIn("不随意提交敏感资料", topic["choice"][91])
        self.assertIn("不补写尚未发生的成果", topic["choice"][93])
        selected = {role: set() for role in roles}
        reached = set()
        for axis in load_applicability()["axes"]:
            context = {"id": "portrait", "title": "测试", "evidence": "文化解释", "counter": "需现实核对",
                       "core": "生活观察", "tension": "不是已知经历", "axisDrive": axis}
            for index in range(240):
                seed = f"portrait-expanded-{index}"
                story = render_story(seed, context)
                evidence = story["narrativeEvidence"]
                self.assertEqual(story, render_story(seed, context))
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if row < 64:
                        continue
                    reached.add(row)
                    for role, actual in (("scene", story["scenes"][position * 2]),
                                         ("tension", story["scenes"][position * 2 + 1]),
                                         ("choice", story["items"][position]),
                                         ("reflection", story["summary"] if position == 0 else story["insight"])):
                        fragment = f"portrait:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        selected[role].add(version)
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
        self.assertEqual(reached, set(range(64, 96)))
        self.assertTrue(all({0, 1, 2, 3} <= versions <= set().union(*(variant_options("portrait", row, role) for row in range(64, 96))) for role, versions in selected.items()))
        # Rare row 70 has extra options; test reachability without relying on corpus frequency.
        focused = deepcopy(topic)
        focused["entryRows"] = [70]
        selected = {role: set() for role in roles}
        with patch("story_narrative.load_topic", return_value=focused):
            for index in range(128):
                story = render_story(f"portrait-row70-{index}", context)
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["fragmentIds"][0], "portrait:scene:70")
                for role in roles:
                    selected[role].add(evidence["paragraphVariants"][f"portrait:{role}:70"])
        self.assertTrue(all(versions == variant_options("portrait", 70, role) for role, versions in selected.items()))

    def test_career_collaboration_arcs_keep_all_wordings_and_practical_limits(self):
        topic, bank = load_topic("career"), load_variants("career")
        roles = ("scene", "tension", "choice", "reflection")
        limits = {
            96: ("相同事实与限制", "关键条件"), 97: ("不擅自录制", "不暗中拍摄"),
            98: ("不补造过程", "不虚构测试记录"), 99: ("无关隐私", "尊重隐私"),
            100: ("不越权承诺", "超权限事项"), 101: ("不冒充", "不编造资质"),
            102: ("无关个人特征", "无关隐私"), 103: ("不擅自省略安全步骤", "危险环节交由"),
            104: ("不擅自转嫁职责", "协作必需"), 105: ("不跳过安全检查", "必要复核"),
            106: ("不把设想", "不以剪辑效果"), 107: ("不自行越权", "不公开无关隐私"),
            108: ("不可比", "不选择性省略"), 109: ("未授权", "资料权限"),
            110: ("不擅自公开", "不夸大或侵占"), 111: ("双方同意", "双方许可"),
            112: ("不擅自取消", "不把个人判断当成共同决定"), 113: ("不擅自长期占用", "不把沉默"),
            114: ("未经同意不录音", "无法获得同意"), 115: ("不擅自删除", "不私自销毁"),
            116: ("不遮挡安全标识", "安全指引"), 117: ("不将简短分享代替", "资格要求"),
            118: ("自愿", "无关隐私"), 119: ("不把周期当保证", "必要休息"),
            120: ("不以小范围成功保证", "无依据保证"), 121: ("准确和可读", "先协商"),
            122: ("无关私人信息", "不以讥讽"), 123: ("不依赖命理", "不凭命理推断"),
            124: ("必要安全要求", "保留安全"), 125: ("不默认无限互助", "未经同意"),
            126: ("必要安全要求", "不压下安全问题"), 127: ("资料权限", "公开敏感材料"),
        }
        self.assertEqual(set(limits), set(range(96, 128)))
        for row, phrases in limits.items():
            self.assertIn(phrases[0], topic["choice"][row], row)
            self.assertIn(phrases[1], bank["rows"][row]["choice"][0], row)
            for role in roles:
                self.assertEqual(len(bank["rows"][row][role]), 4 if row == 104 else 2)
        selected = {(row, role): set() for row in range(96, 128) for role in roles}
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "career", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "编辑情境而非既有经历", "axisDrive": axis}
            for index in range(1200):
                seed = f"career-collaboration-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if row < 96:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"career:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"career:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        selected[row, role].add(version)
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
        for key, versions in selected.items():
            self.assertEqual(versions, set(range(5 if key[0] == 104 else 3)), key)

    def test_action_fourth_wording_keeps_specific_boundaries(self):
        bank = load_variants("actions")
        boundaries = {
            80: "不强迫每页", 81: "不把未回应当成同意", 82: "不擅自停掉关键服务",
            83: "原始来源", 84: "不勉强走不安全", 85: "附件权限", 86: "退出方式",
            87: "先取得同意", 88: "不收礼", 89: "不夸大结果", 90: "不公开完整私人行程",
            91: "未经授权不删除", 92: "不保证立刻好转", 93: "安全和关键条件",
            94: "不承接无依据指控", 95: "不突然抛下已承诺",
        }
        self.assertEqual(set(boundaries), set(range(80, 96)))
        for row, phrase in boundaries.items():
            for role in ("scene", "tension", "choice", "reflection"):
                self.assertEqual(len(bank["rows"][row][role]), 3)
            self.assertIn(phrase, bank["rows"][row]["choice"][2], row)

    def test_new_career_arcs_have_complete_rewordings_without_new_fragment_ids(self):
        bank = load_variants("career")
        self.assertEqual(bank["version"], "career-paragraph-variants-v11")
        self.assertEqual(len(bank["rows"]), 128)
        roles = ("scene", "tension", "choice", "reflection")
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), set(roles))
            expected = 5 if index == 51 else (4 if index in {74, 104} else (3 if 32 <= index < 64 else 2))
            if index in {64, 72}:
                expected += 1
            self.assertEqual({len(values) for values in row.values()}, {expected})
        selected = {role: set() for role in roles}
        context = {"id": "career", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "学习内化"}
        for index in range(120):
            story = render_story(f"career-variants-{index}", context)
            evidence = story["narrativeEvidence"]
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                if row < 32:
                    continue
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"career:{role}:{row}" for role in roles])
                for role in roles:
                    selected[role].add(evidence["paragraphVariants"][f"career:{role}:{row}"])
        for role, values in selected.items():
            expected = set().union(*(variant_options("career", row, role) for row in range(32, len(load_topic("career")["scene"]))))
            self.assertTrue(values.issubset(expected))
            self.assertIn(0, values)

    def test_expanded_career_scenarios_keep_boundaries_and_reach_all_wordings(self):
        topic = load_topic("career")
        bank = load_variants("career")
        self.assertEqual(topic["version"], 4)
        roles = ("scene", "tension", "choice", "reflection")
        for row, phrase in ((67, "私人"), (70, "原因"), (71, "授权"), (75, "权限"),
                            (79, "编造"), (80, "安全"), (81, "依据"), (89, "更正")):
            text = "".join(topic[role][row] + "".join(bank["rows"][row][role]) for role in roles)
            self.assertIn(phrase, text)
        reached = set()
        selected = {role: set() for role in roles}
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "career", "title": "测试", "evidence": "文化解释", "counter": "需现实核对",
                       "core": "生活观察", "tension": "假设情境而非已知经历", "axisDrive": axis}
            for index in range(1200):
                seed = f"career-expanded-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for offset, position in ((0, 0), (4, 1)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not 64 <= row < 96:
                        continue
                    reached.add(row)
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"career:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        selected[role].add(version)
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
        self.assertEqual(reached, set(range(64, 96)))
        self.assertTrue(all(versions == set().union(*(variant_options("career", row, role) for row in range(64, 96))) for role, versions in selected.items()))

    def test_portrait_and_career_three_wordings_keep_boundaries_and_identity(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "career": {33: "未经验证", 39: "共同约定", 40: "证据", 46: "许可", 49: "获准",
                       53: "合成", 54: "门槛", 60: "例外", 62: "证据", 65: "猜测", 68: "权限",
                       69: "分母", 70: "原因", 71: "未经授权", 75: "不借密码", 76: "权限",
                       77: "私人", 78: "专业支持", 79: "隐私", 80: "安全", 81: "拒绝编造",
                       83: "反证", 85: "授权", 86: "紧急", 87: "许可", 88: "获准", 89: "更正",
                       90: "低风险", 91: "休息", 92: "退出", 93: "维护", 94: "分享", 95: "学习成本"},
            "portrait": {2: "定型", 11: "性格", 16: "愿意", 20: "安全", 25: "协商", 33: "礼貌",
                         36: "事实", 40: "前提", 44: "征求", 45: "归还", 46: "猜测", 47: "依据",
                         54: "补救", 60: "核实", 62: "未经证实", 65: "安全", 67: "猜测", 69: "隐私",
                         73: "想象", 75: "食品安全", 76: "意愿", 79: "愿意", 80: "核实",
                         81: "吉凶", 82: "停用", 83: "原始", 84: "不适", 85: "关键条件",
                         87: "真实", 88: "低风险", 89: "私密", 91: "敏感", 92: "指责", 93: "事实", 94: "偶然"},
        }
        for topic_id in ("portrait", "career"):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                new_roles = roles if topic_id == "career" or row >= 64 else ("choice", "reflection")
                self.assertIn(phrase, "".join(bank["rows"][row][role][1] for role in new_roles), (topic_id, row))
            for role in roles:
                self.assertEqual(len({row[role][1] for row in bank["rows"][:96]}), 96)
            selected = {(row, role): set() for row in range(96) for role in roles}
            for axis in (*load_applicability()["axes"], "综合承接"):
                context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                           "core": "生活观察", "tension": "假设场景而非既有经历", "axisDrive": axis}
                for index in range(1200 if topic_id == "career" else 600):
                    seed = f"{topic_id}-three-wordings-{index}"
                    story = render_story(seed, context)
                    self.assertEqual(story, render_story(seed, context))
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                    for position, offset in enumerate((0, 4)):
                        row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                        if row >= 96:
                            continue
                        self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                         [f"{topic_id}:{role}:{row}" for role in roles])
                        values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                                  story["items"][position], story["summary"] if position == 0 else story["insight"])
                        for role, actual in zip(roles, values):
                            fragment = f"{topic_id}:{role}:{row}"
                            version = evidence["paragraphVariants"][fragment]
                            selected[row, role].add(version)
                            options = [topic[role][row], *bank["rows"][row][role]]
                            self.assertEqual(actual, express(options[version], seed, fragment))
            for key, versions in selected.items():
                self.assertEqual(versions, variant_options(topic_id, key[0], key[1]), (topic_id, key))

    def test_new_structure_arcs_keep_each_role_and_its_original_identity(self):
        roles = ("scene", "tension", "choice", "reflection")
        bank = load_variants("structure")
        self.assertEqual(bank["version"], "structure-paragraph-variants-v16")
        self.assertEqual(len(bank["rows"]), 180)
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), set(roles))
            for role, values in row.items():
                if index == 32:
                    expected_len = 4
                elif index in {41, 67}:
                    expected_len = 3
                elif index in {145, 150}:
                    expected_len = 4
                else:
                    expected_len = 2 if index >= 96 or (index < 32 and role in {"scene", "tension"}) else 1
                    if index in {18, 34, 46, 48, 104, 124, 127, 168, 173}:
                        expected_len += 1
                if 64 <= index < 96:
                    expected_len += 2
                self.assertEqual(len(values), expected_len)
        selected = {(band, role): set() for band in ("legacy", "expanded", "operational", "everyday") for role in roles}
        context = {"id": "structure", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "规则责任"}
        for index in range(120):
            story = render_story(f"structure-variants-{index}", context)
            evidence = story["narrativeEvidence"]
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"structure:{role}:{row}" for role in roles])
                for role in roles:
                    selected[("legacy" if row < 32 else "expanded" if row < 96 else "operational" if row < 128 else "everyday", role)].add(
                        evidence["paragraphVariants"][f"structure:{role}:{row}"])
        for (band, role), values in selected.items():
            ranges = {"legacy": (0, 32), "expanded": (32, 96), "operational": (96, 128), "everyday": (128, 180)}
            expected = set().union(*(variant_options("structure", row, role) for row in range(*ranges[band])))
            self.assertTrue(values.issubset(expected))
            self.assertIn(0, values)

    def test_structure_and_action_expansions_keep_complete_arcs_and_every_wording(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundary_terms = {
            "structure": {67: "安全", 78: "安全", 85: "共同", 90: "同意", 93: "未知"},
            "actions": {68: "拒绝", 71: "同意", 77: "安全", 78: "许可", 79: "未成年人", 83: "来源", 92: "保证"},
        }
        for topic_id in ("structure", "actions"):
            topic = load_topic(topic_id)
            bank = load_variants(topic_id)
            self.assertEqual(topic["version"], 9 if topic_id == "structure" else 3)
            for row, term in boundary_terms[topic_id].items():
                prose = "".join(topic[role][row] + "".join(bank["rows"][row][role]) for role in roles)
                self.assertIn(term, prose)
            selected = {(row, role): set() for row in range(64, len(topic["scene"])) for role in roles}
            for axis in (*load_applicability()["axes"], "综合承接"):
                context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "需现实核对",
                           "core": "生活观察", "tension": "假设情境而非已知经历", "axisDrive": axis}
                for index in range(1200 if topic_id == "structure" else 600):
                    seed = f"expanded-{topic_id}-{index}"
                    story = render_story(seed, context)
                    self.assertEqual(story, render_story(seed, context))
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                    for offset, position in ((0, 0), (4, 1)):
                        row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                        if row < 64:
                            continue
                        self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                         [f"{topic_id}:{role}:{row}" for role in roles])
                        values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                                  story["items"][position], story["summary"] if position == 0 else story["insight"])
                        for role, actual in zip(roles, values):
                            fragment = f"{topic_id}:{role}:{row}"
                            version = evidence["paragraphVariants"][fragment]
                            selected[row, role].add(version)
                            options = [topic[role][row], *bank["rows"][row][role]]
                            self.assertEqual(actual, express(options[version], seed, fragment))
            for key, versions in selected.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(versions, expected, (topic_id, key))

    def test_structure_operational_scenarios_keep_all_wordings_and_boundaries(self):
        topic, bank = load_topic("structure"), load_variants("structure")
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            96: ("时区", "休息"), 97: ("授权", "公开"), 98: ("离线", "核"),
            99: ("候补", "期限"), 100: ("确认", "讨论"), 101: ("授权", "记录"),
            102: ("维护",), 103: ("生效", "强制"), 104: ("授权", "备份"),
            105: ("隐私", "协商"), 106: ("食品安全",), 107: ("休息",),
            108: ("保证", "条件"), 109: ("授权", "安全"), 110: ("紧急", "等待"),
            111: ("权限", "复核"), 112: ("整体", "等待"), 113: ("准备", "决定"),
            114: ("自愿", "隐私"), 115: ("说明", "尊重"), 116: ("颜色", "文字"),
            117: ("可靠", "材料"), 118: ("可靠", "安全"), 119: ("同意", "安全"),
            120: ("安全", "职责"), 121: ("停止", "维护"), 122: ("分歧", "确认"),
            123: ("许可", "安全"), 124: ("例外", "维护"), 125: ("自愿", "私人"),
            126: ("授权", "必要"), 127: ("法定", "记录"),
        }
        self.assertEqual(set(boundaries), set(range(96, 128)))
        for row, terms in boundaries.items():
            for version in (0, 1, 2):
                prose = "".join(topic[role][row] if version == 0 else bank["rows"][row][role][version - 1]
                                for role in roles)
                for term in terms:
                    self.assertIn(term, prose, (row, version, term))
        self.assertIn("不默认别人应当熬夜配合", topic["choice"][96])
        self.assertIn("归还", topic["choice"][102])
        self.assertIn("交还", bank["rows"][102]["tension"][0])
        self.assertIn("非敏感", topic["choice"][104])
        self.assertIn("不得擅自改动真实资料", bank["rows"][104]["choice"][0])
        self.assertIn("不擅自绕过安全或强制要求", topic["choice"][109])
        self.assertIn("不公开私人顾虑", topic["choice"][114])
        self.assertIn("不追问使用者无关隐私", topic["choice"][116])
        self.assertIn("不收集无关个人情况", bank["rows"][116]["choice"][0])
        self.assertIn("不自行撤掉安全或法定任务", bank["rows"][127]["choice"][0])

    def test_daily_rhythm_new_wordings_keep_support_and_safety_boundaries(self):
        bank = load_variants("wellbeing")
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            32: "环境", 33: "商量", 34: "不把公共空间单方面占为己用", 35: "休息",
            36: "必需", 37: "不突然失联", 38: "及时告知", 39: "不能确定",
            40: "官方", 41: "安全", 42: "双方", 43: "不依据这段建议自行诊断",
            44: "安全", 45: "职责", 46: "紧急安全风险", 47: "必要信息",
            48: "自身条件", 49: "不临时无故缺席", 50: "不打乱他人休息", 51: "必要职责",
            52: "不让自愿留下自动变成永久职责", 53: "必要交接", 54: "不擅自简化必要步骤",
            55: "安全和基本需要", 56: "双方意愿", 57: "安全交通", 58: "轮换",
            59: "必要事项", 60: "不补做余项", 61: "专业评估", 62: "明显不舒服时停止",
            63: "必要中断",
        }
        self.assertEqual(set(boundaries), set(range(32, 64)))
        for row, phrase in boundaries.items():
            self.assertIn(phrase, "".join(bank["rows"][row][role][1] for role in roles), row)
        selected = {(row, role): set() for row in range(32, 64) for role in roles}
        topic = load_topic("wellbeing")
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "wellbeing", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "编辑情境而非已知经历", "axisDrive": axis}
            for index in range(600):
                seed = f"daily-rhythm-three-wordings-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not 32 <= row < 64:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"wellbeing:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"wellbeing:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        selected[row, role].add(version)
        for key, versions in selected.items():
            self.assertEqual(versions, variant_options("wellbeing", key[0], key[1]), key)

    def test_action_rewordings_preserve_boundaries_and_reach_every_role(self):
        roles = ("scene", "tension", "choice", "reflection")
        topic = load_topic("actions")
        bank = load_variants("actions")
        self.assertEqual(bank["version"], "actions-paragraph-variants-v6")
        self.assertEqual(len(bank["rows"]), 96)
        for role in roles:
            self.assertEqual(len({row[role][1] for row in bank["rows"]}), 96)
        boundaries = {
            1: "安全", 2: "休息", 7: "愿意", 25: "偶然", 27: "睡眠",
            28: "意愿", 34: "历史", 41: "拒绝", 45: "隐私", 49: "原谅",
            57: "明确同意", 59: "不能自动证明原因", 62: "个人资料",
            64: "不够相信", 65: "双方确认", 66: "最新通知", 67: "紧急联系",
            68: "不催", 69: "不顺带布置新任务", 70: "资格", 71: "同意",
            72: "许可", 73: "不安全", 74: "拒绝", 75: "他人必须满足",
            76: "确认", 77: "不安全", 78: "未经许可", 79: "未成年人",
            81: "不等于同意", 82: "必要依赖", 83: "原始来源", 84: "隐私",
            85: "权限", 86: "退出", 87: "取得同意", 88: "不收礼",
            89: "条件差异", 90: "私人行程", 91: "未经授权", 92: "保证",
            93: "安全", 94: "无依据", 95: "责任",
        }
        for row, term in boundaries.items():
            prose = "".join(bank["rows"][row][role][1] for role in roles)
            self.assertIn(term, prose, row)
        selected = {(row, role): set() for row in range(96) for role in roles}
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "actions", "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "假设场景而非已知经历", "axisDrive": axis}
            for index in range(1200):
                seed = f"actions-three-wordings-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"actions:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"actions:{role}:{row}"
                        variant = evidence["paragraphVariants"][fragment]
                        selected[row, role].add(variant)
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[variant], seed, fragment))
        for key, versions in selected.items():
            expected = variant_options("actions", key[0], key[1])
            self.assertEqual(versions, expected, key)

    def test_portrait_and_structure_new_advice_retains_context_and_boundaries(self):
        for topic, count in (("portrait", 64), ("structure", 32)):
            rows = load_variants(topic)["rows"][:count]
            for role in ("choice", "reflection"):
                self.assertEqual(len({row[role][0] for row in rows}), count)
        portrait = load_variants("portrait")["rows"]
        self.assertIn("基本礼貌", portrait[33]["choice"][0])
        self.assertIn("征求意愿", portrait[44]["choice"][0])
        self.assertIn("归还条件", portrait[45]["choice"][0])
        self.assertIn("不把偶然结果归给运气", portrait[62]["choice"][0])
        self.assertIn("不是替人控制命运", portrait[62]["reflection"][0])
        structure = load_variants("structure")["rows"]
        self.assertIn("不可复制的偶然因素", structure[19]["choice"][0])
        self.assertIn("适用条件", structure[30]["choice"][0])

    def test_wealth_money_entry_and_new_arcs_preserve_scope_and_boundaries(self):
        topic, bank = load_topic("wealth"), load_variants("wealth")
        roles = ("scene", "tension", "choice", "reflection")
        self.assertEqual(topic["version"], 4)
        self.assertEqual(topic["familyVersion"], "wealth-scene-families-v1")
        self.assertEqual(len(set(topic["families"])), 8)
        self.assertNotIn(64, topic["entryRows"])
        self.assertNotIn(81, topic["entryRows"])
        self.assertNotIn(124, topic["entryRows"])
        self.assertTrue(set(range(96, 128)) - {124} <= set(topic["entryRows"]))
        boundaries = {
            96: ("不把预计到账", "不擅自改变约定"),
            97: ("尚未确定", "不预设后续报酬"),
            98: ("不为未获同意", "不把报销预期"),
            99: ("征求同意", "未同意"),
            100: ("不要求对方等价回赠", "不要求回礼"),
            101: ("未理解条件", "不只凭起始价"),
            102: ("当地专业意见", "不自行推定"),
            103: ("实际到账前", "不重复预支"),
            104: ("不把取消提醒误当", "确认继续或停止"),
            105: ("不只拿最大次数", "不为折扣许下"),
            106: ("不为不需要", "不把待兑换奖励"),
            107: ("休息和安全", "自身条件"),
            108: ("基本照护和安全", "不盲目停掉必要服务"),
            109: ("不预设旧款项", "不把尚未落实"),
            110: ("不要求他人公开", "先获同意"),
            111: ("不要求别人", "不把消费差异"),
            112: ("允许拒绝", "先取得对方同意"),
            113: ("不追问无关", "隐私与选择"),
            114: ("不要求密码", "遮去无关个人信息"),
            115: ("资质要求", "重大或专业事项核验资质"),
            116: ("不自行冒险拆修", "不因已经送修"),
            117: ("不擅自扩大使用", "不以已经付费"),
            118: ("不凭外形相似", "不冒险凑用"),
            119: ("不把付费当作能力", "不用同时报名"),
            120: ("安全条件", "保护必要隐私"),
            121: ("不挤占必要责任", "不为了奖励而追加债务"),
            122: ("不泄露受助者隐私", "拒绝不明转账请求"),
            123: ("不擅自替所有人购买", "取得同意后执行"),
            124: ("不使用未经授权", "不用人情迫使"),
            125: ("长期难以承担", "不把尚未收到"),
            126: ("不擅自处置共有物", "不为用完材料强行"),
            127: ("不要求交出账户控制权", "优先寻求可信支持"),
        }
        self.assertEqual(set(boundaries), set(range(96, 128)))
        for row, pair in boundaries.items():
            for version, phrase in enumerate(pair):
                text = "".join(topic[role][row] if version == 0 else bank["rows"][row][role][0]
                               for role in roles)
                self.assertIn(phrase, text, (row, version))
        new_boundaries = [
            "不擅自改变约定",
            "不预设后续报酬",
            "在授权范围内",
            "未获同意",
            "不要求回礼",
            "未理解的增项",
            "当地专业人士",
            "不重复预支",
            "不能视为取消服务",
            "不为折扣",
            "不把待兑换奖励",
            "必要休息",
            "不盲目停掉必要服务",
            "尚未落实",
            "不追问无关收入",
            "不逼人超出负担",
            "允许拒绝",
            "隐私与选择",
            "不交出密码",
            "核验资质",
            "不因已经送修就默认全部同意",
            "不以已经付费",
            "不冒险凑用",
            "不用同时报名",
            "保护必要隐私",
            "不为了奖励而追加债务",
            "拒绝不明转账请求",
            "取得同意后执行",
            "不使用未经授权",
            "不把尚未收到",
            "剩余共有物协商处理",
            "优先寻求可信支持"
        ]
        for row, phrase in enumerate(new_boundaries, start=96):
            self.assertIn(phrase, bank["rows"][row]["choice"][1], row)
        selected = {(row, role): set() for row in range(96, 128) for role in roles}
        reached_first, reached_second = set(), set()
        for axis in (*load_applicability()["axes"], "综合承接"):
            context = {"id": "wealth", "title": "旧标题", "evidence": "文化解释", "counter": "现实核对",
                       "core": "生活观察", "tension": "假设示例", "axisDrive": axis}
            for index in range(1200):
                seed = f"wealth-money-scene-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                self.assertEqual(story["title"], topic["title"])
                evidence = story["narrativeEvidence"]
                basis = evidence["selectionBasis"]
                self.assertTrue(basis["entryRestricted"])
                self.assertEqual(basis["entryScope"], topic["entryScope"])
                self.assertNotEqual(*basis["familyContrast"]["selected"])
                first, second = (int(evidence["fragmentIds"][i].rsplit(":", 1)[1]) for i in (0, 4))
                self.assertIn(first, topic["entryRows"])
                reached_first.add(first)
                reached_second.add(second)
                for position, row in enumerate((first, second)):
                    if row < 96:
                        continue
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"wealth:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(actual, express(options[version], seed, fragment))
                        selected[row, role].add(version)
        self.assertEqual(reached_first, set(topic["entryRows"]))
        self.assertEqual(reached_second, set(range(128)))
        for key, values in selected.items():
            self.assertEqual(values, variant_options("wealth", key[0], key[1]), key)

    def test_wealth_variants_cover_all_roles_without_changing_original_fragment_ids(self):
        roles = ("scene", "tension", "choice", "reflection")
        bank = load_variants("wealth")
        self.assertEqual(bank["version"], "wealth-paragraph-variants-v10")
        self.assertEqual(len(bank["rows"]), 128)
        for row, variants in enumerate(bank["rows"]):
            self.assertEqual(set(variants), set(roles))
            for role in roles:
                expected = (3 if role in {"scene", "tension"} else 2) if row < 32 else 2
                if row == 89:
                    expected += 1
                self.assertEqual(len(variants[role]), expected)
        selected = {(band, role): set() for band in ("legacy", "expanded") for role in roles}
        context = {"id": "wealth", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "资源经营"}
        for index in range(240):
            story = render_story(f"wealth-variants-{index}", context)
            evidence = story["narrativeEvidence"]
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"wealth:{role}:{row}" for role in roles])
                for role in roles:
                    selected[("legacy" if row < 32 else "expanded", role)].add(
                        evidence["paragraphVariants"][f"wealth:{role}:{row}"])
        for (band, role), values in selected.items():
            ranges = {"legacy": (0, 32), "expanded": (32, 128)}
            expected = set().union(*(variant_options("wealth", row, role) for row in range(*ranges[band])))
            self.assertTrue(values.issubset(expected), (band, role))
            self.assertIn(0, values, (band, role))

    def test_character_and_resource_rewordings_reach_each_role_with_boundaries(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "character": {64: "不把反复自责", 68: "安全边界", 69: "不夹在道歉里反击",
                          70: "不随口许诺", 72: "不转述", 75: "不硬碰危险局面",
                          80: "不以忙碌取消修正", 82: "人格评价", 84: "代替证据",
                          86: "不擅自省略", 90: "明确约定", 91: "不采纳",
                          93: "停止条件", 94: "泄露隐私", 95: "人格结论"},
            "wealth": {33: "就谢绝", 39: "自愿分工", 41: "紧急联络渠道",
                       46: "不把模糊曝光当作确定回报", 48: "征求接收意愿",
                       49: "必要安全准备", 51: "许可和归还条件", 56: "许可范围",
                       57: "参与意愿", 61: "时段冲突先协商", 63: "允许错过"},
        }
        for topic_id, start in (("character", 64), ("wealth", 32)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                self.assertIn(phrase, bank["rows"][row]["choice"][1], (topic_id, row))
            selected = {(row, role): set() for row in range(start, start + 32) for role in roles}
            for axis in (*load_applicability()["axes"], "综合承接"):
                context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                           "core": "生活观察", "tension": "假设而非已知经历", "axisDrive": axis}
                for index in range(1200):
                    seed = f"complete-rewording-{index}"
                    story = render_story(seed, context)
                    self.assertEqual(story, render_story(seed, context))
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                    for position, offset in enumerate((0, 4)):
                        row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                        if not start <= row < start + 32:
                            continue
                        self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                         [f"{topic_id}:{role}:{row}" for role in roles])
                        values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                                  story["items"][position], story["summary"] if position == 0 else story["insight"])
                        for role, actual in zip(roles, values):
                            fragment = f"{topic_id}:{role}:{row}"
                            version = evidence["paragraphVariants"][fragment]
                            options = [topic[role][row], *bank["rows"][row][role]]
                            self.assertEqual(actual, express(options[version], seed, fragment))
                            selected[row, role].add(version)
            if topic_id == "character":
                focused = deepcopy(topic)
                focused["entryRows"] = [91]
                with patch("story_narrative.load_topic", return_value=focused):
                    for index in range(128):
                        seed = f"question-expression-91-{index}"
                        story = render_story(seed, context)
                        evidence = story["narrativeEvidence"]
                        self.assertEqual(evidence["fragmentIds"][0], "character:scene:91")
                        actual = (story["scenes"][0], story["scenes"][1], story["items"][0], story["summary"])
                        for role, text in zip(roles, actual):
                            fragment = f"character:{role}:91"
                            version = evidence["paragraphVariants"][fragment]
                            options = [topic[role][91], *bank["rows"][91][role]]
                            self.assertEqual(text, express(options[version], seed, fragment))
                            selected[91, role].add(version)
            for key, versions in selected.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(versions, expected, (topic_id, key))

    def test_relationship_variants_keep_all_roles_and_explicit_boundaries(self):
        bank = load_variants("relationships")
        self.assertEqual(bank["version"], "relationships-paragraph-variants-v10")
        self.assertEqual(len(bank["rows"]), 143)
        roles = ("scene", "tension", "choice", "reflection")
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), set(roles))
            expected_len = len(row["scene"])
            self.assertTrue(all(len(row[role]) == expected_len for role in roles))
        for role in roles:
            self.assertEqual(len({row[role][0] for row in bank["rows"]}), 143)
        danger = bank["rows"][46]
        self.assertIn("保障安全", danger["tension"][0])
        self.assertIn("现实支持", danger["tension"][0])
        self.assertIn("不以牺牲安全", danger["choice"][0])
        for row in (32, 48, 91, 103, 109):
            self.assertTrue(any(term in bank["rows"][row]["choice"][0]
                                for term in ("同意", "意愿", "允许", "许可")))
        context = {"id": "relationships", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "规则责任"}
        selected = {(band, role): set() for band in (0, 1, 2) for role in roles}
        for index in range(240):
            story = render_story(f"relationships-variants-{index}", context)
            evidence = story["narrativeEvidence"]
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"relationships:{role}:{row}" for role in roles])
                for role in roles:
                    selected[(row // 64, role)].add(evidence["paragraphVariants"][f"relationships:{role}:{row}"])
        for (band, role), versions in selected.items():
            ranges = {0: (0, 64), 1: (64, 128), 2: (128, len(load_topic("relationships")["scene"]))}
            expected = set().union(*(variant_options("relationships", row, role) for row in range(*ranges[band])))
            self.assertTrue(versions.issubset(expected), (band, role))
            self.assertIn(0, versions, (band, role))

    def test_relationship_and_action_new_roles_are_reachable_and_keep_boundaries(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "relationships": {32: "明确同意", 34: "未经允许", 38: "未经许可", 40: "默认同意",
                              43: "专业", 46: "牺牲安全", 48: "同意", 49: "不保证",
                              52: "私事", 53: "失联考验", 55: "不擅自", 57: "退出",
                              58: "寻求支持", 60: "拒绝", 63: "共识"},
            "actions": {1: "安全", 2: "先休息", 7: "愿意", 9: "不可逆", 13: "不自行降低",
                        16: "删掉", 19: "允许调整", 20: "低风险", 21: "获准", 25: "偶然",
                        27: "睡眠", 28: "同意", 29: "共有成果", 30: "他人权益", 31: "提前调整"},
        }
        for topic_id, start, option in (("relationships", 32, 2), ("actions", 0, 3)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                self.assertIn(phrase, bank["rows"][row]["choice"][option - 1], (topic_id, row))
            selected = {(row, role): set() for row in range(start, start + 32) for role in roles}
            context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "实际核对",
                       "core": "日常观察", "tension": "场景不代表已知经历", "axisDrive": "综合承接"}
            for index in range(2200):
                seed = f"{topic_id}-new-roles-v41-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not start <= row < start + 32:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"{topic_id}:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, text in zip(roles, values):
                        fragment = f"{topic_id}:{role}:{row}"
                        version = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        expected_option_count = 5 if topic_id == "relationships" and row == 54 else option + 1
                        self.assertGreaterEqual(len(set(options)), expected_option_count)
                        expected_option_count = len(set(options))
                        self.assertEqual(text, express(options[version], seed, fragment))
                        selected[row, role].add(version)
            for key, versions in selected.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(versions, expected, (topic_id, key))

    def test_portrait_and_wealth_new_roles_keep_boundaries_and_all_options(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "wealth": {3: "不默认为", 6: "可靠渠道", 11: "不作勉强", 13: "必须继续",
                       17: "未经同意", 18: "先停用", 21: "合格意见", 22: "密码",
                       24: "许可", 25: "关联影响", 28: "可靠依据", 29: "知情同意", 31: "单方意愿"},
            "portrait": {65: "遵守要求", 67: "不把猜测", 69: "私密", 70: "重要原件",
                         73: "不用想象", 75: "食品安全", 76: "沉默", 79: "愿意",
                         80: "可信来源", 82: "先停用", 83: "证据", 84: "及时停止",
                         85: "尚未证明", 87: "不为悦耳", 88: "低风险", 89: "未经许可",
                         91: "敏感资料", 92: "指责", 93: "不虚构", 94: "低风险"},
        }
        for topic_id, start in (("wealth", 0), ("portrait", 64)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                original_option = 2 if (topic_id, row) == ("portrait", 70) else -1
                self.assertIn(phrase, bank["rows"][row]["choice"][original_option], (topic_id, row))
                if (topic_id, row) == ("portrait", 70):
                    for choice in bank["rows"][row]["choice"][3:]:
                        if "删" in choice or "去重" in choice:
                            self.assertIn("重要原件", choice)
            selected = {(row, role): set() for row in range(start, start + 32) for role in roles}
            context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "日常观察", "tension": "不预设个人经历", "axisDrive": "综合承接"}
            seeds = [("综合承接", index) for index in range(4800)]
            seeds += [(axis, index) for axis in load_applicability()["axes"] for index in range(1200)]
            for axis, index in seeds:
                context["axisDrive"] = axis
                seed = f"{topic_id}-new-roles-v42-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not start <= row < start + 32:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"{topic_id}:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"{topic_id}:{role}:{row}"
                        options = [topic[role][row], *bank["rows"][row][role]]
                        option = evidence["paragraphVariants"][fragment]
                        self.assertEqual(actual, express(options[option], seed, fragment))
                        selected[row, role].add(option)
            for (row, role), options in selected.items():
                self.assertEqual(options, set(range(len(bank["rows"][row][role]) + 1)), (topic_id, row, role))

    def test_portrait_and_career_new_roles_cover_each_option_and_keep_boundaries(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "portrait": {33: "失礼", 35: "先协商", 36: "当事实", 40: "资历", 44: "愿意",
                         45: "归还", 46: "未证实", 47: "新依据", 50: "不补写", 54: "羞辱",
                         57: "紧急", 60: "推测", 62: "吉凶证明", 63: "判定"},
            "career": {33: "未经验证", 34: "擅自", 35: "风险", 36: "确定期限", 37: "停止条件",
                       38: "许可范围", 39: "许可", 40: "保证", 41: "安全", 45: "不隐瞒",
                       46: "受限", 49: "公开", 51: "一致", 52: "休息", 53: "合成",
                       54: "安全", 55: "必要响应", 59: "许可", 60: "高风险", 61: "低风险",
                       62: "不许诺", 63: "失联"},
        }
        for topic_id in ("portrait", "career"):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                self.assertIn(phrase, bank["rows"][row]["choice"][2], (topic_id, row))
            selected = {(row, role): set() for row in range(32, 64) for role in roles}
            context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "实际核对",
                       "core": "日常观察", "tension": "不预设个人经历", "axisDrive": "综合承接"}
            for index in range(2400):
                seed = f"{topic_id}-new-roles-v43-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not 32 <= row < 64:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"{topic_id}:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"{topic_id}:{role}:{row}"
                        options = [topic[role][row], *bank["rows"][row][role]]
                        expected_option_count = 6 if (topic_id == "career" and row == 51) or (topic_id == "portrait" and row in {41, 45, 51, 55, 56, 60}) else 4
                        self.assertGreaterEqual(len(set(options)), expected_option_count)
                        expected_option_count = len(set(options))
                        option = evidence["paragraphVariants"][fragment]
                        self.assertEqual(actual, express(options[option], seed, fragment))
                        selected[row, role].add(option)
            for key, options in selected.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(options, expected, (topic_id, key))

    def test_resource_and_choice_new_roles_retain_boundaries_and_all_options(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "wealth": {65: "续用条件", 68: "愿意", 69: "隐私", 70: "同意", 72: "原谅",
                       73: "安全", 75: "必要服务", 77: "风险", 79: "无法确认", 80: "备份",
                       81: "必要承诺", 82: "必需", 83: "必要事项", 86: "安全", 88: "转让",
                       90: "先协商", 92: "同意", 93: "核实", 94: "有权", 95: "虚构"},
            "character": {33: "不确定", 34: "危险", 35: "紧急", 36: "必然成功", 37: "重大不可逆",
                          40: "补写", 41: "拒绝", 42: "同意", 43: "不夸大", 44: "隐私",
                          46: "紧急", 47: "低风险", 48: "迫使", 49: "不装懂", 50: "未证实",
                          51: "猜测", 54: "安全", 58: "专业支持", 59: "协商", 60: "依据",
                          61: "保密", 62: "关键风险", 63: "未来走向"},
        }
        for topic_id, start, new_option in (("wealth", 64, 2), ("character", 32, 3)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                self.assertIn(phrase, bank["rows"][row]["choice"][-1], (topic_id, row))
            selected = {(row, role): set() for row in range(start, start + 32) for role in roles}
            context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "日常观察", "tension": "不预设个人经历", "axisDrive": "综合承接"}
            for index in range(4800):
                seed = f"{topic_id}-new-roles-v44-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not start <= row < start + 32:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"{topic_id}:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"{topic_id}:{role}:{row}"
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(len(set(options)), len(options))
                        option = evidence["paragraphVariants"][fragment]
                        self.assertEqual(actual, express(options[option], seed, fragment))
                        selected[row, role].add(option)
            for key, options in selected.items():
                self.assertEqual(options, variant_options(topic_id, key[0], key[1]), (topic_id, key))

    def test_review_and_transition_new_roles_preserve_sources_and_boundaries(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "review": {32: "未提供", 35: "必要支持", 38: "不计作预测命中", 39: "时刻未知",
                       40: "不编造", 43: "发生前", 44: "不填写虚假", 46: "有来源",
                       48: "缺失", 49: "语义", 51: "专业意见", 57: "允许不认同",
                       58: "未知", 60: "不得当作预测准确率", 61: "歧视", 62: "未命中", 63: "不据命理预定"},
            "turning-points": {97: "不接受侮辱", 100: "权限", 102: "低风险", 104: "先协商",
                               108: "不把未知写成已完成", 109: "同意", 110: "安全", 111: "不预设",
                               112: "安全", 113: "官方", 115: "不归咎", 116: "不自行试验",
                               118: "不越权", 119: "不盲目删除", 121: "退出", 122: "核验",
                               123: "协商", 124: "不夸大", 125: "自主", 127: "同意"},
        }
        for topic_id, start in (("review", 32), ("turning-points", 96)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                self.assertIn(phrase, bank["rows"][row]["choice"][-1], (topic_id, row))
            selected = {(row, role): set() for row in range(start, start + 32) for role in roles}
            context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "日常观察", "tension": "不预设个人经历", "axisDrive": "综合承接"}
            for index in range(4800):
                seed = f"{topic_id}-new-roles-v45-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not start <= row < start + 32:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"{topic_id}:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"{topic_id}:{role}:{row}"
                        options = [topic[role][row], *bank["rows"][row][role]]
                        expected_option_count = 5 if (topic_id, row) in {("turning-points", 121), ("review", 53)} else 3
                        self.assertGreaterEqual(len(set(options)), expected_option_count)
                        expected_option_count = len(set(options))
                        option = evidence["paragraphVariants"][fragment]
                        self.assertEqual(actual, express(options[option], seed, fragment))
                        selected[row, role].add(option)
            if topic_id == "review":
                for _, story in archived_review_coverage():
                    evidence = story["narrativeEvidence"]
                    row = int(evidence["fragmentIds"][4].rsplit(":", 1)[1])
                    if 32 <= row < 64:
                        for role in roles:
                            selected[row, role].add(evidence["paragraphVariants"][f"review:{role}:{row}"])
            for key, options in selected.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(options, expected, (topic_id, key))

    def test_collaboration_and_daily_support_new_roles_preserve_complete_arcs(self):
        roles = ("scene", "tension", "choice", "reflection")
        boundaries = {
            "career": {96: "限制一致", 97: "同意", 98: "不虚构", 99: "隐私", 100: "安全",
                       101: "资格", 102: "证据", 103: "安全", 104: "不擅自", 105: "授权",
                       106: "未验证", 107: "权限", 108: "不可比", 109: "未授权", 110: "公开许可",
                       111: "双方同意", 112: "有权", 113: "沉默", 114: "同意", 115: "权限",
                       116: "安全", 117: "资格", 118: "自愿", 119: "不将", 120: "停止",
                       121: "先协商", 122: "不羞辱", 123: "专业资格", 124: "授权", 125: "未经同意不扩大",
                       126: "安全", 127: "许可"},
            "wellbeing": {65: "交接", 66: "协商", 67: "必要信息", 70: "安全", 71: "意愿",
                          72: "不以补罚", 73: "承诺", 74: "分工", 75: "立即", 76: "遗漏",
                          78: "安全", 79: "基本使用", 80: "不为展示", 81: "先协商", 82: "规则",
                          83: "紧急", 84: "安全", 85: "职责", 86: "规范", 88: "不强迫",
                          89: "核实", 90: "不在行车中", 92: "紧急", 93: "交接", 94: "专业支持"},
        }
        for topic_id, start in (("career", 96), ("wellbeing", 64)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            for row, phrase in boundaries[topic_id].items():
                self.assertIn(phrase, bank["rows"][row]["choice"][-1], (topic_id, row))
                self.assertNotIn("不未经", bank["rows"][row]["choice"][-1], (topic_id, row))
            selected = {(row, role): set() for row in range(start, start + 32) for role in roles}
            context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                       "core": "日常观察", "tension": "编辑情境而非已知经历", "axisDrive": "综合承接"}
            for index in range(4800):
                seed = f"{topic_id}-new-roles-v46-{index}"
                story = render_story(seed, context)
                self.assertEqual(story, render_story(seed, context))
                evidence = story["narrativeEvidence"]
                self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    if not start <= row < start + 32:
                        continue
                    self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                     [f"{topic_id}:{role}:{row}" for role in roles])
                    values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                              story["items"][position], story["summary"] if position == 0 else story["insight"])
                    for role, actual in zip(roles, values):
                        fragment = f"{topic_id}:{role}:{row}"
                        options = [topic[role][row], *bank["rows"][row][role]]
                        expected_count = len(set(options))
                        self.assertGreaterEqual(expected_count, 3)
                        self.assertEqual(len(set(options)), expected_count)
                        option = evidence["paragraphVariants"][fragment]
                        self.assertEqual(actual, express(options[option], seed, fragment))
                        selected[row, role].add(option)
            for key, options in selected.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(options, expected, (topic_id, key))

    def test_portrait_explanations_and_actions_do_not_repeat_the_flagged_phrases(self):
        bank = load_variants("portrait")
        explanation = bank["rows"][27]["tension"][1]
        action = bank["rows"][35]["choice"][2]
        self.assertNotIn("穿着相似的外衣", explanation)
        self.assertIn("协商分工", explanation)
        self.assertNotIn("证明全面", action)
        self.assertIn("先协商", action)
        self.assertIn("安全", action)
        self.assertIn("只试约定的部分", action)

    def test_character_reversible_choice_question_keeps_authored_punctuation(self):
        source = load_variants("character")["rows"][37]["scene"][1]
        self.assertTrue(source.endswith("吗？"))
        self.assertNotIn("吗。", source)
        for index in range(32):
            self.assertTrue(express(source, f"question-{index}", "character:scene:37").endswith("吗？"))

    def test_expanded_relationship_paragraphs_retain_complete_arcs(self):
        topic, bank = load_topic("relationships"), load_variants("relationships")
        roles = ("scene", "tension", "choice", "reflection")
        selected = {(row, role): set() for row in range(96, len(topic["scene"])) for role in roles}
        context = {"id": "relationships", "title": "测试", "evidence": "文化解释", "counter": "实际核对",
                   "core": "日常交往", "tension": "不预设经历", "axisDrive": "综合承接"}
        for index in range(2000):
            seed = f"relationships-expanded-{index}"
            story = render_story(seed, context)
            evidence = story["narrativeEvidence"]
            for position, offset in enumerate((0, 4)):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                if row < 96:
                    continue
                actual = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                          story["items"][position], story["summary"] if position == 0 else story["insight"])
                for role, text in zip(roles, actual):
                    fragment = f"relationships:{role}:{row}"
                    version = evidence["paragraphVariants"][fragment]
                    options = [topic[role][row], *bank["rows"][row][role]]
                    self.assertEqual(text, express(options[version], seed, fragment))
                    selected[row, role].add(version)
        # Whole-pool sampling is not guaranteed to reach every option after expansion.
        for row in range(96, len(topic["scene"])):
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            with patch("story_narrative.load_topic", return_value=focused):
                for index in range(128):
                    seed = f"relationships-complete-options-{row}-{index}"
                    story = render_story(seed, context)
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(evidence["fragmentIds"][0], f"relationships:scene:{row}")
                    actual = (story["scenes"][0], story["scenes"][1], story["items"][0], story["summary"])
                    for role, text in zip(roles, actual):
                        fragment = f"relationships:{role}:{row}"
                        option = evidence["paragraphVariants"][fragment]
                        options = [topic[role][row], *bank["rows"][row][role]]
                        self.assertEqual(text, express(options[option], seed, fragment))
                        selected[row, role].add(option)
        for key, versions in selected.items():
            self.assertEqual(versions, variant_options("relationships", key[0], key[1]), key)
        for row in (103, 109, 122):
            self.assertTrue(any(word in bank["rows"][row]["choice"][1] for word in ("同意", "许可", "答复")))

    def test_relationship_transition_and_review_new_options_keep_complete_arcs(self):
        roles = ("scene", "tension", "choice", "reflection")
        for topic_id, start, last_option in (("relationships", 0, 2), ("turning-points", 64, 2), ("review", 64, 3)):
            topic, bank = load_topic(topic_id), load_variants(topic_id)
            reached = {(row, role): set() for row in range(start, start + 32) for role in roles}
            for axis in (*load_applicability()["axes"], "综合承接"):
                context = {"id": topic_id, "title": "测试", "evidence": "文化解释", "counter": "现实核对",
                           "core": "生活观察", "tension": "编辑情境而非已知经历", "axisDrive": axis}
                for index in range(1200):
                    seed = f"complete-arcs-v52-{topic_id}-{index}"
                    story = render_story(seed, context)
                    self.assertEqual(story, render_story(seed, context))
                    evidence = story["narrativeEvidence"]
                    self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
                    for position, offset in enumerate((0, 4)):
                        row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                        if not start <= row < start + 32:
                            continue
                        self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                         [f"{topic_id}:{role}:{row}" for role in roles])
                        values = (story["scenes"][position * 2], story["scenes"][position * 2 + 1],
                                  story["items"][position], story["summary"] if position == 0 else story["insight"])
                        for role, actual in zip(roles, values):
                            fragment = f"{topic_id}:{role}:{row}"
                            options = [topic[role][row], *bank["rows"][row][role]]
                            expected = len(set(options))
                            self.assertGreaterEqual(expected, last_option + 1)
                            self.assertEqual(len(set(options)), expected)
                            option = evidence["paragraphVariants"][fragment]
                            self.assertEqual(actual, express(options[option], seed, fragment))
                            reached[row, role].add(option)
            for key, options in reached.items():
                expected = variant_options(topic_id, key[0], key[1])
                self.assertEqual(options, expected, (topic_id, key))

    def test_everyday_new_wordings_keep_practical_boundaries(self):
        boundaries = {
            "character": {128: "拒绝", 129: "同意", 130: "诊断", 131: "不擅入", 132: "承诺",
                          133: "不以嘲弄", 134: "不借", 135: "可承受", 136: "安全", 137: "受限",
                          138: "合适帮助", 139: "持续越界", 140: "保护", 141: "同意", 142: "不依据巧合",
                          143: "专业支持", 144: "不嘲弄", 145: "专业", 146: "不攻击", 147: "越界",
                          148: "负担", 149: "不编造", 150: "双方选择", 151: "安全", 152: "隐私",
                          153: "同意", 154: "不盲目", 155: "未获同意", 156: "不逃避", 157: "不追赌",
                          158: "不绕过拒绝", 159: "未达标准"},
            "structure": {128: "通道", 129: "规则", 130: "未经授权", 131: "食品安全", 132: "同意",
                          133: "同意", 134: "无授权", 135: "未知", 136: "未获许可", 137: "安全检查",
                          138: "未获同意", 139: "先协商", 140: "安全", 141: "紧急安全", 142: "隐私",
                          143: "权限", 144: "不失联", 145: "寄送要求", 146: "不暗录", 147: "权限",
                          148: "指导", 149: "不羞辱", 150: "授权", 151: "不虚构", 152: "不冒用",
                          153: "私人地址", 154: "不擅翻", 155: "资质", 156: "交接", 157: "同意",
                          158: "不承诺", 159: "隐私"},
        }
        for topic, rows in boundaries.items():
            self.assertEqual(set(rows), set(range(128, 160)))
            for row, phrase in rows.items():
                self.assertIn(phrase, load_variants(topic)["rows"][row]["choice"][1], (topic, row))

    def test_plain_wording_and_shared_decisions_keep_their_limits(self):
        original = load_topic("turning-points")["tension"][72]
        variant = load_variants("turning-points")["rows"][72]["tension"][0]
        written = load_variants("turning-points")["rows"][81]["tension"][1]
        family = load_variants("relationships")["rows"][6]["choice"][1]
        self.assertNotIn("接收方式", original + variant)
        self.assertNotIn("回应不同的信息和责任需求", written)
        for phrase in ("个人选择尊重本人意愿", "涉及共同安排则一起协商", "不因承担更多事务就替他人作主"):
            self.assertIn(phrase, family)
        for index in range(128):
            rendered = express(family, str(index), "relationships:choice:6")
            self.assertIn("一起协商", rendered)
            self.assertIn("不因承担更多事务就替他人作主", rendered)

    def test_family_arrangement_and_music_sentences_are_plain_and_complete(self):
        family = load_topic("relationships")["choice"][16]
        music = load_variants("wellbeing")["rows"][97]["tension"][1]
        self.assertEqual(family, "家人替你安排事情时，说清希望提前参与哪一步决定。")
        self.assertTrue(music.startswith("喜欢什么，无须定期更新。"))
        self.assertIn("顾及场合", music)
        for index in range(128):
            self.assertNotIn("下一次被替你", express(family, str(index), "relationships:choice:16"))
            self.assertNotIn("更新频率的任务", express(music, str(index), "wellbeing:tension:97"))

    def test_turning_variants_keep_scenario_identity_and_generic_role_boundaries(self):
        bank = load_variants("turning-points")
        self.assertEqual(bank["version"], "turning-points-paragraph-variants-v8")
        self.assertEqual(len(bank["rows"]), 128)
        roles = ("scene", "tension", "choice", "reflection")
        for index, row in enumerate(bank["rows"]):
            self.assertEqual(set(row), set(roles))
            expected_len = 4 if index in {86, 87, 121} else (3 if index == 94 else (2 if index == 28 or index >= 64 else 1))
            self.assertTrue(all(len(row[role]) == expected_len for role in roles))
        for role in roles:
            self.assertEqual(len({row[role][0] for row in bank["rows"]}), 128)
        for row in (32, 39, 41, 57):
            for role in roles:
                self.assertNotIn("退休", bank["rows"][row][role][0])
                self.assertNotIn("孩子", bank["rows"][row][role][0])
        self.assertIn("保密", bank["rows"][56]["tension"][0])
        self.assertIn("不含保密信息", bank["rows"][56]["choice"][0])
        context = {"id": "turning-points", "title": "测试", "evidence": "文化解释", "counter": "按实际条件核对",
                   "core": "生活观察", "tension": "不是既有经历", "axisDrive": "自主驱动"}
        selected = {(band, role): set() for band in (0, 1) for role in roles}
        for index in range(240):
            story = render_story(f"turning-variants-{index}", context)
            evidence = story["narrativeEvidence"]
            self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
            for offset in (0, 4):
                row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                self.assertEqual(evidence["fragmentIds"][offset:offset + 4],
                                 [f"turning-points:{role}:{row}" for role in roles])
                for role in roles:
                    selected[(row // 64, role)].add(evidence["paragraphVariants"][f"turning-points:{role}:{row}"])
        for (band, role), versions in selected.items():
            expected = set().union(*(variant_options("turning-points", row, role) for row in range(64 if band == 1 else 0, 128 if band == 1 else 64)))
            self.assertTrue(versions.issubset(expected), (band, role))
            self.assertIn(0, versions, (band, role))

    def test_editorial_theme_tags_do_not_require_literal_keyword_presence(self):
        context = {"id": "wealth", "title": "测试", "evidence": "依据", "counter": "条件", "core": "观察", "tension": "待核实", "axisDrive": "资源经营"}
        story = render_story("frozen-seed", context)
        basis = story["narrativeEvidence"]["selectionBasis"]
        self.assertEqual(basis["method"], "traditional_axis_editorial_topic_tags")
        self.assertIn("R", basis["selectedTags"][0])
        self.assertIn("O", basis["selectedTags"][1])
        self.assertGreater(basis["eligibleCount"], 4)

    def test_adult_notes_do_not_claim_frequency_or_event_prediction(self):
        payload = {**exact_payload(), "year": 1991,
                   "events": [{"date": "2020-06", "type": "迁移", "summary": "搬到新城市"}]}
        report = generate_report(payload, use_wisdom=True)["report"]
        notes = {section["id"]: section["note"] for section in report["sections"]}
        self.assertNotIn("高频", notes["character"])
        self.assertIn("不是统计结论", notes["character"])
        self.assertIn("用于组织表达和回看", notes["turning-points"])
        self.assertIn("不能作为预测命中的证据", notes["turning-points"])

    def test_expression_preserves_authored_slow_pace_in_different_contexts(self):
        sources = ("熟悉的旋律陪今天慢慢过去。", "慢慢走回家。", "让习惯慢慢长出来。",
                   "雨水慢慢流过台阶。", "慢慢说完这一段。")
        for index in range(128):
            for source in sources:
                self.assertEqual(express(source, f"slow-pace-{index}", "grammar-boundary"), source)

    def test_support_and_rhythm_added_wordings_keep_action_boundaries(self):
        limits = {
            "character": {
                96: "未获明确授权", 97: "不公开", 98: "不无限拖延", 99: "来源可靠性",
                100: "不把一次结果", 101: "不参与取笑", 102: "双方意愿", 103: "不反复索取保证",
                104: "不保证", 105: "不无限搁置", 106: "不编造", 107: "停止施压",
                108: "实际能力", 109: "不要求", 110: "主动确认", 111: "不编造",
                112: "不急着", 113: "必要时拒绝", 114: "真实性", 115: "继续检验",
                116: "不夸大", 117: "紧急危险", 118: "不贴", 119: "不以沉默惩罚",
                120: "可靠说明", 121: "不制造问题", 122: "不为保住标签", 123: "不",
                124: "不照搬", 125: "不因道德压力", 126: "不冒险逞强", 127: "可执行安排",
            },
            "wellbeing": {
                96: "提前询问", 97: "安全", 98: "暂停连播", 99: "安全",
                100: "预算", 101: "不自行", 102: "不在驾驶中", 103: "不因限时",
                104: "不为补拍", 105: "不查询行踪", 106: "预算", 107: "安全",
                108: "隐私", 109: "必要事项", 110: "不改动设施", 111: "商量",
                112: "保留拒绝", 113: "可信", 114: "不把情绪当预兆", 115: "不连续追问",
                116: "急事联络", 117: "不假装", 118: "安全", 119: "不仓促承诺",
                120: "不以休息", 121: "不擅入", 122: "不为复制", 123: "不赋予",
                124: "不混用", 125: "安全条件", 126: "不私自离队", 127: "必要支持",
            },
        }
        for topic, boundaries in limits.items():
            self.assertEqual(set(boundaries), set(range(96, 128)))
            bank = load_variants(topic)
            for row, boundary in boundaries.items():
                self.assertIn(boundary, bank["rows"][row]["choice"][-1], (topic, row))

    def test_expression_preserves_arrange_objects_and_time_words(self):
        sources = (
            "今天重新安排未来。", "把这天重新安排得妥帖。", "重新安排剩余任务。",
            "这是一种重新安排。", "让各自有时间创作。", "没有时间有时是真实限制。",
            "这些约定有时限，沟通有时差，资料有时效。", "活动有时序要求。",
            "有时候先等一等。", "有时停下来也很必要。",
        )
        for source in sources:
            for index in range(64):
                self.assertEqual(express(source, f"arrange-time-{index}", "grammar-boundary"), source)

    def test_expression_keeps_notice_and_reservation_compounds_intact(self):
        sources = (
            "忠实保留意思。", "解释自己的保留意见。", "预留意外开销的余量。",
            "请留意台阶。", "留意变化，再决定怎样回应。",
            load_topic("relationships")["tension"][113],
            load_variants("character")["rows"][67]["choice"][0],
        )
        for source in sources:
            for index in range(128):
                self.assertEqual(express(source, f"notice-boundary-{index}", "compound-boundary"), source)

    def test_expression_preserves_phrase_boundaries_and_negation(self):
        source = "有时候可以先弄清楚，再把具体问题说清楚、写清楚。不一定要多一点点，也不等于必须少一点点。"
        variants = set()
        for index in range(32):
            text = express(source, str(index), "grammar-test")
            self.assertEqual(text, express(source, str(index), "grammar-test"))
            self.assertIn("有时候", text)
            self.assertIn("多一点点", text)
            self.assertIn("少一点点", text)
            self.assertTrue("不一定" in text or "未必" in text)
            self.assertTrue(any(phrase in text for phrase in ("不等于", "并不意味着", "不代表")))
            for fragment in ("楚楚", "并并", "尝尝", "候候", "的的"):
                self.assertNotIn(fragment, text)
            ambiguous_boundary = "挡下一次要求，留下一次机会，记下一次经历。"
            self.assertEqual(express(ambiguous_boundary, str(index), "phrase-boundary"), ambiguous_boundary)
            variants.add(text)
        self.assertGreater(len(variants), 1)

    def test_expression_keeps_conjunction_and_uncertainty_grammatical(self):
        source = "没有成品并不一定没有推进。不一定有效，也不代表保证成功。"
        independent = set()
        for index in range(64):
            text = express(source, str(index), "conjunction-boundary")
            self.assertIn("并不一定没有推进", text)
            self.assertNotIn("并未必", text)
            self.assertIn("不代表保证成功", text)
            self.assertTrue("不一定有效" in text or "未必有效" in text)
            independent.add("未必有效" in text)
        self.assertEqual(independent, {True, False})

    def test_expression_avoids_wordy_substitutions_without_removing_uncertainty(self):
        source = "下一步是适合自己的尝试。可能带来变化，也可能只是一次观察；不一定有效，不等于保证成功。"
        for index in range(40):
            text = express(source, str(index), "plain-language")
            self.assertIn("下一步", text)
            self.assertIn("适合自己", text)
            self.assertTrue(any(term in text for term in ("可能带来", "也许带来", "或许带来")))
            self.assertTrue(any(term in text for term in ("可能只是", "也许只是", "或许只是")))
            self.assertTrue("不一定有效" in text or "未必有效" in text)
            for phrase in ("接下来的一步", "后面的一步", "适合自身", "或许仅仅是"):
                self.assertNotIn(phrase, text)

    def test_uncertainty_phrases_keep_authored_grammar_in_all_contexts(self):
        phrases = ("可能来自", "可能带来", "可能让", "可能只是", "可能与")
        for index in range(64):
            for prefix in ("", "更", "最", "很", "极有", "有", "也", "不", "尽", "是否", "未必", "不太"):
                for phrase in phrases:
                    source = f"{prefix}{phrase}观察对象相关。"
                    self.assertEqual(express(source, str(index), "uncertainty-context"), source)
        source = load_variants("review")["rows"][68]["tension"][0]
        self.assertIn("更可能让", source)
        for index in range(128):
            result = express(source, str(index), "review:tension:68")
            self.assertIn("更可能让", result)
            self.assertNotIn("更也许", result)
            self.assertNotIn("更或许", result)

    def test_complete_arcs_are_marked_for_reading_without_changing_stored_prose(self):
        for year in (1991, 2010, 2016, 2024):
            report = generate_report({**exact_payload(), "year": year}, use_wisdom=True)["report"]
            for section in report["sections"]:
                if year == 1991 and section["id"] == "actions":
                    self.assertEqual(section["narrativeLayout"], "linked_actions")
                    self.assertEqual(section["scenes"], [])
                    self.assertEqual(len(section["items"]), 3)
                    continue
                self.assertEqual(section["narrativeLayout"], "paired_arcs")
                self.assertEqual(section["narrativeEvidence"]["expressionVersion"], EXPRESSION_VERSION)
                self.assertEqual(len(section["scenes"]), 4)
                self.assertEqual(len(section["items"]), 2)
                self.assertTrue(section["summary"] and section["insight"])
        baseline = generate_report(exact_payload())["report"]
        self.assertTrue(all("narrativeLayout" not in section for section in baseline["sections"]))

    def test_review_question_does_not_mix_conditional_and_interrogative_openings(self):
        source = load_variants("review")["rows"][17]["scene"][0]
        for index in range(40):
            text = express(source, str(index), "review:scene:17")
            self.assertIn("生活出现什么情况，才算这句话说错了？", text)
            self.assertFalse(any(term in text for term in ("如果", "假如", "倘若")))

    def test_candidate_rename_and_repeat_do_not_change_narrative(self):
        payload = {**exact_payload(), "year": 1991}
        report = generate_report(payload, use_wisdom=True)
        repeated = generate_report(payload, use_wisdom=True)
        renamed = generate_report({**payload, "name": "另一个称呼"}, use_wisdom=True)
        self.assertEqual(report["report"]["sections"], repeated["report"]["sections"])
        self.assertEqual(report["report"]["sections"], renamed["report"]["sections"])
        baseline = generate_report(payload)
        self.assertEqual(report["chart"], baseline["chart"])

    def test_reference_date_keeps_age_and_luck_context_stable_across_wall_clocks(self):
        class LaterClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2040, 1, 1, tzinfo=tz)

        payload = {**exact_payload(), "year": 2010}
        first = generate_report(payload, use_wisdom=True)
        with patch("report_engine.datetime", LaterClock), patch("narrative_engine.datetime", LaterClock):
            later = generate_report(payload, use_wisdom=True)
        self.assertNotEqual(first["report"]["generatedAt"], later["report"]["generatedAt"])
        later["report"]["generatedAt"] = first["report"]["generatedAt"]
        self.assertEqual(first, later)
        self.assertEqual(first["report"]["narrativeProfile"]["referenceDate"], "2026-09-20")

    def test_birth_after_model_reference_date_is_not_given_negative_age_guidance(self):
        with self.assertRaisesRegex(ValueError, "参照日"):
            generate_report({**exact_payload(), "year": 2027}, use_wisdom=True)

    def test_minor_uses_youth_content_and_unknown_time_stays_unknown(self):
        result = generate_report({**exact_payload(), "timeText": "不详"}, use_wisdom=True)
        self.assertIsNone(result["chart"]["hour_pillar"])
        for section in result["report"]["sections"]:
            self.assertEqual(section["narrativeEvidence"]["selectionBasis"]["audience"], "youth")
        self.assertEqual(result["report"]["narrativeProfile"]["audience"], "youth")
        self.assertTrue(all(claim["confidence"] in {"养育建议，不是人格预测", "计算结果"} for claim in result["report"]["claims"]))
        self.assertNotIn("婚姻", body_text(result["report"]["sections"]))

    def test_early_childhood_uses_caregiver_scenarios_not_schoolwork(self):
        knowledge = load_early_childhood()
        self.assertEqual(set(knowledge["topics"]), {path.stem for path in TOPICS.glob("*.json")})
        all_ids = []
        for topic_id, topic in knowledge["topics"].items():
            self.assertEqual(len(topic["arcs"]), 4)
            for arc in topic["arcs"]:
                self.assertTrue(all(arc[role] for role in ("scene", "tension", "choice", "reflection")))
                all_ids.append(arc["id"])
            for age in (0, 2, 5):
                story = render_youth_story("frozen-seed", {"age": age, "id": topic_id})
                basis = story["narrativeEvidence"]["selectionBasis"]
                self.assertEqual(basis["reader"], "caregiver")
                self.assertEqual(basis["developmentalBand"], "early_childhood")
                self.assertTrue(all(fragment.startswith("early-") for fragment in story["narrativeEvidence"]["fragmentIds"]))
                text = body_text([story])
                for unsuitable in ("考试成绩", "职业选择", "写作业", "应当会", "注定成功"):
                    self.assertNotIn(unsuitable, text)
            older = render_youth_story("frozen-seed", {"age": 6, "id": topic_id})
            self.assertEqual(older["narrativeEvidence"]["selectionBasis"]["reader"], "young_person_and_caregiver")
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_teen_and_school_age_examples_have_distinct_complete_story_arcs(self):
        knowledge = load_teen()
        self.assertEqual(set(knowledge["topics"]), {path.stem for path in TOPICS.glob("*.json")})
        all_ids = []
        for topic_id, topic in knowledge["topics"].items():
            self.assertEqual(len(topic["arcs"]), 6)
            for arc in topic["arcs"]:
                self.assertTrue(all(arc[role] for role in ("scene", "tension", "choice", "reflection")))
                all_ids.append(arc["id"])
            younger = render_youth_story("frozen-seed", {"age": 12, "id": topic_id})
            for age in (13, 17):
                older = render_youth_story("frozen-seed", {"age": age, "id": topic_id})
                evidence = older["narrativeEvidence"]
                self.assertEqual(evidence["selectionBasis"]["developmentalBand"], "teen")
                self.assertEqual(younger["narrativeEvidence"]["selectionBasis"]["developmentalBand"], "school_age")
                self.assertTrue(all(fragment.startswith("teen-") for fragment in evidence["fragmentIds"]))
                self.assertFalse(set(evidence["fragmentIds"]) & set(younger["narrativeEvidence"]["fragmentIds"]))
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_minor_notes_and_disclosure_match_readers_age_band(self):
        for year, band, note in ((2024, "early_childhood", "供照护者"),
                                 (2020, "school_age", "面向学龄阶段"),
                                 (2010, "teen", "情境供本人")):
            report = generate_report({**exact_payload(), "year": year}, use_wisdom=True)["report"]
            self.assertNotIn("情境预测", report["disclosure"])
            self.assertIn("不预测人格", report["disclosure"])
            for section in report["sections"]:
                self.assertEqual(section["narrativeEvidence"]["selectionBasis"]["developmentalBand"], band)
                self.assertTrue(section["note"].startswith(note))

    def test_supplied_event_remains_an_attributed_observation(self):
        payload = {**exact_payload(), "year": 1991, "events": [{"date": "2020-06", "type": "迁移", "summary": "搬到新城市"}]}
        result = generate_report(payload, use_wisdom=True)
        text = body_text(result["report"]["sections"])
        self.assertIn("你提供的经历记录是", text)
        self.assertIn("2020-06迁移：搬到新城市", text)
        self.assertIn("不是报告事先预测的结果", text)

    def test_frozen_six_fixtures_and_two_more_minors_meet_canonical_target(self):
        fixtures = [
            {"name": "甲", "gender": "male", "year": 1989, "month": 4, "day": 6, "timeText": "22:00", "birthplace": "西安"},
            {"name": "乙", "gender": "male", "year": 1991, "month": 5, "day": 22, "timeText": "00:30", "birthplace": "商洛"},
            {"name": "丙", "gender": "male", "year": 2018, "month": 4, "day": 5, "timeText": "05:25", "birthplace": "西安"},
            {"name": "丁", "gender": "female", "year": 1988, "month": 11, "day": 29, "timeText": "12:00", "birthplace": "宝鸡"},
            {"name": "戊", "gender": "female", "year": 1965, "month": 12, "day": 8, "timeText": "unknown", "birthplace": "宝鸡"},
            {"name": "己", "gender": "male", "year": 1961, "month": 9, "day": 27, "timeText": "unknown", "birthplace": "香港"},
            {"name": "未成年示例一", "gender": "female", "year": 2010, "month": 6, "day": 9},
            {"name": "未成年示例二", "gender": "male", "year": 2023, "month": 10, "day": 11},
        ]
        results = [generate_report({**exact_payload(), **fixture}, use_wisdom=True) for fixture in fixtures]
        for (i, left), (j, right) in combinations(enumerate(results), 2):
            with self.subTest(left=i, right=j):
                self.assertLess(narrative_similarity(left["report"], right["report"], width=7), TARGET)

    def test_different_databases_and_history_orders_do_not_change_prose(self):
        payloads = [{**exact_payload(), "year": 1991, "name": "成人测试"},
                    {**exact_payload(), "name": "成长测试"}]
        expected = [generate_report(payload, use_wisdom=True) for payload in payloads]
        with tempfile.TemporaryDirectory() as directory:
            for order in ((0, 1), (1, 0)):
                db = Path(directory) / f"order-{order[0]}.db"
                for index in order:
                    actual = generate_and_save_report(db, payloads[index], use_wisdom=True)
                    self.assertEqual(actual["report"]["sections"], expected[index]["report"]["sections"])
                    self.assertEqual(actual["report"]["claims"], expected[index]["report"]["claims"])
                    repeated = generate_and_save_report(db, payloads[index], use_wisdom=True)
                    self.assertTrue(repeated["reused"])
                    self.assertEqual(actual["recordId"], repeated["recordId"])
                renamed = generate_and_save_report(db, {**payloads[0], "name": "另一个称呼"}, use_wisdom=True)
                self.assertEqual(renamed["report"]["sections"], expected[0]["report"]["sections"])

    def test_concurrent_queries_reuse_one_saved_edition_and_failures_rollback(self):
        payload = {**exact_payload(), "year": 1991}
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.db"
            connect(db).close()
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: generate_and_save_report(db, payload, use_wisdom=True), range(2)))
            self.assertEqual(results[0]["recordId"], results[1]["recordId"])
            self.assertEqual(len(list_reports(db)), 1)
            with patch("server.generate_report", side_effect=NarrativeDiversityError("候选未通过")):
                with self.assertRaises(NarrativeDiversityError):
                    generate_and_save_report(db, {**payload, "year": 1992}, use_wisdom=True)
            self.assertEqual(len(list_reports(db)), 1)


if __name__ == "__main__":
    unittest.main()
