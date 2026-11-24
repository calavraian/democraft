#!/usr/bin/env python3
"""DemoCraft multi-language caption validator and SRT exporter (stdlib only)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MIN_SECONDS_PER_WORD = 0.25


@dataclass(frozen=True)
class CaptionCue:
    """Single timed subtitle entry."""

    start: float
    end: float
    text: str


def load_captions(path: Path, lang: str | None = None) -> list[CaptionCue]:
    """Loads caption cues from either a `captions.json` or a `storyboard.json` file."""
    if not path.is_file():
        raise FileNotFoundError(f"Captions file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict) and "languages" in raw:
        languages = raw["languages"]
        selected = lang or raw.get("default_lang") or next(iter(languages.keys()), None)
        if not selected or selected not in languages:
            raise KeyError(f"Language '{selected}' not found in {path} (available: {list(languages.keys())})")
        entries = languages[selected]
    elif isinstance(raw, dict) and isinstance(raw.get("scenes"), list):
        # Seamless support for unified storyboard.json as caption source
        from storyboard import extract_captions

        return extract_captions(raw, lang=lang)
    else:
        raise ValueError(
            "Invalid captions file: expected list, {'languages': {...}}, or storyboard {'scenes': [...]}."
        )

    cues: list[CaptionCue] = []
    for item in entries:
        cues.append(
            CaptionCue(
                start=float(item["start"]),
                end=float(item["end"]),
                text=str(item["text"]).strip(),
            )
        )
    return cues


def validate_cues(cues: list[CaptionCue]) -> dict[str, Any]:
    """Validates cue timestamps, overlaps, emptiness, and reading-speed floor."""
    errors: list[str] = []
    warnings: list[str] = []

    prev_end: float | None = None
    for idx, cue in enumerate(cues, start=1):
        if not cue.text:
            errors.append(f"Cue #{idx}: text cannot be empty.")
        if cue.start < 0:
            errors.append(f"Cue #{idx}: start time ({cue.start}s) cannot be negative.")
        if cue.end <= cue.start:
            errors.append(f"Cue #{idx}: end must be greater than start ({cue.start}s -> {cue.end}s).")
        if prev_end is not None and cue.start < prev_end:
            errors.append(
                f"Cue #{idx}: overlap detected (starts at {cue.start}s before previous end {prev_end}s)."
            )

        duration = cue.end - cue.start
        words = len(cue.text.split())
        if duration > 0 and words > 0:
            min_recommended = max(1.0, words * MIN_SECONDS_PER_WORD)
            if duration < min_recommended:
                warnings.append(
                    f"Cue #{idx}: fast reading speed ({words} words in {duration:.2f}s; recommend >= {min_recommended:.2f}s)."
                )
        prev_end = max(prev_end or 0.0, cue.end)

    return {
        "valid": len(errors) == 0,
        "count": len(cues),
        "errors": errors,
        "warnings": warnings,
    }


def format_srt_timestamp(seconds: float) -> str:
    """Formats float seconds into standard SubRip `HH:MM:SS,mmm`."""
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def export_srt(cues: list[CaptionCue], output_path: Path) -> Path:
    """Writes cues as a valid UTF-8 SubRip (`.srt`) subtitle file."""
    blocks: list[str] = []
    for idx, cue in enumerate(cues, start=1):
        ts = f"{format_srt_timestamp(cue.start)} --> {format_srt_timestamp(cue.end)}"
        blocks.append(f"{idx}\n{ts}\n{cue.text}\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(blocks), encoding="utf-8")
    return output_path


def cues_to_dicts(cues: list[CaptionCue]) -> list[dict[str, Any]]:
    """Serializes CaptionCue objects for JSON injection into HTML compositions."""
    return [asdict(c) for c in cues]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate DemoCraft captions and export .srt.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate caption timings and reading speed.")
    p_val.add_argument("captions_file", type=Path)
    p_val.add_argument("--lang", default=None)

    p_exp = sub.add_parser("export-srt", help="Export captions to .srt format.")
    p_exp.add_argument("captions_file", type=Path)
    p_exp.add_argument("--lang", default=None)
    p_exp.add_argument("--output", "-o", type=Path, required=True)

    args = parser.parse_args()
    cues = load_captions(args.captions_file, lang=args.lang)
    report = validate_cues(cues)

    if args.command == "validate":
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if not report["valid"]:
            sys.exit(1)
        return

    if not report["valid"]:
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    exported = export_srt(cues, args.output)
    print(f"Exported {len(cues)} cues to {exported}")


if __name__ == "__main__":
    main()
