"""Unit tests for DemoCraft zero-bloat stdlib installer (`install.py`)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import install


def _make_fake_skill_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text("---\nname: democraft\n---\n# DemoCraft\n", encoding="utf-8")
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts" / "probe.py").write_text("# probe\n", encoding="utf-8")
    # Files that must NEVER be copied in copy mode
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "config").write_text("secret-git\n", encoding="utf-8")
    (root / ".env.local").write_text("GEMINI_API_KEY=do-not-copy\n", encoding="utf-8")
    (root / ".DS_Store").write_text("junk", encoding="utf-8")
    return root


def test_detect_installed_agents_finds_existing_config_roots(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    (fake_home / ".gemini" / "config").mkdir(parents=True)
    (fake_home / ".claude").mkdir(parents=True)

    detected = install.detect_installed_agents(fake_home)

    assert detected == ["antigravity", "claude"]


def test_resolve_target_dirs_auto_falls_back_when_no_agent_detected(tmp_path: Path) -> None:
    fake_home = tmp_path / "empty_home"
    fake_home.mkdir()

    targets = install.resolve_target_dirs(["auto"], home=fake_home)

    assert len(targets) == 1
    assert targets[0][0] == "cursor"
    assert targets[0][1] == fake_home / ".agents" / "skills" / "democraft"


def test_install_symlink_is_idempotent_and_protects_existing_dirs(tmp_path: Path) -> None:
    skill_root = _make_fake_skill_repo(tmp_path / "repo")
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    targets = install.resolve_target_dirs(["claude"], home=fake_home)

    # First install creates symlink
    res1 = install.install_skill(skill_root, targets, mode="symlink")
    dest = fake_home / ".claude" / "skills" / "democraft"
    assert res1[0]["status"] == "installed"
    assert dest.is_symlink()
    assert dest.resolve() == skill_root.resolve()

    # Re-running is cleanly idempotent
    res2 = install.install_skill(skill_root, targets, mode="symlink")
    assert res2[0]["status"] == "already_linked"

    # Existing unrelated directory is protected unless force=True
    other_target = [("codex", fake_home / ".codex" / "skills" / "democraft")]
    other_target[0][1].mkdir(parents=True)
    res3 = install.install_skill(skill_root, other_target, mode="symlink", force=False)
    assert res3[0]["status"] == "skipped_exists"
    assert not other_target[0][1].is_symlink()

    res4 = install.install_skill(skill_root, other_target, mode="symlink", force=True)
    assert res4[0]["status"] == "installed"
    assert other_target[0][1].is_symlink()


def test_install_copy_mode_excludes_git_and_secret_env_files(tmp_path: Path) -> None:
    skill_root = _make_fake_skill_repo(tmp_path / "repo")
    project_dir = tmp_path / "my_app"
    project_dir.mkdir()
    targets = install.resolve_target_dirs([], home=tmp_path / "home", project_dir=project_dir)

    res = install.install_skill(skill_root, targets, mode="copy")

    dest = project_dir / ".agents" / "skills" / "democraft"
    assert res[0]["status"] == "installed"
    assert (dest / "SKILL.md").is_file()
    assert (dest / "scripts" / "probe.py").is_file()
    assert not (dest / ".git").exists()
    assert not (dest / ".env.local").exists()
    assert not (dest / ".DS_Store").exists()


def test_install_dry_run_makes_no_filesystem_changes(tmp_path: Path) -> None:
    skill_root = _make_fake_skill_repo(tmp_path / "repo")
    fake_home = tmp_path / "home"
    (fake_home / ".gemini" / "config").mkdir(parents=True)
    targets = install.resolve_target_dirs(["antigravity"], home=fake_home)

    res = install.install_skill(skill_root, targets, mode="symlink", dry_run=True)

    assert res[0]["status"] == "planned"
    assert not (fake_home / ".gemini" / "config" / "skills" / "democraft").exists()


def test_uninstall_removes_symlink_without_deleting_source_repo(tmp_path: Path) -> None:
    skill_root = _make_fake_skill_repo(tmp_path / "repo")
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    targets = install.resolve_target_dirs(["claude"], home=fake_home)
    install.install_skill(skill_root, targets, mode="symlink")

    res = install.uninstall_skill(targets, skill_root=skill_root)
    assert res[0]["status"] == "removed"
    assert not (fake_home / ".claude" / "skills" / "democraft").exists()
    assert (skill_root / "SKILL.md").is_file()

    # Safety: pointing uninstall directly at the source repo itself refuses deletion
    res_self = install.uninstall_skill([("self", skill_root)], skill_root=skill_root)
    assert res_self[0]["status"] == "skipped_source_repo"
    assert (skill_root / "SKILL.md").is_file()
