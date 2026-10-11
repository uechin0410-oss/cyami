"""FAQ ナレッジベースの読み込みと検索。

knowledge/ 配下の Markdown ファイルを「## 見出し」単位で 1 件の FAQ として扱う。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FaqEntry:
    id: str
    category: str
    question: str
    answer: str


def load_faq(directory: Path) -> list[FaqEntry]:
    entries: list[FaqEntry] = []
    for path in sorted(directory.glob("*.md")):
        category = path.stem
        sections = re.split(r"^## +", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
        for i, section in enumerate(sections[1:], start=1):
            question, _, answer = section.partition("\n")
            entries.append(
                FaqEntry(
                    id=f"{category}-{i}",
                    category=category,
                    question=question.strip(),
                    answer=answer.strip(),
                )
            )
    return entries


def _bigrams(text: str) -> set[str]:
    # 日本語は単語区切りがないため、文字 2-gram で類似度を測る
    chars = re.sub(r"\s+", "", text.lower())
    return {chars[i : i + 2] for i in range(len(chars) - 1)}


def search_faq(entries: list[FaqEntry], query: str, limit: int = 3) -> list[FaqEntry]:
    query_grams = _bigrams(query)
    if not query_grams:
        return []
    scored = []
    for entry in entries:
        # 質問文の一致を本文より重く見る
        score = 2 * len(query_grams & _bigrams(entry.question)) + len(
            query_grams & _bigrams(entry.answer)
        )
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]
