from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path


EXPRESSION_VERSION = "expression-v13"


@lru_cache(maxsize=1)
def expression_rules() -> tuple[dict[str, list[str]], re.Pattern[str]]:
    source = Path(__file__).resolve().parent.parent / "mingli-system" / "expression_variants.json"
    phrases = json.loads(source.read_text(encoding="utf-8"))["phrases"]
    guards = {"有时": "有时(?!候)", "多一点": "多一点(?!点)", "少一点": "少一点(?!点)",
              "不一定": "(?<!并)不一定", "说明": "(?<!分别)说明(?!(?:书|假设))",
              "核对": "核对(?!假设)", "检查": "检查(?!一个假设|假设)",
              "保留": "保留(?!(?:意思|意见))",
              "求助": "求助(?!(?:消息|记录|信息|电话|信|者|渠道))"}
    pattern = re.compile("|".join(guards.get(key, re.escape(key)) for key in sorted(phrases, key=len, reverse=True)))
    return phrases, pattern


def express(text: str, seed: str, fragment_id: str) -> str:
    """One pass over authored prose only; never transform supplied personal facts."""
    phrases, pattern = expression_rules()

    def replace(match: re.Match[str]) -> str:
        choices = phrases[match.group()]
        # Do not add another attributive marker after an existing modifier.
        if match.start() and text[match.start() - 1] == "的":
            choices = [choice for choice in choices if "的" not in choice] or [match.group()]
        key = f"{seed}|{fragment_id}|{match.start()}|{match.group()}"
        index = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % len(choices)
        return choices[index]

    return pattern.sub(replace, text)
