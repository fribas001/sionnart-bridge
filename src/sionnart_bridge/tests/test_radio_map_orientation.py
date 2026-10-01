"""Plane-coordinate and export regression checks; no Blender dependency."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import radio_map_orientation as orientation
from radio_map_worker import build_rows
from result_export_worker import _rectilinear_coordinates


class OrientationTests(unittest.TestCase):
    def test_legacy_defaults_and_presets(self):
        self.assertEqual(orientation.orientation_from_settings(SimpleNamespace()), [0, 0, 0])
        self.assertEqual(orientation.orientation_from_payload({}), [0, 0, 0])
        for plane, axes in [('XY', np.eye(3)), ('XZ', [[1, 0, 0], [0, 0, 1], [0, -1, 0]]),
                            ('YZ', [[0, 1, 0], [0, 0, 1], [1, 0, 0]])]:
            angles = orientation.orientation_from_settings(SimpleNamespace(radio_map_plane=plane))
            np.testing.assert_allclose(orientation.plane_basis(angles), axes, atol=1e-12)

    def test_invalid_angles_rejected(self):
        for angles in ([0, 1], [0, float('nan'), 0], [float('inf'), 0, 0]):
            with self.assertRaises(ValueError):
                orientation.orientation_from_payload({'orientation': angles})

    def test_custom_basis_and_centering(self):
        angles = [.63, -.41, .77]
        basis = np.array(orientation.plane_basis(angles))
        np.testing.assert_allclose(basis @ basis.T, np.eye(3), atol=1e-12)
        np.testing.assert_allclose(np.cross(basis[0], basis[1]), basis[2])
        center, tx = np.array([1, 2, 3]), np.array([-4, -5, 7])
        moved = orientation.center_on_plane(center, tx, angles)
        self.assertAlmostEqual(np.dot(np.array(moved) - center, basis[2]), 0)
        np.testing.assert_allclose(basis[:2] @ (np.array(moved) - tx), 0, atol=1e-12)
        self.assertEqual(orientation.center_on_plane(center, tx, [0, 0, 0]), [-4, -5, 3])

    def test_rows_keep_world_coordinates_and_full_rotation(self):
        angles = [.63, -.41, .77]
        basis = np.array(orientation.plane_basis(angles))
        centers = np.array([[[-1, -1, 0], [1, -1, 0]], [[-1, 1, 0], [1, 1, 0]]]) @ basis
        frame = {'frame': 2, 'radio_map': {'orientation': angles, 'cell_size_x': 2, 'cell_size_y': 2}}
        rows, *_ = build_rows(frame, centers, np.ones((2, 2)), np.zeros((2, 2)), 'path_gain')
        for row, p in zip(rows, centers.reshape(-1, 3)):
            np.testing.assert_allclose([row[k] for k in ('x', 'y', 'z')], p)
            np.testing.assert_allclose([row['normal_' + k] for k in 'xyz'], basis[2])
            np.testing.assert_allclose([row['rotation_' + k] for k in 'xyz'], angles[::-1])
        self.assertEqual(_rectilinear_coordinates('coverage_2d', centers), {})

    def test_vertical_plane_is_not_mislabelled_horizontal(self):
        centers = np.array([[[0, 2, 0], [1, 2, 0]], [[0, 2, 1], [1, 2, 1]]])
        self.assertEqual(_rectilinear_coordinates('coverage_2d', centers), {})
        self.assertEqual(_rectilinear_coordinates('coverage_2d', centers[:1,:1],
                                                  orientation=[0,0,math.pi/2]), {})


if __name__ == '__main__':
    unittest.main()
