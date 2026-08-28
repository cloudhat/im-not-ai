#!/usr/bin/env python3
"""Validate a Codex humanize draft and atomically create ``final.md``."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile

from detection_registry import CATEGORY_ORDER, DETECTOR_BY_ID, S1_IDS, S2_IDS
from verify_change_rate import evaluate_change_rate


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPORTER = os.path.join(_HERE, "report_detection_counts.py")
_CHECK_LABELS = {
    "1": "고유명사·수치·날짜·인용·내용 앵커 100% 보존",
    "2": "변경률 30% 이하",
    "3": "장르 이탈 없음",
    "4": "register 보존",
    "5": "S1 잔존 0건",
    "6": "인공 표현 추가 없음",
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as file:
        return file.read()


def _atomic_write(path: str, text: str, *, preserve_mode_from: str | None = None) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    descriptor, temporary = tempfile.mkstemp(prefix=".humanize-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        if preserve_mode_from is not None:
            mode = stat.S_IMODE(os.stat(preserve_mode_from).st_mode)
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _review(path: str) -> tuple[dict[str, bool], list[dict[str, str]]]:
    value = json.loads(_read(path))
    if not isinstance(value, dict):
        raise ValueError("review.json 최상위 값은 object여야 한다")
    checks = value.get("self_check")
    if not isinstance(checks, dict) or set(checks) != {"1", "3", "4", "6"}:
        raise ValueError("review.json self_check는 1·3·4·6 판정을 모두 가져야 한다")
    if any(type(checks[key]) is not bool for key in checks):
        raise ValueError("review.json self_check 판정은 boolean이어야 한다")
    highlights = value.get("highlights")
    if not isinstance(highlights, list) or not 3 <= len(highlights) <= 5:
        raise ValueError("review.json highlights는 3~5건이어야 한다")
    normalized: list[dict[str, str]] = []
    for index, highlight in enumerate(highlights, 1):
        if not isinstance(highlight, dict) or set(highlight) != {"id", "before", "after"}:
            raise ValueError(f"highlight {index}는 id·before·after만 가져야 한다")
        if highlight["id"] not in DETECTOR_BY_ID:
            raise ValueError(f"highlight {index}의 taxonomy ID가 유효하지 않다")
        if not all(isinstance(highlight[key], str) for key in ("id", "before", "after")):
            raise ValueError(f"highlight {index} 값은 문자열이어야 한다")
        if not highlight["before"] or not highlight["after"]:
            raise ValueError(f"highlight {index}의 before·after는 비어 있을 수 없다")
        if len(highlight["before"]) > 100 or len(highlight["after"]) > 100:
            raise ValueError(f"highlight {index}의 before·after는 각각 100자 이하여야 한다")
        normalized.append(highlight)
    return checks, normalized


def _report(
    before_path: str,
    draft_path: str,
    genre: str,
    translated: bool,
) -> dict:
    command = [
        sys.executable,
        _REPORTER,
        "--before",
        before_path,
        "--after",
        draft_path,
        "--genre",
        genre,
    ]
    if translated:
        command.append("--translated")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        reason = completed.stderr.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"report_detection_counts.py 실패: {reason}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("report_detection_counts.py가 순수 JSON을 반환하지 않았다") from error


def _grade(
    rate: float,
    s1_after: int,
    s2_after: int,
    passed: int,
) -> tuple[str, str]:
    if rate > 0.50 or s1_after >= 3:
        grade = "D"
    elif rate > 0.30 or 1 <= s1_after <= 2 or passed <= 4 or s2_after > 4:
        grade = "C"
    elif s1_after == 0 and s2_after <= 2 and 0.10 <= rate <= 0.25 and passed == 6:
        grade = "A"
    elif s1_after == 0 and s2_after <= 4 and passed >= 5:
        grade = "B"
    else:
        grade = "C"
    reason = (
        f"{grade} — S1 {s1_after}건, S2 {s2_after}건, "
        f"변경률 {rate * 100:.1f}%, 자체검증 {passed}/6."
    )
    return grade, reason


def _display_categories(report: dict) -> list[dict[str, int | str]]:
    before = report["before"]["by_category"]
    after = report["after"]["by_category"]
    active = [category for category in CATEGORY_ORDER if before[category] or after[category]]
    active.sort(key=lambda category: (-before[category], -after[category], CATEGORY_ORDER.index(category)))
    return [
        {"category": category, "before": before[category], "after": after[category]}
        for category in active[:6]
    ]


def _summary(
    run_id: str,
    before: str,
    draft: str,
    rate: float,
    grade: str,
    grade_reason: str,
    report: dict,
    checks: dict[str, bool],
    highlights: list[dict[str, str]],
    warning: str | None,
) -> str:
    lines = [
        "<!-- HUMANIZE-SUMMARY v2",
        f"run_id: {run_id}",
        "metrics:",
        f"  char_in: {len(before)}",
        f"  char_out: {len(draft)}",
        f"  change_rate: {rate * 100:.1f}%",
        f"  self_check: {sum(checks.values())}/6",
        f"  grade: {grade}",
        "categories:",
    ]
    for category in CATEGORY_ORDER:
        before_count = report["before"]["by_category"][category]
        after_count = report["after"]["by_category"][category]
        lines.append(f"  {category}: {before_count} -> {after_count}")
    lines.append("self_check:")
    for key in "123456":
        mark = "pass" if checks[key] else "fail"
        lines.append(f"  {key}: {mark} — {_CHECK_LABELS[key]}")
    lines.append("highlights:")
    for highlight in highlights:
        lines.extend(
            (
                f"  - id: {highlight['id']}",
                f"    before: {json.dumps(highlight['before'], ensure_ascii=False)}",
                f"    after: {json.dumps(highlight['after'], ensure_ascii=False)}",
            )
        )
    lines.append(f"grade_reason: {json.dumps(grade_reason, ensure_ascii=False)}")
    if warning:
        lines.append(f"warning: {json.dumps(warning, ensure_ascii=False)}")
    lines.append("-->")
    return "\n".join(lines)


def _finalize(args: argparse.Namespace) -> dict:
    run_dir = os.path.abspath(args.run_dir)
    run_id = os.path.basename(run_dir)
    before_path = os.path.join(run_dir, "01_input.md")
    draft_path = os.path.join(run_dir, ".draft.md")
    review_path = os.path.join(run_dir, "review.json")
    final_path = os.path.join(run_dir, "final.md")

    before = _read(before_path)
    draft = _read(draft_path).rstrip()
    if not draft:
        raise ValueError(".draft.md가 비어 있다")
    if "HUMANIZE-SUMMARY" in draft:
        raise ValueError(".draft.md에는 HUMANIZE-SUMMARY를 넣지 않는다")
    model_checks, highlights = _review(review_path)
    report = _report(before_path, draft_path, args.genre, args.translated)
    rate, _verdict, _gate_code = evaluate_change_rate(before, draft)

    after_by_id = report["after"]["by_id"]
    s1_after = sum(after_by_id[pattern_id] for pattern_id in S1_IDS)
    s2_after = sum(after_by_id[pattern_id] for pattern_id in S2_IDS)
    checks = {
        "1": model_checks["1"],
        "2": rate <= 0.30,
        "3": model_checks["3"],
        "4": model_checks["4"],
        "5": s1_after == 0,
        "6": model_checks["6"],
    }
    passed = sum(checks.values())
    grade, grade_reason = _grade(rate, s1_after, s2_after, passed)
    if rate > 0.50:
        warning = "변경률 50% 초과. 등급 D 결과를 유지했으므로 사람 검토가 필요하다."
    elif rate > 0.30:
        warning = "변경률 30% 초과. 등급 상한을 C로 적용했다."
    else:
        warning = None
    summary = _summary(
        run_id,
        before,
        draft,
        rate,
        grade,
        grade_reason,
        report,
        checks,
        highlights,
        warning,
    )
    final_text = f"{draft}\n\n{summary}\n"
    _atomic_write(final_path, final_text)

    original_updated = False
    if args.update_original:
        original_path = os.path.abspath(args.update_original)
        if not os.path.isfile(original_path):
            raise ValueError(f"원본 파일이 없다: {original_path}")
        _atomic_write(original_path, f"{draft}\n", preserve_mode_from=original_path)
        original_updated = True

    os.unlink(draft_path)
    os.unlink(review_path)
    recommendation = (
        None
        if grade == "A"
        else "정밀 검증은 Claude Code의 정밀 모드(3콜)를 권장한다."
    )
    return {
        "schema_version": 1,
        "status": "completed",
        "run_id": run_id,
        "final_path": final_path,
        "change_rate": round(rate * 100, 1),
        "grade": grade,
        "self_check": f"{passed}/6",
        "categories": _display_categories(report),
        "highlight": highlights[0],
        "warning": warning,
        "recommendation": recommendation,
        "original_updated": original_updated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex humanize run 최종화")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--genre", required=True, choices=("칼럼", "리포트", "블로그", "공적"))
    parser.add_argument("--translated", action="store_true")
    parser.add_argument("--update-original")
    args = parser.parse_args(argv)
    try:
        result = _finalize(args)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 3
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
