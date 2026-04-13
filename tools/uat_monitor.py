#!/usr/bin/env python3
"""Summarize and optionally tail Spaceship Sim UAT logs."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}


def colorize(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{ANSI[color]}{text}{ANSI['reset']}"


def latest_session_log() -> Path | None:
    if not LOG_DIR.exists():
        return None
    candidates = sorted(LOG_DIR.glob("session_*.log"))
    return candidates[-1] if candidates else None


@dataclass
class PatternRule:
    label: str
    severity: str
    pattern: re.Pattern[str]


RULES: list[PatternRule] = [
    PatternRule("traceback", "critical", re.compile(r"Traceback \(most recent call last\):")),
    PatternRule("python_error", "critical", re.compile(r"\b(ERROR|CRITICAL)\b")),
    PatternRule("process_exit", "critical", re.compile(r"subprocess exited unexpectedly", re.I)),
    PatternRule("mission_failure", "warning", re.compile(r"Mission FAILED:")),
    PatternRule("unauthorized", "warning", re.compile(r"Unauthorized|authentication failed", re.I)),
    PatternRule("disconnect", "warning", re.compile(r"Client disconnected:")),
    PatternRule("scenario_loaded", "info", re.compile(r"Loaded scenario: (?P<name>.+)$")),
    PatternRule("mission_success", "success", re.compile(r"Mission SUCCESS")),
    PatternRule("rcon_auth", "success", re.compile(r"RCON authenticated")),
    PatternRule("client_connected", "info", re.compile(r"Client connected:")),
    PatternRule("station_claim", "info", re.compile(r"claimed .* on ship", re.I)),
    PatternRule("sim_started", "info", re.compile(r"Simulation started with")),
    PatternRule("sim_stopped", "info", re.compile(r"Simulation stopped")),
]


@dataclass
class MonitorState:
    counts: Counter[str] = field(default_factory=Counter)
    scenarios: list[str] = field(default_factory=list)
    critical_lines: list[str] = field(default_factory=list)
    warning_lines: list[str] = field(default_factory=list)
    success_lines: list[str] = field(default_factory=list)
    info_lines: list[str] = field(default_factory=list)

    def record(self, severity: str, label: str, line: str) -> None:
        self.counts[severity] += 1
        self.counts[label] += 1

        bucket = {
            "critical": self.critical_lines,
            "warning": self.warning_lines,
            "success": self.success_lines,
            "info": self.info_lines,
        }[severity]
        bucket.append(line.rstrip())
        del bucket[:-12]


def classify_line(line: str) -> tuple[str | None, str | None]:
    for rule in RULES:
        if rule.pattern.search(line):
            return rule.severity, rule.label
    return None, None


def consume_lines(lines: Iterable[str], state: MonitorState) -> None:
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        severity, label = classify_line(line)
        if severity is None or label is None:
            continue

        state.record(severity, label, line)
        if label == "scenario_loaded":
            match = re.search(r"Loaded scenario: (?P<name>.+)$", line)
            if match:
                state.scenarios.append(match.group("name"))


def print_summary(log_path: Path, state: MonitorState, use_color: bool) -> None:
    print(colorize(f"UAT monitor summary for {log_path}", "bold", use_color))
    print(
        " ".join(
            [
                f"critical={state.counts['critical']}",
                f"warning={state.counts['warning']}",
                f"success={state.counts['success']}",
                f"info={state.counts['info']}",
            ]
        )
    )

    if state.scenarios:
        print("scenarios:")
        seen: set[str] = set()
        for name in state.scenarios:
            if name in seen:
                continue
            seen.add(name)
            print(f"  - {name}")

    for severity, title, color in (
        ("critical", "critical lines", "red"),
        ("warning", "warning lines", "yellow"),
        ("success", "success lines", "green"),
    ):
        lines = getattr(state, f"{severity}_lines")
        if not lines:
            continue
        print(colorize(f"{title}:", color, use_color))
        for line in lines[-8:]:
            print(f"  {line}")


def follow_file(log_path: Path, state: MonitorState, use_color: bool, fail_on_critical: bool) -> int:
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(0, os.SEEK_END)
        print(colorize(f"Following {log_path} (Ctrl+C to stop)", "cyan", use_color))
        try:
            while True:
                mark = handle.tell()
                line = handle.readline()
                if not line:
                    time.sleep(0.3)
                    handle.seek(mark)
                    continue

                consume_lines([line], state)
                severity, label = classify_line(line)
                if severity is None or label is None:
                    continue

                color = {
                    "critical": "red",
                    "warning": "yellow",
                    "success": "green",
                    "info": "blue",
                }[severity]
                prefix = f"[{severity.upper():8}]"
                print(colorize(prefix, color, use_color), line.rstrip())

                if fail_on_critical and severity == "critical":
                    print(colorize("Critical log pattern detected; stopping monitor.", "red", use_color))
                    return 1
        except KeyboardInterrupt:
            print()
            return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize or tail UAT logs")
    parser.add_argument("--log", type=Path, help="Specific log file to inspect")
    parser.add_argument("--follow", action="store_true", help="Tail the log after printing the summary")
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit non-zero if a critical pattern appears",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_path = args.log or latest_session_log()
    if log_path is None or not log_path.exists():
        print("No session log found. Start the stack first so logs/session_*.log exists.", file=sys.stderr)
        return 1

    state = MonitorState()
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        consume_lines(handle, state)

    use_color = not args.no_color and sys.stdout.isatty()
    print_summary(log_path, state, use_color)

    if args.follow:
        return follow_file(log_path, state, use_color, args.fail_on_critical)

    if args.fail_on_critical and state.counts["critical"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
