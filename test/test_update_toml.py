import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

import update_toml


def write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_update_file_adds_missing_values_without_overwriting_existing_values():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        example = directory / "config.example.toml"
        config = directory / "config.toml"
        write_file(
            example,
            """log_level = "DEBUG"
listen_port = 8080

[app]
existing = "example"
new_setting = true
""",
        )
        write_file(
            config,
            """log_level = "INFO" # preserve this customized value

[app]
existing = "custom"
""",
        )

        assert update_toml.update_file(example, config) == 2

        parsed = tomllib.loads(config.read_text(encoding="utf-8"))
        assert parsed["log_level"] == "INFO"
        assert parsed["listen_port"] == 8080
        assert parsed["app"] == {"existing": "custom", "new_setting": True}
        assert "preserve this customized value" in config.read_text(encoding="utf-8")


def test_update_file_keeps_root_keys_before_tables():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        example = directory / "config.example.toml"
        config = directory / "config.toml"
        write_file(example, "root_value = 42\n\n[app]\napp_value = true\n")
        write_file(config, "[app]\nexisting = true\n")

        update_toml.update_file(example, config)

        content = config.read_text(encoding="utf-8")
        assert content.index("root_value = 42") < content.index("[app]")
        assert tomllib.loads(content) == {
            "root_value": 42,
            "app": {"existing": True, "app_value": True},
        }


def test_update_file_is_idempotent_when_all_values_are_present():
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        example = directory / "config.example.toml"
        config = directory / "config.toml"
        content = "root_value = 42\n\n[app]\napp_value = true\n"
        write_file(example, content)
        write_file(config, content)

        before = config.read_text(encoding="utf-8")
        assert update_toml.update_file(example, config) == 0
        assert config.read_text(encoding="utf-8") == before


def test_main_copies_example_when_config_does_not_exist(monkeypatch):
    with TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        example = directory / "config.example.toml"
        config = directory / "config.toml"
        write_file(example, "[app]\nnew_setting = true\n")
        monkeypatch.setattr(
            "sys.argv", ["update_toml.py", str(config), str(example)]
        )

        assert update_toml.main() == 0
        assert config.read_text(encoding="utf-8") == example.read_text(encoding="utf-8")