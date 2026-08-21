"""Persistent, non-sensitive WebUI generation presets."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from loguru import logger

from app.models.schema import VideoParams
from app.utils.utils import storage_dir

PRESETS_VERSION = 1
PRESETS_FILE = Path(storage_dir("presets.json"))
_PRESETS_LOCK = RLock()
_SETTINGS_FIELDS = set(VideoParams.model_fields)
_SECRET_FIELD_NAMES = {
    "api_key",
    "api_keys",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "credentials",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_secret_field(name: str) -> bool:
    normalized = name.lower()
    return any(secret in normalized for secret in _SECRET_FIELD_NAMES)


def _settings_from_params(params: VideoParams | dict) -> dict:
    webui_state = {}
    if isinstance(params, dict) and "params" in params:
        webui_state = params.get("webui", {})
        params = params["params"]
    if isinstance(params, VideoParams):
        values = params.model_dump(mode="json")
    else:
        values = VideoParams.model_validate(params).model_dump(mode="json")

    values = {
        key: value
        for key, value in values.items()
        if key in _SETTINGS_FIELDS and not _is_secret_field(key)
    }
    return {
        "script": {
            key: values[key]
            for key in (
                "video_subject",
                "video_script",
                "video_terms",
                "video_language",
                "paragraph_number",
                "video_script_prompt",
                "custom_system_prompt",
            )
            if key in values
        },
        "video": {
            key: values[key]
            for key in (
                "video_sources",
                "video_aspect",
                "video_concat_mode",
                "video_transition_mode",
                "video_clip_duration",
                "video_clip_speed",
                "video_count",
                "match_materials_to_script",
                "video_materials",
            )
            if key in values
        },
        "audio": {
            key: webui_state[key]
            for key in ("tts_server", "voice_mode")
            if key in webui_state and not _is_secret_field(key)
        } | {
            key: values[key]
            for key in (
                "custom_audio_file",
                "voice_name",
                "voice_volume",
                "voice_rate",
                "bgm_type",
                "bgm_file",
                "bgm_volume",
                "video_music_prompt",
                "sonilo_bgm_prompt",
            )
            if key in values
        },
        "subtitles": {
            key: values[key]
            for key in (
                "subtitle_enabled",
                "subtitle_position",
                "custom_position",
                "font_name",
                "text_fore_color",
                "text_background_color",
                "rounded_subtitle_background",
                "font_size",
                "stroke_color",
                "stroke_width",
            )
            if key in values
        },
    }


def settings_from_params(params: VideoParams | dict) -> dict:
    """Return a JSON-compatible snapshot of generation preferences only."""
    return _settings_from_params(params)


def settings_to_params(settings: dict, current: VideoParams | dict) -> VideoParams:
    """Merge a preset with current/default values and validate unknown old fields away."""
    if not isinstance(settings, dict):
        settings = {}
    merged = {}
    if isinstance(current, VideoParams):
        merged.update(current.model_dump(mode="python"))
    else:
        merged.update(VideoParams.model_validate(current).model_dump(mode="python"))
    for category in ("script", "video", "audio", "subtitles"):
        values = settings.get(category, {})
        if isinstance(values, dict):
            merged.update(
                {
                    key: value
                    for key, value in values.items()
                    if key in _SETTINGS_FIELDS and not _is_secret_field(key)
                }
            )
    return VideoParams.model_validate(merged)


def _read_unlocked(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_presets = data.get("presets", data) if isinstance(data, dict) else data
        if not isinstance(raw_presets, list):
            return []
        return [preset for preset in raw_presets if isinstance(preset, dict)]
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning(f"failed to read WebUI presets: {path}: {exc}")
        return []


def _write_unlocked(path: Path, presets: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": PRESETS_VERSION, "presets": presets}
    fd, temporary_path = tempfile.mkstemp(prefix="presets-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def load_presets(path: Path | str = PRESETS_FILE) -> list[dict]:
    with _PRESETS_LOCK:
        return copy.deepcopy(_read_unlocked(Path(path)))


def save_preset(title: str, description: str, params: VideoParams | dict, *, path=PRESETS_FILE) -> dict:
    title = str(title or "").strip()
    if not title:
        raise ValueError("preset title is required")
    settings = settings_from_params(params)
    now = _now()
    preset = {
        "version": PRESETS_VERSION,
        "id": str(uuid4()),
        "title": title,
        "description": str(description or "").strip(),
        "is_default": False,
        "created_at": now,
        "updated_at": now,
        "settings": settings,
    }
    with _PRESETS_LOCK:
        presets = _read_unlocked(Path(path))
        presets.append(preset)
        _write_unlocked(Path(path), presets)
    return copy.deepcopy(preset)


def update_preset(preset_id: str, params: VideoParams | dict, *, path=PRESETS_FILE) -> dict:
    settings = settings_from_params(params)
    with _PRESETS_LOCK:
        presets = _read_unlocked(Path(path))
        for preset in presets:
            if preset.get("id") == preset_id:
                preset["settings"] = settings
                preset["updated_at"] = _now()
                _write_unlocked(Path(path), presets)
                return copy.deepcopy(preset)
    raise KeyError(preset_id)


def update_preset_metadata(
    preset_id: str, title: str, description: str, *, path=PRESETS_FILE
) -> dict:
    """Update editable preset metadata without changing its generation settings."""
    title = str(title or "").strip()
    if not title:
        raise ValueError("preset title is required")
    with _PRESETS_LOCK:
        presets = _read_unlocked(Path(path))
        for preset in presets:
            if preset.get("id") == preset_id:
                preset["title"] = title
                preset["description"] = str(description or "").strip()
                preset["updated_at"] = _now()
                _write_unlocked(Path(path), presets)
                return copy.deepcopy(preset)
    raise KeyError(preset_id)


def duplicate_preset(preset_id: str, *, path=PRESETS_FILE) -> dict:
    with _PRESETS_LOCK:
        presets = _read_unlocked(Path(path))
        for preset in presets:
            if preset.get("id") == preset_id:
                now = _now()
                duplicate = copy.deepcopy(preset)
                duplicate.update(
                    id=str(uuid4()),
                    title=f"{preset.get('title', 'Preset')} (Copy)",
                    is_default=False,
                    created_at=now,
                    updated_at=now,
                )
                presets.append(duplicate)
                _write_unlocked(Path(path), presets)
                return copy.deepcopy(duplicate)
    raise KeyError(preset_id)


def delete_preset(preset_id: str, *, path=PRESETS_FILE) -> None:
    with _PRESETS_LOCK:
        presets = _read_unlocked(Path(path))
        remaining = [preset for preset in presets if preset.get("id") != preset_id]
        if len(remaining) == len(presets):
            raise KeyError(preset_id)
        _write_unlocked(Path(path), remaining)


def set_default_preset(preset_id: str | None, *, path=PRESETS_FILE) -> None:
    with _PRESETS_LOCK:
        presets = _read_unlocked(Path(path))
        if preset_id is not None and not any(p.get("id") == preset_id for p in presets):
            raise KeyError(preset_id)
        for preset in presets:
            preset["is_default"] = preset.get("id") == preset_id if preset_id else False
        _write_unlocked(Path(path), presets)


def get_default_preset(*, path=PRESETS_FILE) -> dict | None:
    presets = load_presets(path)
    return next((preset for preset in presets if preset.get("is_default") is True), None)
