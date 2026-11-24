#!/usr/bin/env python3
"""DemoCraft minimal storyboard validator & caption extractor (Python stdlib only).

Keeps scene planning deliberately lightweight and flexible so AI agents retain
broad creative freedom while enforcing clean timing, optional freeze/stop cues,
and graceful duration bounds across `promo` and `tutorial` modes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from captions import CaptionCue, cues_to_dicts, export_srt, validate_cues

# Mode duration policies: (soft_cap_s, grace_margin_s)
MODE_DURATION_LIMITS: dict[str, tuple[float, float]] = {
    "promo": (25.0, 3.0),      # target 15-25s, internal grace up to 28s
    "tutorial": (150.0, 10.0), # target 45-150s (2m30s), internal grace up to 160s
}

VALID_FREEZE_MODES = ("before_action", "after_action", "hold")
CAPTION_EDGE_PADDING_S = 0.2


def load_storyboard(path: Path) -> dict[str, Any]:
    """Loads a minimal `storyboard.json` file."""
    if not path.is_file():
        raise FileNotFoundError(f"Storyboard file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise ValueError("Invalid storyboard.json: expected object with a 'scenes' list.")
    return data


def extract_captions(data: dict[str, Any], lang: str | None = None) -> list[CaptionCue]:
    """Derives timed CaptionCue entries directly from storyboard scenes."""
    selected_lang = lang or data.get("default_lang") or "es"
    cues: list[CaptionCue] = []
    cursor = 0.0

    for scene in data.get("scenes", []):
        duration = float(scene.get("duration_s", 0.0))
        scene_start = cursor
        scene_end = cursor + duration
        cursor = scene_end

        scene_caps = scene.get("captions")
        text = ""
        if isinstance(scene_caps, dict):
            text = str(scene_caps.get(selected_lang, "")).strip()
        elif isinstance(scene_caps, str):
            text = scene_caps.strip()

        if not text or duration <= 0:
            continue

        pad = min(CAPTION_EDGE_PADDING_S, duration * 0.15)
        cues.append(
            CaptionCue(
                start=round(scene_start + pad, 3),
                end=round(scene_end - pad, 3),
                text=text,
            )
        )
    return cues


def validate_storyboard(data: dict[str, Any], lang: str | None = None) -> dict[str, Any]:
    """Validates minimal storyboard structure, freeze stops, and grace duration limits."""
    errors: list[str] = []
    warnings: list[str] = []

    mode = str(data.get("mode", "promo")).strip().lower()
    if mode not in MODE_DURATION_LIMITS:
        errors.append(
            f"Unsupported mode '{mode}'. Choose from: {', '.join(MODE_DURATION_LIMITS)}."
        )
        soft_cap, grace = (25.0, 3.0)
    else:
        soft_cap, grace = MODE_DURATION_LIMITS[mode]

    scenes = data.get("scenes", [])
    if not scenes:
        errors.append("Storyboard must include at least one scene.")

    seen_ids: set[str] = set()
    total_duration = 0.0
    total_freeze = 0.0

    for idx, scene in enumerate(scenes, start=1):
        sid = str(scene.get("id", "")).strip()
        if not sid:
            errors.append(f"Scene #{idx}: missing required 'id'.")
        elif sid in seen_ids:
            errors.append(f"Scene #{idx}: duplicate scene id '{sid}'.")
        else:
            seen_ids.add(sid)

        dur = float(scene.get("duration_s", 0.0))
        if dur <= 0:
            errors.append(f"Scene '{sid or idx}': duration_s must be positive (got {dur}).")
        else:
            total_duration += dur

        if "freeze_s" in scene and scene["freeze_s"] is not None:
            freeze_s = float(scene["freeze_s"])
            if freeze_s < 0 or (dur > 0 and freeze_s >= dur):
                errors.append(
                    f"Scene '{sid or idx}': freeze_s ({freeze_s}s) must be >= 0 and < duration_s ({dur}s)."
                )
            else:
                total_freeze += freeze_s

        if "freeze_mode" in scene and scene["freeze_mode"] is not None:
            fmode = str(scene["freeze_mode"]).strip().lower()
            if fmode not in VALID_FREEZE_MODES:
                errors.append(
                    f"Scene '{sid or idx}': invalid freeze_mode '{fmode}'. "
                    f"Expected one of: {', '.join(VALID_FREEZE_MODES)}."
                )

    max_with_grace = soft_cap + grace
    suggest_split = False
    if total_duration <= soft_cap:
        duration_status = "within_target"
    elif total_duration <= max_with_grace:
        duration_status = "within_grace"
        warnings.append(
            f"Total duration {total_duration:.1f}s is slightly above the {soft_cap:.0f}s {mode} soft cap "
            f"but accepted within the +{grace:.0f}s internal grace margin."
        )
    else:
        duration_status = "exceeds_grace"
        suggest_split = True
        warnings.append(
            f"Total duration {total_duration:.1f}s exceeds the {mode} limit + grace ({max_with_grace:.0f}s); "
            "consider splitting into a multi-part series or tightening scenes."
        )

    cues = extract_captions(data, lang=lang)
    if cues:
        cap_report = validate_cues(cues)
        warnings.extend(cap_report["warnings"])
        errors.extend(cap_report["errors"])

    return {
        "valid": len(errors) == 0,
        "mode": mode,
        "scene_count": len(scenes),
        "total_duration_s": round(total_duration, 2),
        "total_freeze_s": round(total_freeze, 2),
        "soft_cap_s": soft_cap,
        "grace_limit_s": max_with_grace,
        "duration_status": duration_status,
        "suggest_split": suggest_split,
        "caption_count": len(cues),
        "errors": errors,
        "warnings": warnings,
    }


def export_storyboard_srt(data: dict[str, Any], output_path: Path, lang: str | None = None) -> Path:
    """Exports storyboard scene captions directly to a SubRip `.srt` file."""
    cues = extract_captions(data, lang=lang)
    return export_srt(cues, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate DemoCraft storyboard.json and export captions.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate storyboard pacing, freeze stops, and captions.")
    p_val.add_argument("storyboard_file", type=Path)
    p_val.add_argument("--lang", default=None)

    p_exp = sub.add_parser("export-captions", help="Derive captions.json and/or .srt from storyboard.")
    p_exp.add_argument("storyboard_file", type=Path)
    p_exp.add_argument("--lang", default=None)
    p_exp.add_argument("--out-json", type=Path, default=None)
    p_exp.add_argument("--out-srt", type=Path, default=None)

    args = parser.parse_args()
    data = load_storyboard(args.storyboard_file)
    report = validate_storyboard(data, lang=args.lang)

    if args.command == "validate":
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if not report["valid"]:
            sys.exit(1)
        return

    if not report["valid"]:
        print(json.dumps(report, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    cues = extract_captions(data, lang=args.lang)
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(cues_to_dicts(cues), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Exported {len(cues)} cues JSON to {args.out_json}")
    if args.out_srt:
        export_srt(cues, args.out_srt)
        print(f"Exported {len(cues)} cues SRT to {args.out_srt}")


if __name__ == "__main__":
    main()
