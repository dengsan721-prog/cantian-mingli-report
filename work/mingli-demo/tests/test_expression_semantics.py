from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_expression import express
from story_narrative import load_topic


class ExpressionSemanticsTests(unittest.TestCase):
    def test_comparison_relations_keep_authored_operator(self):
        sources = ["评论区并不等于完整受众。", "样本不等于总体。", "人数不等于人次。",
                   "两次测量并不等于两份独立证据。", "获得帮助并不等于交出决定权。"]
        for source in sources:
            for index in range(128):
                self.assertEqual(express(source, str(index), "comparison-relation"), source)

    def test_implications_and_questions_keep_authored_operator(self):
        sources = ["一次失误并不意味着所有努力都没有价值。",
                   "眼前没有结果并不意味着方向有错。", "这并不意味着必须答应，对吗？",
                   "不等于没有作用，但也不代表保证成功。",
                   "证据不足并不意味着结论必然错误，也并不等于结论成立。"]
        for source in sources:
            for index in range(128):
                self.assertEqual(express(source, str(index), "implication-relation"), source)

    def test_review_audience_paragraph_keeps_population_comparison(self):
        source = load_topic("review")["tension"][96]
        self.assertTrue(source.startswith("评论区并不等于完整受众"))
        for index in range(256):
            actual = express(source, str(index), "review:tension:96")
            self.assertTrue(actual.startswith("评论区并不等于完整受众"))
            self.assertNotIn("评论区并不意味着", actual)

    def test_assumption_nouns_are_not_rewritten_as_conditional_conjunctions(self):
        sources = ["估算需要说明假设。", "检查一个假设。", "条件变化后，这项假设不再成立。",
                   "对假设进行核验，不把假设当成事实。", "假设的成立依赖证据。",
                   "假设检验和假设条件需要分别说明。"]
        for source in sources:
            for index in range(128):
                self.assertEqual(express(source, str(index), "assumption-noun"), source)

    def test_conditional_and_mixed_sentences_retain_authored_meaning(self):
        for index in range(128):
            self.assertEqual(express("假设明天下雨，活动改期。", str(index), "assumption-clause"),
                             "假设明天下雨，活动改期。")
            actual = express("如果条件改变，重新核对假设。", str(index), "mixed-assumption")
            self.assertIn(actual, {"如果条件改变，重新核对假设。", "假如条件改变，重新核对假设。",
                                   "倘若条件改变，重新核对假设。"})

    def test_review_estimate_paragraph_keeps_assumption_noun_across_seeds(self):
        source = load_topic("review")["tension"][139]
        self.assertIn("估算需要说明假设", source)
        for index in range(256):
            actual = express(source, str(index), "review:tension:139")
            self.assertIn("估算需要说明假设", actual)
            self.assertNotIn("说明假如", actual)


if __name__ == "__main__":
    unittest.main()
