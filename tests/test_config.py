from pathlib import Path

from codex_auto_router.config import load_config, write_default_config


def test_default_config_can_be_written_and_loaded(tmp_path: Path):
    path = tmp_path / "config.toml"
    write_default_config(path)
    config = load_config(path)
    assert config.routes["luna_low"].model == "gpt-5.6-luna"
    assert config.routing.max_auto_tier == "sol_medium"
    assert config.classifier.mode == "local"
    assert config.classifier.tier == "luna_low"
    assert config.classifier.repo_map_enabled is True
    assert config.classifier.repo_map_budget == 2500
    assert config.bridge.max_remote_tier == "terra_medium"
    assert config.bridge.sandbox == "workspace-write"
