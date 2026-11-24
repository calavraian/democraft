"""Unit tests for DemoCraft declarative web navigation & hybrid capture (`capture_flow.py`)."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capture_flow


def test_resolve_viewport_presets() -> None:
    assert capture_flow.resolve_viewport("desktop") == (1440, 900)
    assert capture_flow.resolve_viewport("hd") == (1280, 720)
    assert capture_flow.resolve_viewport("mobile") == (390, 844)
    assert capture_flow.resolve_viewport("vertical") == (1080, 1920)
    assert capture_flow.resolve_viewport("landscape") == (1920, 1080)
    assert capture_flow.resolve_viewport("square") == (1080, 1080)
    assert capture_flow.resolve_viewport([1366, 768]) == (1366, 768)

    with pytest.raises(ValueError, match="Unsupported viewport"):
        capture_flow.resolve_viewport("4k-cinema")


def test_validate_flow_rejects_remote_url_without_flag() -> None:
    flow = {
        "base_url": "https://production-app.example.com",
        "steps": [{"action": "goto", "path": "/"}],
    }
    with pytest.raises(PermissionError, match="allow-remote"):
        capture_flow.validate_flow(flow, allow_remote=False)

    # Allowed when explicitly opted in
    capture_flow.validate_flow(flow, allow_remote=True)


def test_validate_flow_rejects_unknown_action_and_empty_steps() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        capture_flow.validate_flow({"base_url": "http://127.0.0.1:3000", "steps": []})

    with pytest.raises(ValueError, match="Unsupported action"):
        capture_flow.validate_flow(
            {
                "base_url": "http://127.0.0.1:3000",
                "steps": [{"action": "exec_shell", "cmd": "rm -rf /"}],
            }
        )


def test_normalize_rect_clamps_to_unit_bounds() -> None:
    rect = {"x": 360.0, "y": 450.0, "width": 180.0, "height": 90.0}
    norm = capture_flow.normalize_rect(rect, viewport_w=1440, viewport_h=900)

    assert norm["bounds_norm"] == [0.25, 0.5, 0.125, 0.1]
    assert norm["center_norm"] == [0.3125, 0.55]


def test_compute_scroll_positions_uses_smooth_ease_curve() -> None:
    positions = capture_flow.compute_scroll_positions(from_y=0.0, to_y=600.0, frame_count=5)
    assert len(positions) == 5
    assert positions[0] == 0.0
    assert positions[-1] == 600.0
    assert positions[2] == pytest.approx(300.0, abs=0.1)
    # Easing should start slower than linear (linear at idx 1 would be 150)
    assert positions[1] < 150.0
    assert positions[3] > 450.0


def test_sanitize_capture_name_prevents_path_traversal() -> None:
    assert capture_flow.sanitize_name("../secrets/01_login") == "secrets_01_login"
    with pytest.raises(ValueError, match="cannot be empty"):
        capture_flow.sanitize_name("///...")


def test_resolve_type_value_prefers_env_without_exposing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_TEST_PASS", "my-temp-secret")
    val = capture_flow.resolve_type_value({"action": "type", "selector": "#pw", "value_env": "DEMO_TEST_PASS"})
    assert val == "my-temp-secret"

    monkeypatch.delenv("MISSING_ENV_VAR", raising=False)
    with pytest.raises(ValueError, match="MISSING_ENV_VAR"):
        capture_flow.resolve_type_value({"action": "type", "selector": "#pw", "value_env": "MISSING_ENV_VAR"})


def test_execute_flow_with_mock_cdp_captures_stills_cues_and_scroll(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    fake_png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nFAKE").decode("ascii")
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeCDP:
        def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            p = params or {}
            calls.append((method, p))
            if method == "Page.captureScreenshot":
                return {"data": fake_png_b64}
            if method == "Runtime.evaluate":
                expr = p.get("expression", "")
                if "getBoundingClientRect" in expr:
                    return {"result": {"value": {"x": 144, "y": 90, "width": 288, "height": 45}}}
                if "scrollHeight" in expr:
                    return {"result": {"value": {"maxY": 800, "currentY": 0}}}
                return {"result": {"value": True}}
            return {}

    monkeypatch.setenv("DEMO_EMAIL", "coach@demo.local")
    flow = {
        "base_url": "http://127.0.0.1:3000",
        "viewport": "desktop",
        "device_scale": 1,
        "steps": [
            {"action": "goto", "path": "/login"},
            {"action": "wait_for", "selector": "#email", "timeout_s": 2},
            {"action": "type", "selector": "#email", "value_env": "DEMO_EMAIL"},
            {"action": "capture", "name": "01_dashboard", "highlight_selector": "#btn-start"},
            {"action": "click", "selector": "#btn-start", "record_cue": True},
            {"action": "record_scroll", "name": "02_scroll_feed", "from_y": 0, "to_y": 400, "duration_s": 0.4, "fps": 10},
        ],
    }

    # Act
    manifest = capture_flow.execute_flow_on_cdp(
        cdp=FakeCDP(),
        flow=flow,
        out_dir=tmp_path,
        allow_remote=False,
    )

    # Assert
    assert (tmp_path / "01_dashboard.png").exists()
    scroll_frames = sorted((tmp_path / "02_scroll_feed").glob("frame_*.png"))
    assert len(scroll_frames) == 4
    assert len(manifest["captures"]) == 1
    assert manifest["captures"][0]["highlight"]["bounds_norm"] == [0.1, 0.1, 0.2, 0.05]
    assert len(manifest["cues"]) == 1
    assert manifest["cues"][0]["kind"] == "click"
    assert len(manifest["recordings"]) == 1
    assert manifest["recordings"][0]["frames"] == 4
    # Secret must never leak into manifest
    assert "coach@demo.local" not in json.dumps(manifest)
    assert "highlight_theme" in manifest


def test_parse_css_rgb_and_hex_conversion() -> None:
    assert capture_flow.parse_css_rgb("rgb(5, 150, 105)") == (5, 150, 105)
    assert capture_flow.parse_css_rgb("rgba(2, 132, 199, 0.9)") == (2, 132, 199)
    assert capture_flow.parse_css_rgb("rgba(0, 0, 0, 0)") is None
    assert capture_flow.rgb_to_hex((5, 150, 105)) == "#059669"


def test_recommend_highlight_recycles_scene_palette_and_avoids_button_clash() -> None:
    # Arrange: GoalPad's own harvested colors; targets are cream sidebar + emerald CTA button
    scene_palette = ["#059669", "#0284C7", "#D97706", "#18181B"]
    target_backgrounds = ["#F5F3EC", "#059669"]

    # Act
    theme = capture_flow.recommend_highlight_color(scene_palette, target_backgrounds)

    # Assert: picks a color from the scene's own palette, NEVER clashing with #059669
    assert theme["source"] == "scene_palette"
    assert theme["recommended_hex"] in scene_palette
    assert theme["recommended_hex"] != "#059669"
    assert theme["ring_style"] == "dual-ring-spotlight"


def test_recommend_highlight_falls_back_cleanly_on_empty_palette() -> None:
    theme = capture_flow.recommend_highlight_color([], ["#FFFFFF"])
    assert theme["source"] == "fallback"
    assert theme["recommended_hex"].startswith("#")


def test_compute_drag_path_uses_curved_bezier_with_smooth_easing() -> None:
    pts = capture_flow.compute_drag_path((100.0, 200.0), (500.0, 200.0), frame_count=5, arc_dy=-60.0)
    assert len(pts) == 5
    assert pts[0] == (100.0, 200.0)
    assert pts[-1] == (500.0, 200.0)
    # Midpoint lifts upward due to negative arc_dy
    assert pts[2][0] == pytest.approx(300.0, abs=0.5)
    assert pts[2][1] < 200.0


def test_execute_flow_record_drag_dispatches_pointer_events_and_records_trajectory(
    tmp_path: Path,
) -> None:
    fake_png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nFAKE").decode("ascii")
    mouse_events: list[dict[str, Any]] = []

    class FakeCDP:
        def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            p = params or {}
            if method == "Input.dispatchMouseEvent":
                mouse_events.append(p)
                return {}
            if method == "Page.captureScreenshot":
                return {"data": fake_png_b64}
            if method == "Runtime.evaluate":
                expr = p.get("expression", "")
                if "getBoundingClientRect" in expr:
                    return {"result": {"value": {"x": 200, "y": 300, "width": 80, "height": 80}}}
                return {"result": {"value": True}}
            return {}

    flow = {
        "base_url": "http://127.0.0.1:3000",
        "viewport": [1440, 900],
        "device_scale": 1,
        "steps": [
            {"action": "goto", "path": "/board"},
            {
                "action": "record_drag",
                "name": "drag_player",
                "selector": "#player-9",
                "to_norm": [0.75, 0.40],
                "arc_dy": -40,
                "duration_s": 0.4,
                "fps": 10,
            },
        ],
    }

    manifest = capture_flow.execute_flow_on_cdp(
        cdp=FakeCDP(), flow=flow, out_dir=tmp_path, allow_remote=False
    )

    drag_frames = sorted((tmp_path / "drag_player").glob("frame_*.png"))
    assert len(drag_frames) == 4
    kinds = [ev["type"] for ev in mouse_events]
    assert "mousePressed" in kinds
    assert "mouseMoved" in kinds
    assert "mouseReleased" in kinds
    assert len(manifest["recordings"]) == 1
    rec = manifest["recordings"][0]
    assert rec["kind"] == "drag"
    assert rec["frames"] == 4
    assert len(rec["pointer_frames"]) == 4
    assert rec["from_norm"] == [round(240 / 1440, 4), round(340 / 900, 4)]
    assert rec["to_norm"] == [0.75, 0.4]
