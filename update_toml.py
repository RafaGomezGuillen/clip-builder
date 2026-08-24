#!/usr/bin/env python3
"""Add keys from config.example.toml without changing existing config values."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path


SECTION_RE = re.compile(r"^\s*\[([^\[].*[^\]])\]\s*(?:#.*)?$")
ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")


def parse_config(path: Path) -> dict:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SystemExit(f"Cannot read valid TOML from {path}: {error}") from error


def example_assignments(path: Path) -> dict[tuple[str, ...], list[str]]:
    assignments: dict[tuple[str, ...], list[str]] = {}
    section: tuple[str, ...] = ()
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        section_match = SECTION_RE.match(line)
        if section_match:
            section = tuple(part.strip() for part in section_match.group(1).split("."))
            continue
        assignment_match = ASSIGNMENT_RE.match(line)
        if assignment_match:
            key = assignment_match.group(1)
            assignments.setdefault(section + (key,), []).append(line)
    return assignments


def key_exists(config: dict, key_path: tuple[str, ...]) -> bool:
    value: object = config
    for part in key_path:
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return True


def section_ranges(lines: list[str]) -> dict[tuple[str, ...], tuple[int, int]]:
    ranges: dict[tuple[str, ...], tuple[int, int]] = {}
    headers: list[tuple[int, tuple[str, ...]]] = []
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match:
            section = tuple(part.strip() for part in match.group(1).split("."))
            headers.append((index, section))
    for position, (start, section) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        ranges[section] = (start, end)
    return ranges


def update_file(example_path: Path, config_path: Path) -> int:
    parse_config(example_path)
    current_config = parse_config(config_path)
    assignments = example_assignments(example_path)
    missing = [key_path for key_path in assignments if not key_exists(current_config, key_path)]
    if not missing:
        print(f"No missing keys in {config_path}")
        return 0

    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    additions: dict[tuple[str, ...], list[str]] = {}
    for key_path in missing:
        section, key = key_path[:-1], key_path[-1]
        additions.setdefault(section, []).extend(assignments[key_path])

    ranges = section_ranges(lines)
    root_additions = additions.pop((), [])
    if root_additions:
        first_table = next(
            (index for index, line in enumerate(lines) if SECTION_RE.match(line)),
            len(lines),
        )
        if first_table and lines[first_table - 1].strip():
            root_additions.insert(0, "\n")
        lines[first_table:first_table] = root_additions

    sections_to_append = [section for section in additions if section not in ranges]
    for section, (start, end) in sorted(ranges.items(), key=lambda item: item[1][0], reverse=True):
        if section not in additions:
            continue
        insertion = additions[section]
        if lines and lines[end - 1].strip():
            insertion.insert(0, "\n")
        lines[end:end] = insertion

    if sections_to_append:
        if lines and lines[-1].strip():
            lines.append("\n")
        for section in sections_to_append:
            lines.append(f"[{'.'.join(section)}]\n")
            lines.extend(additions[section])

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{config_path.name}.", suffix=".tmp", dir=config_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as temporary_file:
            temporary_file.writelines(lines)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, config_path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise

    updated_config = parse_config(config_path)
    if any(not key_exists(updated_config, key_path) for key_path in missing):
        raise SystemExit(f"Update verification failed for {config_path}")
    print(f"Added {len(missing)} missing key(s) to {config_path}")
    return len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add missing config.example.toml keys without overwriting config.toml."
    )
    root = Path(__file__).resolve().parent
    parser.add_argument("config", nargs="?", type=Path, default=root / "config.toml")
    parser.add_argument("example", nargs="?", type=Path, default=root / "config.example.toml")
    args = parser.parse_args()
    if not args.config.exists():
        print(f"{args.config} does not exist; copying {args.example}")
        shutil.copyfile(args.example, args.config)
        return 0
    return update_file(args.example, args.config)


if __name__ == "__main__":
    sys.exit(main())