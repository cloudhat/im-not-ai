#!/usr/bin/env python3
"""Report deterministic before/after taxonomy counts as one JSON value."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from detection_registry import (
    CATEGORY_ORDER,
    DETECTORS,
    DetectionContext,
    count_text,
    validate_registry,
)


_HERE = os.path.dirname(os.path.abspath(__file__))
_TAXONOMY = os.path.abspath(
    os.path.join(_HERE, "..", "skills", "humanize-korean", "references", "ai-tell-taxonomy.md")
)
_HEADING_RE = re.compile(r"^### ([A-J]-\d+)\.", re.MULTILINE)
_GENRES = ("칼럼", "리포트", "블로그", "공적")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as file:
        return file.read()


def _taxonomy_ids() -> list[tuple[str, str]]:
    return [(match.group(1), match.group(1)[0]) for match in _HEADING_RE.finditer(_read(_TAXONOMY))]


def _by_category(by_id: dict[str, int]) -> dict[str, int]:
    return {
        category: sum(
            by_id[detector.pattern_id]
            for detector in DETECTORS
            if detector.category == category
        )
        for category in CATEGORY_ORDER
    }


def build_report(before: str, after: str, context: DetectionContext) -> dict:
    validate_registry(_taxonomy_ids())
    before_by_id = count_text(before, context)
    after_by_id = count_text(after, context)
    return {
        "schema_version": 1,
        "context": {
            "genre": context.genre,
            "translated": context.translated,
        },
        "before": {
            "by_id": before_by_id,
            "by_category": _by_category(before_by_id),
        },
        "after": {
            "by_id": after_by_id,
            "by_category": _by_category(after_by_id),
        },
    }


def main(argv: list[str] | None = None) -> int:
    try:
        parser = _ArgumentParser(description="humanize-korean 탐지 건수 reporter")
        parser.add_argument("--before", required=True)
        parser.add_argument("--after", required=True)
        parser.add_argument("--genre", required=True, choices=_GENRES)
        parser.add_argument("--translated", action="store_true")
        args = parser.parse_args(argv)
        report = build_report(
            _read(args.before),
            _read(args.after),
            DetectionContext(args.genre, args.translated),
        )
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 3

    json.dump(report, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
