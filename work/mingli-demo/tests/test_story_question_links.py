from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_expression import express
from story_narrative import load_applicability, load_topic, load_variants, render_story
from test_story_overlap import context


class StoryQuestionLinkTests(unittest.TestCase):
    def test_added_wordings_reach_every_option_and_preserve_arc_identity(self):
        rows = {"portrait": [21, 27, 41, 45, 51, 55, 56, 60], "wellbeing": [48, 50],
                "structure": [150], "review": [53, *range(128, 178)], "character": [91], "turning-points": [86],
                "relationships": list(range(128, 140))}
        for name, indices in rows.items():
            topic, bank = load_topic(name), load_variants(name)
            for row in indices:
                focused = deepcopy(topic)
                focused["entryRows"] = [row]
                selected = {role: set() for role in ("scene", "tension", "choice", "reflection")}
                with patch("story_narrative.load_topic", return_value=focused):
                    for index in range(128):
                        seed = f"question-expression-{row}-{index}"
                        result = render_story(seed, context(name))
                        evidence = result["narrativeEvidence"]
                        self.assertEqual(evidence["fragmentIds"][0], f"{name}:scene:{row}")
                        actual = {"scene": result["scenes"][0], "tension": result["scenes"][1],
                                  "choice": result["items"][0], "reflection": result["summary"]}
                        for role in selected:
                            fragment = f"{name}:{role}:{row}"
                            version = evidence["paragraphVariants"][fragment]
                            selected[role].add(version)
                            choices = [topic[role][row], *bank["rows"][row][role]]
                            self.assertEqual(actual[role], express(choices[version], seed, fragment))
                for role, versions in selected.items():
                    self.assertEqual(versions, set(range(len(bank["rows"][row][role]) + 1)))
        structure = load_variants("structure")["rows"][150]["choice"][-2:]
        self.assertIn("保密", structure[0])
        self.assertIn("未经许可", structure[1])
        self.assertTrue(all("独立完成" in value or "共同参与者" in value for value in structure))
        memory = load_variants("portrait")["rows"][51]["choice"][-2:]
        self.assertTrue(all("空白" in value or "不推测" in value for value in memory))
        availability = load_variants("portrait")["rows"][41]["choice"][-2:]
        self.assertTrue(all("是否承接" in value or "重新确认" in value for value in availability))

    def test_new_wordings_keep_consent_feedback_and_handoff_boundaries(self):
        boundaries = {
            "review": (53, [("低风险", "结束条件"), ("不适用", "不把结果不好")]),
            "character": (91, [("同意", "不接受"), ("不越过对方意愿", "不承诺")]),
            "wellbeing": (48, [("自身条件", "不为展示"), ("不凭片段", "完整生活")]),
            "turning-points": (86, [("交接", "不将持续帮忙"), ("有序交接", "不突然丢下")]),
        }
        for topic, (row, required) in boundaries.items():
            choices = load_variants(topic)["rows"][row]["choice"][-2:]
            for text, phrases in zip(choices, required):
                for phrase in phrases:
                    self.assertIn(phrase, text, (topic, row))


    def test_new_review_arcs_preserve_boundaries_and_editorial_status(self):
        topic, bank = load_topic("review"), load_variants("review")
        boundaries = {
            128: [
                "后来才出现",
                "不替没有经历"
            ],
            129: [
                "先沟通",
                "不强行两头兼顾"
            ],
            130: [
                "不",
                "核对"
            ],
            131: [
                "支持",
                "支持"
            ],
            132: [
                "安全",
                "不擅自改装"
            ],
            133: [
                "正式要求",
                "核实"
            ],
            134: [
                "必要职责",
                "不擅自关闭"
            ],
            135: [
                "不要求一天补齐",
                "不忽略"
            ],
            136: [
                "不扩散无关隐私",
                "不以删除记录"
            ],
            137: [
                "不以礼物",
                "不要求立即"
            ],
            138: [
                "低风险",
                "保留无效"
            ],
            139: [
                "必要余量",
                "不"
            ],
            140: [
                "不以回复数量",
                "按权限"
            ],
            141: [
                "尊重",
                "不"
            ],
            142: [
                "愿意",
                "不推断"
            ],
            143: [
                "允许调整",
                "不要求"
            ]
        }
        for row, phrases in boundaries.items():
            choices = [topic["choice"][row], *bank["rows"][row]["choice"]]
            self.assertGreaterEqual(len(choices), len(phrases))
            for choice, phrase in zip(choices, phrases):
                self.assertIn(phrase, choice, row)
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            with patch("story_narrative.load_topic", return_value=focused):
                result = render_story(f"new-review-boundary-{row}", context("review"))
            self.assertEqual(result["narrativeEvidence"]["evidenceType"], "editorial_hypothesis")
            self.assertEqual(result["narrativeEvidence"]["fragmentIds"][0], f"review:scene:{row}")

    def test_added_review_wordings_preserve_specific_action_boundaries(self):
        bank = load_variants("review")
        required = {
            128: ("可提前核对", "未知"), 129: ("协商", "不随意推翻"),
            130: ("减少返工", "不把无效"), 131: ("高风险", "不为了证明独立"),
            132: ("未经允许", "授权"), 133: ("正式渠道核实", "不擅自"),
            134: ("不以突然失联", "必要联络"), 135: ("必要承诺", "及时商量"),
            136: ("未经允许", "不用删除掩盖"), 137: ("不让礼物", "不许诺无法承担"),
            138: ("不临时修改", "无效"), 139: ("必要余量", "不把最佳速度"),
            140: ("按权限", "明确各自责任"), 141: ("不愿展开", "不强迫表达"),
            142: ("不把一个人的意见", "不猜测"), 143: ("允许修订", "不为证明"),
        }
        for row, phrases in required.items():
            for text, phrase in zip(bank["rows"][row]["choice"][-2:], phrases):
                self.assertIn(phrase, text, row)
        for row, phrases in {
            144: ("不把点赞", "不追问", "不把一般支持", "不以公开点名"),
            145: ("不擅自", "不为展示牺牲安全", "不用一张照片", "保留必要安全"),
        }.items():
            choices = [load_topic("review")["choice"][row], *bank["rows"][row]["choice"]]
            self.assertGreaterEqual(len(choices), len(phrases))
            for text, phrase in zip(choices, phrases):
                self.assertIn(phrase, text, row)

    def test_practical_secondary_pool_never_falls_back_to_archived_guidance(self):
        topic = load_topic("review")
        for first in topic["entryRows"]:
            focused = deepcopy(topic)
            focused["entryRows"] = [first]
            with patch("story_narrative.load_topic", return_value=focused):
                result = render_story(f"practical-secondary-{first}", context("review"))
            ids = result["narrativeEvidence"]["fragmentIds"]
            self.assertEqual(ids[0], f"review:scene:{first}")
            self.assertIn(int(ids[4].rsplit(":", 1)[1]), topic["secondaryRows"])
            self.assertTrue(result["narrativeEvidence"]["selectionBasis"]["secondaryRestricted"])
        invalid = deepcopy(topic)
        invalid["entryRows"] = invalid["secondaryRows"] = [144]
        with patch("story_narrative.load_topic", return_value=invalid):
            with self.assertRaisesRegex(ValueError, "No eligible secondary story"):
                render_story("empty-practical-pool", context("review"))

    def test_portrait_catalog_assigns_all_rows_once_with_distinct_angles(self):
        topic = load_topic("portrait")
        self.assertEqual(topic["questionVersion"], "portrait-question-links-v3")
        self.assertEqual(len(topic["questionGroups"]), 8)
        rows = []
        for group in topic["questionGroups"]:
            self.assertTrue(group["title"].startswith("认识自己："))
            self.assertTrue(group["question"].endswith("？"))
            self.assertGreaterEqual(len(group["angles"]), 2)
            self.assertTrue(all(group["angles"].values()))
            rows.extend(index for values in group["angles"].values() for index in values)
        self.assertEqual(sorted(rows), list(range(96)))
        label_group = next(group for group in topic["questionGroups"]
                           if group["id"] == "context-before-label")
        self.assertIn(87, label_group["angles"]["description"])
        self.assertIn(61, label_group["angles"]["conditions"])
        self.assertIn(79, label_group["angles"]["participation"])
        self.assertFalse({22, 90} & {i for rows in label_group["angles"].values() for i in rows})
        groups = {group["id"]: {i for rows in group["angles"].values() for i in rows}
                  for group in topic["questionGroups"]}
        self.assertTrue({88, 91}.issubset(groups["adjust-conditions-before-self-blame"]))
        self.assertNotIn(83, groups["adjust-conditions-before-self-blame"])
        self.assertIn(83, groups["find-a-working-method"])
        self.assertNotIn(88, groups["find-a-working-method"])
        self.assertFalse({59, 73} & groups["find-a-working-method"])
        self.assertIn(59, groups["preference-without-audience"])
        self.assertIn(73, groups["context-before-label"])

    def test_review_catalog_covers_all_rows_and_has_practical_entries(self):
        topic = load_topic("review")
        self.assertEqual(topic["questionVersion"], "review-question-links-v5")
        self.assertEqual(len(topic["questionGroups"]), 16)
        rows = []
        reachable = set()
        for group in topic["questionGroups"]:
            self.assertTrue(group["title"].startswith("复盘："))
            self.assertTrue(group["question"].endswith("？"))
            self.assertGreaterEqual(len(group["angles"]), 2)
            entries = [i for indices in group["angles"].values() for i in indices if i in topic["entryRows"]]
            self.assertTrue(entries, group["id"])
            for angle, indices in group["angles"].items():
                self.assertTrue(indices, (group["id"], angle))
                rows.extend(indices)
                if any(entry not in indices for entry in entries):
                    reachable.update(indices)
        self.assertEqual(sorted(rows), list(range(182)))
        self.assertTrue(set(range(64)).issubset(reachable))
        group_for = {i: group["id"] for group in topic["questionGroups"]
                     for indices in group["angles"].values() for i in indices}
        self.assertNotEqual(group_for[65], group_for[60])
        self.assertEqual(group_for[65], group_for[79])
        self.assertEqual(group_for[60], group_for[111])
        self.assertEqual(group_for[53], group_for[95])
        self.assertNotEqual(group_for[88], group_for[84])
        self.assertNotEqual(group_for[75], group_for[43])
        self.assertNotEqual(group_for[117], group_for[110])
        self.assertEqual(group_for[61], group_for[109])
        self.assertEqual(group_for[128], group_for[129])
        self.assertEqual(group_for[130], group_for[131])
        self.assertEqual(group_for[134], "effort-and-recovery")
        self.assertEqual(group_for[136], "repair-without-new-harm")
        self.assertEqual(group_for[138], "check-a-promise")
        self.assertEqual(group_for[141], "help-with-permission")
        self.assertNotEqual(group_for[141], group_for[111])
        self.assertEqual(group_for[144], group_for[145])

    def test_review_expansion_adds_two_distinct_angles_to_every_question(self):
        topic = load_topic("review")
        for group in topic["questionGroups"]:
            additions = [(angle, row) for angle, rows in group["angles"].items()
                         for row in rows if 146 <= row < 178]
            self.assertEqual(len(additions), 2, group["id"])
            self.assertEqual(len({angle for angle, _ in additions}), 2, group["id"])
            for _, row in additions:
                self.assertIn(row, topic["entryRows"])
                self.assertIn(row, topic["secondaryRows"])

    def test_review_expansion_retains_consent_and_safety_in_both_wordings(self):
        topic, bank = load_topic("review"), load_variants("review")
        checks = {
            148: ("食品安全", "安全"),
            156: ("正式渠道", "官方"),
            158: ("自愿", "不把未回应写成赞成"),
            160: ("正式预警", "官方信息"),
            163: ("避免共享私人账号密码", "授权流程"),
            164: ("尊重拒绝", "明确回应"),
            165: ("不催促", "不索要无关隐私"),
            167: ("停止追问", "尊重对方"),
            168: ("不泄露", "相关规则"),
            169: ("限制共享范围", "有授权"),
            174: ("不追加披露", "说明限制"),
            175: ("征得物主同意", "不擅自拆修、不隐瞒"),
            176: ("低风险", "安全检查"),
        }
        for row, phrases in checks.items():
            for text, phrase in zip([topic["choice"][row], bank["rows"][row]["choice"][0]], phrases):
                self.assertIn(phrase, text, row)
        for row in range(146, 178):
            focused = deepcopy(topic)
            focused["entryRows"] = [row]
            with patch("story_narrative.load_topic", return_value=focused):
                story = render_story(f"review-expansion-boundary-{row}", context("review"))
            evidence = story["narrativeEvidence"]
            self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")
            self.assertTrue(evidence["selectionBasis"]["questionLink"]["applied"])
            self.assertNotEqual(*evidence["selectionBasis"]["questionLink"]["angles"])
            self.assertIn("不代表本人实际经历", evidence["selectionBasis"]["matchScope"])

    def test_review_new_full_paragraphs_keep_limits_in_every_added_choice(self):
        bank = load_variants("review")
        required = {
            148: ("食品安全", "使用反馈"),
            152: ("不逼人", "准备条件"),
            154: ("暂不下结论", "有害环境"),
            156: ("正式入口", "官方查询入口"),
            157: ("不擅删资料", "已经据此行动"),
            158: ("自愿", "不强迫"),
            159: ("正规渠道", "合法、安全且有权限"),
            160: ("正式预警", "实际条件"),
            163: ("不共享私人密码", "申请补齐"),
            164: ("不劝尝", "当下同意"),
            165: ("不要求公开私人细节", "勉强完成"),
            167: ("停止追问", "尊重对方"),
            168: ("获准的备用方式", "不明渠道"),
            169: ("按授权限制共享", "按规则处理旧资料"),
            170: ("操作安全", "不专挑有利片段"),
            174: ("不追加公开", "不许诺"),
            175: ("不隐瞒也不擅自拆修", "征得物主"),
            176: ("低风险", "不自行试验"),
            177: ("安全要求", "不")
        }
        for row in range(146, 178):
            for role in ("scene", "tension", "choice", "reflection"):
                self.assertGreaterEqual(len(bank["rows"][row][role]), 3)
        for row, phrases in required.items():
            for text, phrase in zip(bank["rows"][row]["choice"][-2:], phrases):
                self.assertIn(phrase, text, row)

    def test_review_pairs_share_a_question_without_changing_first_arc(self):
        topic = load_topic("review")
        legacy = {k: v for k, v in topic.items() if not k.startswith("question")}
        groups = {g["id"]: g for g in topic["questionGroups"]}
        reached = set()
        for axis in (*load_applicability()["axes"], "综合承接"):
            for index in range(100):
                seed = f"review-question-{index}"
                ctx = context("review", axis)
                result = render_story(seed, ctx)
                with patch("story_narrative.load_topic", return_value=legacy):
                    old = render_story(seed, ctx)
                evidence = result["narrativeEvidence"]
                ids = evidence["fragmentIds"]
                basis = evidence["selectionBasis"]
                link = basis["questionLink"]
                group = groups[link["id"]]
                self.assertTrue(link["applied"])
                self.assertEqual(link["version"], topic["questionVersion"])
                self.assertEqual(ids[:4], old["narrativeEvidence"]["fragmentIds"][:4])
                self.assertEqual(result["scenes"][:2], old["scenes"][:2])
                self.assertEqual(result["items"][0], old["items"][0])
                self.assertEqual(result["summary"], old["summary"])
                self.assertNotEqual(*link["angles"])
                self.assertEqual(result["title"], group["title"])
                for position, offset in enumerate((0, 4)):
                    row = int(ids[offset].rsplit(":", 1)[1])
                    self.assertIn(row, group["angles"][link["angles"][position]])
                self.assertIn(int(ids[0].rsplit(":", 1)[1]), topic["entryRows"])
                self.assertEqual(basis["counterAxisApplied"],
                                 basis["counterTag"] is not None and basis["counterTag"] in basis["selectedTags"][1])
                self.assertEqual(result, render_story(seed, ctx))
                reached.add(link["id"])
        self.assertEqual(reached, set(groups))

    def test_shared_question_preserves_first_arc_and_uses_another_angle(self):
        topic = load_topic("portrait")
        legacy = {key: value for key, value in topic.items() if not key.startswith("question")}
        groups = {group["id"]: group for group in topic["questionGroups"]}
        reached = set()
        for axis in (*load_applicability()["axes"], "综合承接"):
            for index in range(100):
                seed = f"question-link-{index}"
                ctx = context("portrait", axis)
                result = render_story(seed, ctx)
                with patch("story_narrative.load_topic", return_value=legacy):
                    old = render_story(seed, ctx)
                evidence = result["narrativeEvidence"]
                basis = evidence["selectionBasis"]
                link = basis["questionLink"]
                group = groups[link["id"]]
                ids = evidence["fragmentIds"]
                first, second = (int(ids[offset].rsplit(":", 1)[1]) for offset in (0, 4))
                self.assertEqual(ids[:4], old["narrativeEvidence"]["fragmentIds"][:4])
                self.assertEqual(result["scenes"][:2], old["scenes"][:2])
                self.assertEqual(result["summary"], old["summary"])
                self.assertEqual(result["items"][0], old["items"][0])
                self.assertTrue(link["applied"])
                self.assertIn(first, group["angles"][link["angles"][0]])
                self.assertIn(second, group["angles"][link["angles"][1]])
                self.assertNotEqual(*link["angles"])
                self.assertEqual(result["title"], group["title"])
                self.assertFalse(basis["reportContrast"]["reusedGroups"])
                self.assertEqual(basis["counterAxisApplied"],
                                 basis["counterTag"] is not None and basis["counterTag"] in basis["selectedTags"][1])
                reached.add(link["id"])
        self.assertEqual(reached, set(groups))

    def test_missing_counter_axis_does_not_break_question_link_or_claim_a_match(self):
        catalog = deepcopy(load_applicability())
        catalog["topics"]["portrait"] = [["A"] for _ in range(96)]
        with patch("story_narrative.load_applicability", return_value=catalog):
            result = render_story("no-counter-axis", context("portrait", "自主驱动"))
        basis = result["narrativeEvidence"]["selectionBasis"]
        self.assertTrue(basis["questionLink"]["applied"])
        self.assertFalse(basis["counterAxisApplied"])
        self.assertNotEqual(*basis["questionLink"]["angles"])

    def test_exhaustion_stays_in_question_and_discloses_conflict(self):
        catalog = deepcopy(load_applicability())
        catalog["overlapGroups"] = {"all-portrait": [f"portrait:{i}" for i in range(96)]}
        with patch("story_narrative.load_applicability", return_value=catalog):
            result = render_story("exhaustion", context("portrait"), used_groups={"all-portrait"})
        basis = result["narrativeEvidence"]["selectionBasis"]
        self.assertTrue(basis["questionLink"]["applied"])
        self.assertNotEqual(*basis["questionLink"]["angles"])
        self.assertEqual(basis["reportContrast"]["reusedGroups"], ["all-portrait"])

    def test_relationship_catalog_covers_every_scene_once(self):
        topic = load_topic("relationships")
        self.assertEqual(topic["questionVersion"], "relationships-question-links-v3")
        self.assertEqual(len(topic["questionGroups"]), 19)
        group_for = {}
        for group in topic["questionGroups"]:
            self.assertTrue(group["title"].startswith("关系："))
            self.assertTrue(group["question"].endswith("？"))
            self.assertGreaterEqual(len(group["angles"]), 2)
            for indices in group["angles"].values():
                self.assertTrue(indices)
                for index in indices:
                    self.assertNotIn(index, group_for)
                    group_for[index] = group["id"]
        self.assertEqual(sorted(group_for), list(range(143)))
        self.assertEqual(group_for[69], group_for[96])
        self.assertNotEqual(group_for[69], group_for[65])
        self.assertEqual(group_for[65], group_for[113])
        self.assertEqual(group_for[28], group_for[78])
        self.assertEqual(group_for[32], group_for[107])
        self.assertEqual(group_for[67], group_for[119])
        self.assertNotEqual(group_for[19], group_for[87])
        self.assertNotEqual(group_for[33], group_for[46])
        self.assertNotEqual(group_for[70], group_for[58])
        self.assertEqual(group_for[33], group_for[128])
        self.assertEqual(group_for[70], group_for[129])
        self.assertEqual(group_for[87], group_for[130])
        self.assertEqual(group_for[46], group_for[131])

    def test_ordinary_disagreement_never_pairs_with_pressure_or_safety_limits(self):
        topic = load_topic("relationships")
        ordinary = {33, 70, 124, 128, 129}
        boundaries = {46, 58, 87, 130, 131}
        for group, allowed in (("ordinary-disagreements", ordinary),
                               ("boundaries-under-pressure", boundaries)):
            for row in sorted(allowed):
                focused = deepcopy(topic)
                focused["entryRows"] = [row]
                with patch("story_narrative.load_topic", return_value=focused):
                    for axis in (*load_applicability()["axes"], "综合承接"):
                        for index in range(16):
                            result = render_story(f"relationship-boundaries-{index}", context("relationships", axis))
                            evidence = result["narrativeEvidence"]
                            link = evidence["selectionBasis"]["questionLink"]
                            self.assertEqual(link["id"], group)
                            self.assertNotEqual(*link["angles"])
                            for offset in (0, 4):
                                self.assertIn(int(evidence["fragmentIds"][offset].rsplit(":", 1)[1]), allowed)
                            self.assertEqual(evidence["evidenceType"], "editorial_hypothesis")

    def test_new_relationship_choices_preserve_boundaries_in_every_wording(self):
        topic, bank = load_topic("relationships"), load_variants("relationships")
        required = {
            128: ("取得相关人的同意", "未经相关人同意不公开", "公开时先询问本人"),
            129: ("有人不同意就继续商量", "不把安全问题当作试试看", "受影响者都接受且没有安全风险"),
            130: ("不分享密码或验证码", "不提供登录凭证", "不发送密码、验证码"),
            131: ("不要求即刻原谅", "允许慢慢回应或不再继续", "不被催促恢复亲近"),
            132: ("不把无关人员的联系方式一并转出", "不转发无关隐私", "保留相关人员的隐私范围"),
            133: ("不删去限制条件、不扩大原承诺", "未经确认不替别人增加保证", "不能省略的条件留在正文"),
            134: ("不用熬夜证明在意", "不默认一方长期牺牲休息", "不直接推断情分"),
            135: ("不凭猜测认定丢失或责任", "实际收到后再结束跟进", "不补写不存在的签收"),
            136: ("允许别人保留原活动", "尊重他人不便调整", "不要求谁用内疚证明珍惜"),
            137: ("不假装了解", "不把附和当作亲密证明", "不把不参与解释成否定这个人"),
            138: ("不把沉默当作同意", "需要本人同意的事项必须单独确认", "不以未开口替本人作出决定"),
            139: ("不编造依据填补空白", "不用含糊承诺拖延", "不伪装确定也不无声失约"),
        }
        for row, phrases in required.items():
            choices = [topic["choice"][row], *bank["rows"][row]["choice"]]
            self.assertGreaterEqual(len(choices), len(phrases))
            for choice, phrase in zip(choices, phrases):
                self.assertIn(phrase, choice, (row, choice))

    def test_relationship_pair_preserves_entry_and_uses_complementary_angle(self):
        topic = load_topic("relationships")
        legacy = {key: value for key, value in topic.items() if not key.startswith("question")}
        groups = {group["id"]: group for group in topic["questionGroups"]}
        reached = set()
        for axis in (*load_applicability()["axes"], "综合承接"):
            for index in range(100):
                seed = f"relationship-link-{index}"
                ctx = context("relationships", axis)
                result = render_story(seed, ctx)
                with patch("story_narrative.load_topic", return_value=legacy):
                    previous = render_story(seed, ctx)
                evidence = result["narrativeEvidence"]
                link = evidence["selectionBasis"]["questionLink"]
                self.assertTrue(link["applied"])
                group = groups[link["id"]]
                self.assertEqual(result["title"], group["title"])
                self.assertEqual(evidence["fragmentIds"][:4], previous["narrativeEvidence"]["fragmentIds"][:4])
                self.assertEqual(result["scenes"][:2], previous["scenes"][:2])
                self.assertEqual(result["summary"], previous["summary"])
                self.assertEqual(result["items"][0], previous["items"][0])
                self.assertNotEqual(*link["angles"])
                for position, offset in enumerate((0, 4)):
                    row = int(evidence["fragmentIds"][offset].rsplit(":", 1)[1])
                    self.assertIn(row, group["angles"][link["angles"][position]])
                self.assertEqual(result, render_story(seed, ctx))
                reached.add(link["id"])
        self.assertEqual(reached, set(groups))

    def test_other_sections_do_not_claim_question_coverage(self):
        for topic in load_applicability()["topics"]:
            if topic in {"portrait", "review", "relationships", "structure"}:
                continue
            result = render_story("unmapped-question", context(topic))
            link = result["narrativeEvidence"]["selectionBasis"]["questionLink"]
            self.assertFalse(link["applied"])
            self.assertIsNone(link["id"])
            self.assertEqual(link["angles"], [])


if __name__ == "__main__":
    unittest.main()
