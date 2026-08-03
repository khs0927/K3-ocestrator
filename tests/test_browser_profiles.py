from pathlib import Path

from browser_bridge.profiles import load_profiles


def test_default_browser_profiles_load_without_file(tmp_path: Path):
    profiles = load_profiles(tmp_path / "missing.json")
    assert profiles["deepseek"].model == "deepseek-web"
    assert profiles["glm"].model == "glm-web"
    assert profiles["deepseek"].input_selectors
