import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "sionnart_bridge"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_path_gain_conversion():
    worker = load("sionna_worker")
    assert worker._linear_to_db(1.0) == 0.0
    assert worker._linear_to_db(0.01) == -20.0


def test_radio_map_center_normalization():
    worker = load("radio_map_worker")
    soa = np.array([[0.0, 1.0], [2.0, 3.0], [4.0, 5.0]])
    normalized = worker.normalize_cell_centers(soa)
    assert normalized.shape == (2, 3)
    np.testing.assert_allclose(normalized[0], [0.0, 2.0, 4.0])


def test_current_stacked_height_spacing_behavior_is_recorded():
    worker = load("radio_map_3d_worker")
    heights = worker.voxel_layer_heights({"size_z": 10.0, "cell_size_z": 3.0, "center_z": 0.0})
    np.testing.assert_allclose(heights, [-4.5, -1.5, 1.5, 4.5])
