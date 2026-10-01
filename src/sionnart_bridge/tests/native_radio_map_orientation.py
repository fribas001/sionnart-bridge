"""Check the CSV/HDF5 files emitted by blender_radio_map_orientation.py."""
import csv
import json
import sys
from pathlib import Path
import h5py
import numpy as np

out = Path(sys.argv[1]).resolve()
records = json.loads((out/'orientation_checks.json').read_text(encoding='utf-8'))
assert len(records) == 7
for record in records:
    path = Path(record['export'])
    assert path.is_file()
    meta = json.loads(Path(record['metadata']).read_text(encoding='utf-8'))
    assert 'orientation' in json.dumps(meta), record['label']
    if path.suffix == '.csv':
        rows = list(csv.DictReader(path.open(encoding='utf-8', newline='')))
        assert len(rows) == 6
        assert {'normal_x','tangent_x','bitangent_x','rotation_x','rotation_y','rotation_z'} <= set(rows[0])
        continue
    with h5py.File(path, 'r') as f:
        sim = f['simulations/coverage_2d']
        c = sim['coordinates']
        count = 2 if record['label'] == 'animated custom' else 1
        assert sim['data/values_db'].shape == (count,3,2)
        assert 'local plane' in sim.attrs['spatial_axes']
        assert 'z_plane' not in c
        centers = c['cell_centers'][...]
        bases = c['plane_basis'][...]
        origins = c['plane_center'][...]
        angles = c['plane_orientation'][...]
        us = c['plane_u'][...]
        vs = c['plane_v'][...]
        for i in range(count):
            center_grid = centers[i] if centers.ndim == 4 else centers
            basis = bases[i] if bases.ndim == 3 else bases
            origin = origins[i] if origins.ndim == 2 else origins
            u = us[i] if us.ndim == 2 else us
            v = vs[i] if vs.ndim == 2 else vs
            local = (center_grid - origin) @ basis.T
            np.testing.assert_allclose(local[:,:,0], np.broadcast_to(u, (3,2)), atol=2e-5)
            np.testing.assert_allclose(local[:,:,1], np.broadcast_to(v[:,None], (3,2)), atol=2e-5)
            np.testing.assert_allclose(local[:,:,2], 0, atol=2e-5)
            np.testing.assert_allclose(u, [-1,1], atol=2e-5)
            np.testing.assert_allclose(v, [-1,0,1], atol=2e-5)
        if count == 2:
            assert centers.ndim == 4 and bases.ndim == 3 and angles.shape == (2,3)
            assert not np.allclose(centers[0], centers[1])
    print('ORIENTATION_EXPORT_PASS', record['label'], flush=True)
print('ALL_ORIENTATION_EXPORTS_PASS', flush=True)
