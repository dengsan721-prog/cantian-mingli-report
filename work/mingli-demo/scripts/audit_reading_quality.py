"""Single-run reading diagnostics for generated report batches.

This is descriptive evidence, not a fluency score, reader study, or accuracy claim.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrative_diversity import body_text


TERMS = ("可以", "如果", "若", "假如", "假设", "设想", "可能", "不必", "能够", "需要")
SUSPICIOUS_PATTERNS = {
    "repeated_punctuation": r"[，。；、]{2,}",
    "double_de": r"的的",
    "double_le": r"了了",
    "double_bu": r"不不",
    "sentence_end_particle": r"。了",
}


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？!?]\s*", text) if part.strip()]


def chapter_text(section: dict) -> str:
    parts = [section.get("summary", ""), *section.get("scenes", []), section.get("insight", ""), *section.get("items", [])]
    return "\n".join(part for part in parts if part)


def diagnose(records: list[dict]) -> dict:
    texts = [body_text(row["report"]["sections"]) for row in records]
    all_sentences = [sentence for text in texts for sentence in sentences(text)]
    chapters = [chapter_text(section) for row in records for section in row["report"]["sections"]]
    chapter_lengths = [len(text) for text in chapters]
    short_sentences = [sentence for sentence in all_sentences if len(sentence) < 8 and re.search(r"[\u4e00-\u9fff]", sentence)]
    suspicious = {
        key: [sentence for sentence in all_sentences if re.search(pattern, sentence)]
        for key, pattern in SUSPICIOUS_PATTERNS.items()
    }
    chapter_counts = Counter(len(row["report"]["sections"]) for row in records)
    return {
        "sampleSize": len(records),
        "bodyCharacters": {
            "mean": statistics.mean(map(len, texts)),
            "min": min(map(len, texts)),
            "max": max(map(len, texts)),
        },
        "chapterCharacters": {
            "mean": statistics.mean(chapter_lengths),
            "min": min(chapter_lengths),
            "max": max(chapter_lengths),
        },
        "sentenceCharacters": {
            "mean": statistics.mean(map(len, all_sentences)),
            "min": min(map(len, all_sentences)),
            "max": max(map(len, all_sentences)),
        },
        "chapterCounts": dict(sorted(chapter_counts.items())),
        "shortSentenceCount": len(short_sentences),
        "shortSentenceSamples": short_sentences[:20],
        "suspiciousPatternCounts": {key: len(value) for key, value in suspicious.items()},
        "suspiciousPatternSamples": {key: value[:10] for key, value in suspicious.items() if value},
        "terms": {
            term: {
                "meanPerReport": sum(text.count(term) for text in texts) / len(texts),
                "perThousandCharacters": sum(text.count(term) for text in texts) * 1000 / sum(map(len, texts)),
            }
            for term in TERMS
        },
        "scope": (
            "Descriptive diagnostics over personalized body sections only. Short sentences can be useful headings "
            "or aphorisms; uncertainty and permission terms are often necessary. This is not a semantic similarity, "
            "human comprehension, predictive accuracy, or reader satisfaction study."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    reports_path = args.directory / "reports.jsonl.gz"
    with gzip.open(reports_path, "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    result = diagnose(records)
    result["provenance"] = {
        "reports.jsonl.gz": hashlib.sha256(reports_path.read_bytes()).hexdigest(),
        "audit_reading_quality.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    output = args.directory / "reading-quality.json"
    if output.exists():
        raise ValueError("Reading quality audit already exists; choose a fresh evaluation directory")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
