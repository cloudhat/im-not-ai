#!/usr/bin/env python3
"""Create one Codex humanize run and preserve its input byte-for-byte."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys


def _input_bytes(input_file: str | None) -> tuple[bytes, str | None]:
    if input_file is None:
        data = sys.stdin.buffer.read()
        source_path = None
    else:
        source_path = os.path.abspath(input_file)
        with open(source_path, "rb") as file:
            data = file.read()
    if not data:
        raise ValueError("입력이 비어 있다")
    data.decode("utf-8")
    return data, source_path


def _reserve_run_dir(workspace: str, day: str) -> tuple[str, str]:
    os.makedirs(workspace, exist_ok=True)
    pattern = re.compile(rf"^{re.escape(day)}-(\d{{3}})$")
    numbers = [
        int(match.group(1))
        for name in os.listdir(workspace)
        if (match := pattern.match(name)) and os.path.isdir(os.path.join(workspace, name))
    ]
    number = max(numbers, default=0) + 1
    while True:
        run_id = f"{day}-{number:03d}"
        run_dir = os.path.join(workspace, run_id)
        try:
            os.mkdir(run_dir)
            return run_id, run_dir
        except FileExistsError:
            number += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex humanize run 준비")
    parser.add_argument("--input-file")
    args = parser.parse_args(argv)

    try:
        data, source_path = _input_bytes(args.input_file)
        workspace = os.path.abspath(os.path.join(os.getcwd(), "_workspace"))
        run_id, run_dir = _reserve_run_dir(workspace, dt.date.today().isoformat())
        input_path = os.path.join(run_dir, "01_input.md")
        with open(input_path, "xb") as file:
            file.write(data)
        result = {
            "schema_version": 1,
            "run_id": run_id,
            "run_dir": run_dir,
            "input_path": input_path,
            "draft_path": os.path.join(run_dir, ".draft.md"),
            "review_path": os.path.join(run_dir, "review.json"),
            "source_path": source_path,
        }
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 3

    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
