#!/usr/bin/env python3
"""DemoCraft zero-bloat skill registrar & installer (Python stdlib only).

Auto-detects installed AI coding agents (Antigravity, Claude Code, Codex,
Cursor/OpenCode) and registers DemoCraft via symlink (default) or clean copy,
then runs `probe.py` to verify local readiness — zero npx, zero global packages.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from probe import probe_environment

SKILL_NAME = "democraft"

# Mapping: key -> (display_name, detection_config_root, skills_parent_dir)
AGENT_TARGETS: dict[str, tuple[str, str, str]] = {
    "antigravity": ("Google Antigravity", ".gemini/config", ".gemini/config/skills"),
    "claude": ("Claude Code", ".claude", ".claude/skills"),
    "codex": ("OpenAI Codex", ".codex", ".codex/skills"),
    "cursor": ("Cursor / OpenCode", ".agents", ".agents/skills"),
}

COPY_EXCLUDE_NAMES = {
    ".git",
    ".DS_Store",
    "Thumbs.db",
    "__pycache__",
    ".pytest_cache",
    "work",
    "sandbox",
}


def detect_installed_agents(home: Path) -> list[str]:
    """Returns supported agent keys whose configuration root exists under `home`."""
    detected: list[str] = []
    for key, (_label, config_root, _skills_dir) in AGENT_TARGETS.items():
        if (home / config_root).exists():
            detected.append(key)
    return detected


def resolve_target_dirs(
    agents: list[str],
    home: Path | None = None,
    project_dir: Path | None = None,
) -> list[tuple[str, Path]]:
    """Resolves requested agent selectors (`auto`, `all`, or explicit names) to skill target paths."""
    resolved_home = home if home is not None else Path.home()
    targets: list[tuple[str, Path]] = []
    seen_paths: set[Path] = set()

    def _add(agent_key: str, dest: Path) -> None:
        if dest not in seen_paths:
            seen_paths.add(dest)
            targets.append((agent_key, dest))

    if project_dir is not None:
        _add("project", project_dir.resolve() / ".agents" / "skills" / SKILL_NAME)

    normalized: list[str] = []
    for raw in agents:
        for item in str(raw).split(","):
            tok = item.strip().lower()
            if tok:
                normalized.append(tok)

    if not normalized:
        return targets

    expanded: list[str] = []
    for tok in normalized:
        if tok == "auto":
            detected = detect_installed_agents(resolved_home)
            expanded.extend(detected if detected else ["cursor"])
        elif tok == "all":
            expanded.extend(AGENT_TARGETS.keys())
        elif tok in AGENT_TARGETS:
            expanded.append(tok)
        else:
            raise ValueError(
                f"Unsupported agent '{tok}'. Choose auto, all, or: {', '.join(AGENT_TARGETS)}."
            )

    for key in expanded:
        _label, _cfg, skills_rel = AGENT_TARGETS[key]
        _add(key, resolved_home / skills_rel / SKILL_NAME)

    return targets


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in COPY_EXCLUDE_NAMES or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
        elif name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
            ignored.add(name)
    return ignored


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def install_skill(
    skill_root: Path,
    target_dirs: list[tuple[str, Path]],
    mode: str = "symlink",
    force: bool = False,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Installs or symlinks `skill_root` into every resolved agent destination safely."""
    source = skill_root.resolve()
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(f"Invalid DemoCraft root (SKILL.md missing): {source}")
    if mode not in ("symlink", "copy"):
        raise ValueError(f"Unsupported install mode '{mode}'. Choose 'symlink' or 'copy'.")

    results: list[dict[str, Any]] = []
    for agent_key, dest in target_dirs:
        entry: dict[str, Any] = {
            "agent": agent_key,
            "destination": str(dest),
            "mode": mode,
        }
        # Already installed at the exact target path (either same directory or symlink pointing here)
        if dest.exists() or dest.is_symlink():
            if dest.is_symlink() and dest.resolve() == source:
                entry["status"] = "already_linked"
                results.append(entry)
                continue
            if not dest.is_symlink() and dest.resolve() == source:
                entry["status"] = "already_in_place"
                results.append(entry)
                continue
            if not force:
                entry["status"] = "skipped_exists"
                results.append(entry)
                continue

        if dry_run:
            entry["status"] = "planned"
            results.append(entry)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            _remove_path(dest)

        if mode == "symlink":
            dest.symlink_to(source, target_is_directory=True)
        else:
            shutil.copytree(source, dest, ignore=_copy_ignore)

        entry["status"] = "installed"
        results.append(entry)

    return results


