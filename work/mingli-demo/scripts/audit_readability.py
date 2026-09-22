"""Paired prose diagnostics, not a fluency score or a reader study."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_diversity import body_text


TERMS = ("可以", "如果", "若", "假如", "假设", "设想", "可能", "不必", "能够", "需要")


def diagnose(reports):
    texts = [body_text(row["report"]["sections"]) for row in reports]
    lengths = [len(text) for text in texts]
    sentences = [len(sentence) for text in texts for sentence in re.split(r"[。！？]", text) if sentence]
    return {
        "bodyCharacters": {"mean": statistics.mean(lengths), "min": min(lengths), "max": max(lengths)},
        "sentenceCharacters": {"mean": statistics.mean(sentences), "max": max(sentences)},
        "terms": {term: {"meanPerReport": sum(text.count(term) for text in texts) / len(texts),
                         "perThousandCharacters": sum(text.count(term) for text in texts) * 1000 / sum(lengths)}
                  for term in TERMS},
    }


def compare(before, after):
    if [row["id"] for row in before] != [row["id"] for row in after] or not before:
        raise ValueError("Reading comparison requires the same nonempty ordered cohort")
    unchanged = 0
    for left, right in zip(before, after):
        def fragments(row):
            return [(section["id"], section["narrativeEvidence"]["fragmentIds"]) for section in row["report"]["sections"]]
        unchanged += fragments(left) == fragments(right)
    return {"sampleSize": len(before), "before": diagnose(before), "after": diagnose(after),
            "unchangedOriginalFragmentSelections": unchanged,
            "scope": "Descriptive counts only. Terms overlap and include necessary uncertainty, permission and negation; lower is not automatically better. Sentence length is not comprehension. No human reader study, semantic similarity or predictive accuracy is measured."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    cohorts = [json.loads((path / "cohort.json").read_text(encoding="utf-8")) for path in (args.before, args.after)]
    if cohorts[0]["cohortSha256"] != cohorts[1]["cohortSha256"]:
        raise ValueError("Cannot compare different frozen cohorts")
    batches = []
    hashes = []
    for directory in (args.before, args.after):
        path = directory / "reports.jsonl.gz"
        hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            batches.append([json.loads(line) for line in stream])
    result = {**compare(*batches), "cohortSha256": cohorts[0]["cohortSha256"], "reportFileHashes": hashes,
              "scriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output = args.after / "reading-diagnostics.json"
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
