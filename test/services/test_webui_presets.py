import json
import tempfile
import unittest
from pathlib import Path

from app.models.schema import VideoParams
from app.services import webui_presets


class TestWebuiPresets(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "presets.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_round_trip_and_sensitive_fields_are_excluded(self):
        params = VideoParams(video_subject="Tema", video_language="es", voice_name="voice")
        preset = webui_presets.save_preset(
            "Español",
            "Vertical",
            {
                "params": params.model_dump(mode="json"),
                "webui": {"tts_server": "edge-tts", "voice_mode": "tts"},
            },
            path=self.path,
        )
        loaded = webui_presets.load_presets(self.path)

        self.assertEqual(loaded[0], preset)
        self.assertEqual(preset["settings"]["script"]["video_subject"], "Tema")
        self.assertEqual(preset["settings"]["audio"]["tts_server"], "edge-tts")
        self.assertNotIn("api_key", json.dumps(preset))
        self.assertEqual(
            webui_presets.settings_to_params(preset["settings"], VideoParams(video_subject=""))
            .video_language,
            "es",
        )

    def test_only_one_default_and_default_can_be_removed(self):
        first = webui_presets.save_preset("First", "", VideoParams(video_subject="1"), path=self.path)
        second = webui_presets.save_preset("Second", "", VideoParams(video_subject="2"), path=self.path)

        webui_presets.set_default_preset(first["id"], path=self.path)
        webui_presets.set_default_preset(second["id"], path=self.path)
        loaded = webui_presets.load_presets(self.path)
        self.assertEqual([p["id"] for p in loaded if p["is_default"]], [second["id"]])

        webui_presets.set_default_preset(None, path=self.path)
        self.assertIsNone(webui_presets.get_default_preset(path=self.path))

    def test_duplicate_update_and_delete(self):
        original = webui_presets.save_preset("Original", "Description", VideoParams(video_subject="old"), path=self.path)
        duplicate = webui_presets.duplicate_preset(original["id"], path=self.path)

        self.assertNotEqual(original["id"], duplicate["id"])
        self.assertEqual(original["settings"], duplicate["settings"])
        self.assertFalse(duplicate["is_default"])
        self.assertNotEqual(original["title"], duplicate["title"])

        updated = webui_presets.update_preset(
            original["id"], VideoParams(video_subject="new"), path=self.path
        )
        self.assertEqual(updated["settings"]["script"]["video_subject"], "new")
        webui_presets.delete_preset(duplicate["id"], path=self.path)
        self.assertEqual(len(webui_presets.load_presets(self.path)), 1)

    def test_update_metadata_preserves_generation_settings(self):
        original = webui_presets.save_preset(
            "Original",
            "Old description",
            VideoParams(video_subject="unchanged"),
            path=self.path,
        )

        updated = webui_presets.update_preset_metadata(
            original["id"], "Renamed", "New description", path=self.path
        )

        self.assertEqual(updated["title"], "Renamed")
        self.assertEqual(updated["description"], "New description")
        self.assertEqual(
            updated["settings"], original["settings"]
        )
        with self.assertRaises(ValueError):
            webui_presets.update_preset_metadata(
                original["id"], "", "", path=self.path
            )

    def test_missing_unknown_and_corrupt_files_are_safe(self):
        self.assertEqual(webui_presets.load_presets(self.path), [])
        self.path.write_text("{broken", encoding="utf-8")
        self.assertEqual(webui_presets.load_presets(self.path), [])

        self.path.write_text(
            json.dumps(
                [{
                    "id": "old",
                    "title": "Old",
                    "is_default": True,
                    "settings": {
                        "script": {"video_subject": "legacy", "future_field": "ignored"},
                        "unknown": {"value": "ignored"},
                    },
                }]
            ),
            encoding="utf-8",
        )
        preset = webui_presets.get_default_preset(path=self.path)
        restored = webui_presets.settings_to_params(
            preset["settings"], VideoParams(video_subject="current")
        )
        self.assertEqual(restored.video_subject, "legacy")
        self.assertEqual(restored.video_language, "")


if __name__ == "__main__":
    unittest.main()