def uninstall_skill(
    target_dirs: list[tuple[str, Path]],
    skill_root: Path | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Safely unregisters DemoCraft without ever deleting the source repository."""
    source = skill_root.resolve() if skill_root is not None else None
    results: list[dict[str, Any]] = []
    for agent_key, dest in target_dirs:
        entry: dict[str, Any] = {"agent": agent_key, "destination": str(dest)}
        if not dest.exists() and not dest.is_symlink():
            entry["status"] = "not_found"
            results.append(entry)
            continue
        if source is not None and not dest.is_symlink() and dest.resolve() == source:
            entry["status"] = "skipped_source_repo"
            results.append(entry)
            continue
        if dry_run:
            entry["status"] = "planned_remove"
            results.append(entry)
            continue
        _remove_path(dest)
        entry["status"] = "removed"
        results.append(entry)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register DemoCraft in AI coding agents (Antigravity, Claude Code, Codex, Cursor/OpenCode)."
    )
    parser.add_argument(
        "--agent",
        action="append",
        default=None,
        help="Target agent(s): auto (default), all, antigravity, claude, codex, cursor.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Also register project-locally inside <dir>/.agents/skills/democraft.",
    )
    parser.add_argument(
        "--mode",
        choices=("symlink", "copy"),
        default="symlink",
        help="Install via symlink (default, tracks git pull) or clean copy.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing target path.")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without modifying disk.")
    parser.add_argument("--uninstall", action="store_true", help="Unregister DemoCraft from target agents.")
    parser.add_argument("--skip-probe", action="store_true", help="Skip environment capability probe.")
    parser.add_argument("--env-file", type=Path, default=None, help="Optional .env file for probe check.")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    agent_args = args.agent if args.agent is not None else ([] if args.project else ["auto"])
    targets = resolve_target_dirs(agent_args, project_dir=args.project)

    if args.uninstall:
        actions = uninstall_skill(targets, skill_root=skill_root, dry_run=args.dry_run)
        probe_report = None
    else:
        actions = install_skill(
            skill_root=skill_root,
            target_dirs=targets,
            mode=args.mode,
            force=args.force,
            dry_run=args.dry_run,
        )
        probe_report = None if (args.skip_probe or args.dry_run) else probe_environment(env_file=args.env_file)

    output = {
        "skill_root": str(skill_root),
        "action": "uninstall" if args.uninstall else "install",
        "dry_run": args.dry_run,
        "results": actions,
        "probe": probe_report,
    }
    if args.json:
        print(json.dumps(output, indent=2))
        return

    print(f"DemoCraft {'Uninstaller' if args.uninstall else 'Installer'} ({'DRY RUN' if args.dry_run else 'LIVE'}):")
    for item in actions:
        print(f"  - [{item['status']}] {item['agent']} -> {item['destination']}")
    if probe_report is not None:
        status = "READY" if probe_report["core_ready"] else "MISSING REQUIREMENTS"
        opt = probe_report["optional"]
        print(f"\nEnvironment Probe: {status}")
        print(f"  Browser (CDP)   : {probe_report['browser_path'] or 'NOT FOUND'}")
        print(f"  FFmpeg runner   : {probe_report['ffmpeg_strategy']}")
        print(f"  Voice providers : {', '.join(opt['available_voice_providers']) or 'captions-only / BYO'}")
        if probe_report["missing_requirements"]:
            print("  Missing         : " + ", ".join(probe_report["missing_requirements"]))


if __name__ == "__main__":
    main()
