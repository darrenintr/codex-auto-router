from pathlib import Path

from codex_auto_router.config import load_config, write_default_config


def test_default_config_can_be_written_and_loaded(tmp_path: Path):
    path = tmp_path / "config.toml"
    write_default_config(path)
    config = load_config(path)
    assert config.routes["luna_low"].model == "gpt-5.6-luna"
    assert config.routing.max_auto_tier == "sol_medium"
