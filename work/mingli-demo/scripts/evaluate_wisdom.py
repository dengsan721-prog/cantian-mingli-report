"""Reproducible public-sample narrative audit; does not write app history."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import random
import re
import statistics
import sys
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from narrative_engine import narrative_text
from narrative_diversity import TARGET
from report_engine import WISDOM_MODEL_VERSION, generate_report
from wisdom_narrative import load_wisdom


def shingles(text: str, width: int = 7) -> set[str]:
    return {text[i:i + width] for i in range(max(0, len(text) - width + 1))}


def implementation_manifest() -> dict[str, str]:
    system = ROOT.parent / "mingli-system"
    files = [ROOT / name for name in ("narrative_engine.py", "report_engine.py", "narrative_diversity.py",
                                     "narrative_expression.py", "story_narrative.py", "wisdom_narrative.py", "server.py",
                                     "app.js", "styles.css")]
    files += [Path(__file__).resolve(), ROOT / "tests" / "test_narrative_diversity.py",
              ROOT / "tests" / "test_reading_layout.py", ROOT / "tests" / "test_story_overlap.py",
              ROOT / "tests" / "test_narrative_followthrough.py",
              ROOT / "tests" / "test_scale_evaluation.py", ROOT / "scripts" / "audit_readability.py",
              ROOT / "scripts" / "smoke_wisdom.cjs"]
    files += [system / name for name in ("wisdom_knowledge.json", "expression_variants.json", "story_applicability.json",
                                        "youth_topics.json", "early_childhood_stories.json", "teen_stories.json")]
    files += sorted((system / "story_topics").glob("*.json"))
    files += sorted((system / "story_variants").glob("*.json"))
    return {str(path.relative_to(ROOT.parent)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files}


def clock_invariant(payload: dict, original: dict) -> bool:
    class LaterClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2040, 1, 1, tzinfo=tz)

    with patch("report_engine.datetime", LaterClock), patch("narrative_engine.datetime", LaterClock):
        later = generate_report(payload, use_wisdom=True)
    later["report"]["generatedAt"] = original["report"]["generatedAt"]
    return original == later


def compare(left: dict, right: dict) -> dict:
    a, b = narrative_text(left), narrative_text(right)
    sa, sb = shingles(a), shingles(b)
    intersection = len(sa & sb)
    ca = {s["narrativeEvidence"]["cardId"] for s in left["sections"] if "narrativeEvidence" in s}
    cb = {s["narrativeEvidence"]["cardId"] for s in right["sections"] if "narrativeEvidence" in s}
    fa = {fragment for s in left["sections"] for fragment in s.get("narrativeEvidence", {}).get("fragmentIds", [])}
    fb = {fragment for s in right["sections"] for fragment in s.get("narrativeEvidence", {}).get("fragmentIds", [])}
    ja = {(claim["id"], claim["claim"]) for claim in left.get("claims", []) if claim.get("confidence") != "计算结果"}
    jb = {(claim["id"], claim["claim"]) for claim in right.get("claims", []) if claim.get("confidence") != "计算结果"}
    # Containment exposes reuse hidden by simply increasing report length.
    return {
        "jaccard7": intersection / max(1, len(sa | sb)),
        "containment7": intersection / max(1, min(len(sa), len(sb))),
        "sequence": SequenceMatcher(None, a, b, autojunk=False).ratio(),
        "sharedCardFraction": len(ca & cb) / max(1, min(len(ca), len(cb))) if ca and cb else None,
        "sharedFragmentFraction": len(fa & fb) / max(1, min(len(fa), len(fb))) if fa and fb else None,
        "sharedJudgmentFraction": len(ja & jb) / max(1, min(len(ja), len(jb))) if ja and jb else None,
    }


def full_sections_text(report: dict) -> str:
    parts = []
    for section in report["sections"]:
        parts.extend(section.get(key, "") for key in ("title", "summary", "technical", "note", "insight", "listTitle"))
        parts.extend(section.get("scenes", []))
        parts.extend(section.get("items", []))
    return re.sub(r"\s+", "", "".join(parts))


def anonymize(report: dict, names: list[str]) -> dict:
    """Mask identity in prose without removing repeated advice or boundaries."""
    if isinstance(report, dict):
        return {key: anonymize(value, names) for key, value in report.items()}
    if isinstance(report, list):
        return [anonymize(value, names) for value in report]
    if isinstance(report, str):
        for name in sorted(names, key=len, reverse=True):
            report = report.replace(name, "[姓名]")
    return report


def report_html(person: dict, report: dict, version: str) -> str:
    esc = html.escape
    sections = []
    for section in report["sections"]:
        anchor = f' id="report-{esc(section["id"])}"' if "id" in section else ""
        evidence = section.get("narrativeEvidence")
        details = ""
        if evidence:
            details = f"<details><summary>本章的依据与适用条件</summary><p>{esc(evidence['interpretationBasis'])}</p><p>{esc(evidence['counterEvidence'])}</p><p>生活场景为假设示例；条目 {esc(evidence['cardId'])}。</p></details>"
        paragraphs = "".join(f"<p>{esc(p)}</p>" for p in section["scenes"])
        actions = []
        links = (evidence or {}).get("linkedActions", [])
        valid_sources = {s.get("id") for s in report["sections"] if s is not section}
        for index, text in enumerate(section["items"]):
            source = links[index]["sectionId"] if index < len(links) else None
            link = f' <a href="#report-{esc(source)}">回看前文</a>' if source and source in valid_sources else ""
            actions.append(f"<li>{esc(text)}{link}</li>")
        actions = "".join(actions)
        if section.get("narrativeLayout") == "paired_arcs":
            arcs = []
            for display_index, index in enumerate(section.get("narrativeArcOrder", [0, 1])):
                reflection = (section["summary"], section["insight"])[index]
                scenes = "".join(f"<p>{esc(p)}</p>" for p in section["scenes"][index * 2:index * 2 + 2])
                arcs.append(f"<article><h3>情境{'一' if display_index == 0 else '二'}</h3>{scenes}<p class='lead'>{esc(reflection)}</p><p><strong>试一步</strong> {esc(section['items'][index])}</p></article>")
            observations = "".join(f"<p>{esc(p)}</p>" for p in section["scenes"][4:])
            sections.append(f"<section{anchor}><h2>{esc(section['title'])}</h2>{''.join(arcs)}{observations}{details}<small>{esc(section['note'])}</small></section>")
        else:
            summary = f"<p class='lead'>{esc(section['summary'])}</p>" if section.get("summary") else ""
            insight = f"<blockquote>{esc(section['insight'])}</blockquote>" if section.get("insight") else ""
            list_title = f"<p>{esc(section['listTitle'])}</p>" if section.get("listTitle") else ""
            sections.append(f"<section{anchor}><h2>{esc(section['title'])}</h2>{summary}{paragraphs}{insight}{list_title}<ul>{actions}</ul>{details}<small>{esc(section['note'])}</small></section>")
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(person['name'])} · 叙事试读</title><style>
*{{box-sizing:border-box}}body{{margin:0;color:#272d35;background:#fafbfc;font-family:'Microsoft YaHei',sans-serif;line-height:1.9}}main{{max-width:820px;margin:auto;padding:30px 22px}}h1{{font-size:26px;overflow-wrap:anywhere}}h2{{font-size:21px;color:#314b61}}section{{padding:22px 0;border-top:1px solid #d8dfe6}}p{{margin:14px 0}}.lead{{font-weight:600}}blockquote{{margin:24px 0;padding:14px 20px;border-left:3px solid #b79554;background:#f0f4f7}}small{{color:#52606b}}a{{color:#255985;overflow-wrap:anywhere}}details{{margin:18px 0}}summary{{cursor:pointer}}@media(max-width:480px){{main{{padding:18px}}h1{{font-size:23px}}}}
</style><main><a href="index.html">返回样本目录</a><h1>{esc(person['name'])} · 生活智慧叙事试读</h1><p>{esc(version)} · {esc(person['birthDate'])} · {esc(person['birthplace'])} · 出生时刻未知</p><p>这是公开资料的叙事测试，不是本人认可的性格结论或人生预测。场景供反思，不表示其真实经历。</p><a href="{esc(person['source'], quote=True)}">出生资料来源</a>{''.join(sections)}</main></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cohort", choices=("development", "holdout", "combined"), default="development")
    parser.add_argument("--admission", action="store_true", help="Audit canonical drafts against previous reports; never resample failed drafts")
    parser.add_argument("--enforce-target", action="store_true")
    args = parser.parse_args()
    pool_path = ROOT / "tests" / ("public_narrative_pool.json" if args.cohort in {"development", "combined"} else "public_narrative_holdout.json")
    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    if args.output is None:
        suffix = "-admission" if args.admission else ""
        args.output = ROOT.parent / "mingli-system" / "evaluations" / f"wisdom-20260920-{args.cohort}{suffix}"
    people = random.Random(pool["seed"]).sample(sorted(pool["people"], key=lambda p: p["id"]), pool["sampleSize"])
    if args.cohort == "combined":
        holdout = json.loads((ROOT / "tests" / "public_narrative_holdout.json").read_text(encoding="utf-8"))
        people += random.Random(holdout["seed"]).sample(sorted(holdout["people"], key=lambda p: p["id"]), holdout["sampleSize"])
        pool = {**pool, "people": people, "scope": pool["scope"] + " 开发组六人后接留出组四人，检查组内与跨组全部45对；已被查看的留出组只作回归，不再声称是新盲测。"}
    args.output.mkdir(parents=True, exist_ok=True)
    runs = {"baseline": [], "candidate": []}
    links = []
    checks = []
    for person in people:
        year, month, day = map(int, person["birthDate"].split("-"))
        payload = {"name": person["name"], "gender": person["gender"], "calendarType": "solar", "year": year,
                   "month": month, "day": day, "birthplace": person["birthplace"], "timezone": person["timezone"],
                   "timeText": "", "calendarVerified": True, "timeStandardVerified": False, "events": []}
        baseline = generate_report(payload, use_wisdom=False)
        references = [narrative_text(report) for report in runs["candidate"]] if args.admission else []
        candidate = generate_report(payload, use_wisdom=True, narrative_references=references)
        renamed = generate_report({**payload, "name": "匿名样本"}, use_wisdom=True, narrative_references=references)
        checks.append({"person": person["id"], "unknownHourPreserved": candidate["chart"]["hour_pillar"] is None,
                       "renameInvariant": candidate["report"]["sections"] == renamed["report"]["sections"],
                       "clockInvariant": clock_invariant(payload, generate_report(payload, use_wisdom=True)),
                       "chartUnchanged": baseline["chart"] == candidate["chart"]})
        for version, generated in (("baseline", baseline), ("candidate", candidate)):
            runs[version].append(anonymize(generated["report"], [p["name"] for p in people]))
            file_name = f"{person['id']}-{version}.html"
            (args.output / file_name).write_text(report_html(person, generated["report"], version), encoding="utf-8")
            links.append(f"<li>{html.escape(person['name'])}：<a href='{file_name}'>{version}</a></li>")
        print(f"Generated {person['id']}", flush=True)
    metrics = {}
    for version, reports in runs.items():
        pairs = []
        for (i, left), (j, right) in combinations(enumerate(reports), 2):
            values = compare(left, right)
            pairs.append({"left": people[i]["id"], "right": people[j]["id"], **values})
        summary = {}
        for key in ("jaccard7", "containment7", "sequence", "sharedCardFraction", "sharedFragmentFraction", "sharedJudgmentFraction"):
            values = [p[key] for p in pairs if p[key] is not None]
            summary[key] = {"mean": statistics.mean(values), "max": max(values)} if values else None
        # Separately measure the complete visible sections, including fixed titles and boundaries.
        full_pairs = []
        for left, right in combinations(reports, 2):
            sets = [shingles(full_sections_text(report)) for report in (left, right)]
            full_pairs.append(len(sets[0] & sets[1]) / max(1, len(sets[0] | sets[1])))
        summary["fullSectionsJaccard7"] = {"mean": statistics.mean(full_pairs), "max": max(full_pairs)}
        lengths = [len(narrative_text(report)) for report in reports]
        summary["bodyCharacters"] = {"min": min(lengths), "max": max(lengths)}
        metrics[version] = {"summary": summary, "pairs": pairs}
    passed = metrics["candidate"]["summary"]["jaccard7"]["max"] < TARGET
    blockers = ["主题标签仅为编辑关联，个人提纲适配与整段改写阅读质量仍需验收", "本次仍为已查看的回归样本，新独立公开留出样本尚未验收"]
    if not passed:
        blockers.append(f"至少一对个性化正文七字片段Jaccard未低于{TARGET:.0%}")
    if not all(all(value for key, value in check.items() if key != "person") for check in checks):
        blockers.append("输入稳定性或历法不变性检查失败")
    result = {"evaluatedAt": datetime.now().astimezone().isoformat(), "seed": pool["seed"], "poolSize": len(pool["people"]),
              "sampleSize": len(people), "selectedIds": [p["id"] for p in people], "method": pool["method"], "cohort": args.cohort,
              "poolSha256": hashlib.sha256(json.dumps(pool, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "admissionGateEnabled": args.admission,
              "scope": pool["scope"], "knowledgeVersion": load_wisdom()["version"], "modelVersion": WISDOM_MODEL_VERSION,
              "implementationManifest": implementation_manifest(), "checks": checks, "metrics": metrics,
              "lexicalTarget": TARGET, "lexicalTargetPassed": passed, "releaseReady": not blockers, "releaseBlockers": blockers,
              "metricDefinitions": {"jaccard7": f"去姓名、去空白正文的连续七字集合交并比；保留标点；逐对最高值严格低于{TARGET:.0%}", "sharedCardFraction": "相同知识条目/主题占比，不是相同判断率", "sharedFragmentFraction": "相同库内段落ID占比；不把同义改写识别为不同思想", "sharedJudgmentFraction": "相同判断ID及未改写判断文本的交集/较少一方数量，不含历法计算事实；不是完整语义评测", "fullSectionsJaccard7": "包括标题、技术线索、边界、行动清单的完整章节正文，不含页眉、导航及模型附录"},
              "semanticSimilarity": "未进行独立语义模型评测；主题与段落ID重合只作可追溯代理，不等于语义相似度。",
              "readerAssessment": "未进行真人盲评；不将字数或自动检测视为趣味性、信心改善的证据。",
              "predictiveAccuracy": "本次不评估。未使用已知成就来证明出生盘预测。"}
    (args.output / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    table = ["|版本|正文七字重合均值|正文七字重合最高|短篇包含率最高|序列最高|完整章节重合最高|", "|---|---:|---:|---:|---:|---:|"]
    for version in metrics:
        s = metrics[version]["summary"]
        table.append(f"|{version}|{s['jaccard7']['mean']:.2%}|{s['jaccard7']['max']:.2%}|{s['containment7']['max']:.2%}|{s['sequence']['max']:.2%}|{s['fullSectionsJaccard7']['max']:.2%}|")
    report = "# 公开随机样本叙事审计\n\n" + pool["scope"] + "\n\n" + pool["method"] + "\n\n" + "\n".join(table)
    report += f"\n\n{TARGET:.0%}字面目标：{'达到' if passed else '未达到'}。实际样本与每对指标见 metrics.json。\n\n主题重合率不是判断重合率，段落ID重合可显示原文复用；两者均不等于语义相似度。未做真人阅读盲评，不宣称提高信心或预测准确性。\n\n人物事实只使用出生日期与城市；缺少时刻保持未知；不把来源中的成就放入输入。\n\n发布阻断：" + "；".join(blockers) + "。\n"
    (args.output / "README.md").write_text(report, encoding="utf-8")
    (args.output / "index.html").write_text(f"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>叙事样本对照</title><body style='max-width:800px;margin:30px auto;padding:20px;font-family:Microsoft YaHei,sans-serif;line-height:1.9'><h1>叙事样本对照</h1><p>{html.escape(args.cohort)} · {len(people)}人。候选版尚未替换正式报告。本文档用于阅读比较，不是人物性格事实。</p><ul>" + "".join(links) + "</ul><p><a href='metrics.json'>完整指标</a></p></body></html>", encoding="utf-8")
    history = {"evaluatedAt": result["evaluatedAt"], "cohort": args.cohort, "poolSha256": result["poolSha256"], "selectedIds": result["selectedIds"], "candidate": metrics["candidate"]["summary"], "lexicalTargetPassed": passed}
    with (args.output / "history.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(history, ensure_ascii=False) + "\n")
    print(json.dumps({k: v["summary"] for k, v in metrics.items()}, ensure_ascii=False, indent=2))
    if args.enforce_target and not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
