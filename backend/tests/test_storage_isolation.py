"""Guards for tests/conftest.py: tests must never write into real backend storage."""
import config
import main
import utils
from services import clip_generation


def test_every_directory_alias_points_at_isolated_storage():
    real_backend = config.BASE_DIR
    for value in (config.TEMP_DIR, utils.TEMP_DIR):
        assert real_backend not in value.parents, value
    for value in (config.OUTPUTS_DIR, main.OUTPUTS_DIR, clip_generation.OUTPUTS_DIR):
        assert real_backend not in value.parents, value


def test_get_temp_path_uses_isolated_temp_dir():
    assert utils.get_temp_path(".wav").parent == config.TEMP_DIR
