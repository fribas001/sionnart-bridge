"""Pure-Python regression tests for shared services and tensor edge cases."""
import copy,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import worker_runtime as runtime
import radio_map_worker as maps
class RuntimeTests(unittest.TestCase):
 def test_singleton_planar_dimensions(self):
  for shape in [(1,1,3),(1,4,3),(4,1,3),(3,3,3)]:
   x=np.arange(np.prod(shape)).reshape(shape);np.testing.assert_array_equal(maps.normalize_cell_centers(x),x)
 def test_mesh_vector_three_cells_and_one_cell(self):
  for n in [1,3,5]:
   v=SimpleNamespace(x=np.arange(n),y=np.arange(n)+10,z=np.arange(n)+20)
   np.testing.assert_array_equal(maps.normalize_cell_centers(v),np.column_stack([v.x,v.y,v.z]))
 def test_capability_detection_does_not_swallow_errors(self):
  class Modern:
   def __init__(self,deterministic=False):self.deterministic=deterministic
  self.assertTrue(runtime.make_path_solver(Modern).deterministic)
  self.assertFalse(runtime.make_path_solver(Modern,False).deterministic)
  class Old:pass
  self.assertIsInstance(runtime.make_path_solver(Old,False),Old)
  class Broken:
   def __init__(self,deterministic=False):raise RuntimeError('real failure')
  with self.assertRaisesRegex(RuntimeError,'real failure'):runtime.make_path_solver(Broken)
 def test_material_cache_invalidation_and_summary_ownership(self):
  mat=object();scene=SimpleNamespace(frequency=24e9,radio_materials={'m':mat},objects={})
  cfg={};frame={'materials':[{'model':'ITU'}]}
  with patch.object(runtime,'_apply_radio_materials_uncached',return_value=[{'value':1}]) as apply:
   runtime.apply_radio_materials(scene,frame,cfg)[0]['value']=99
   self.assertEqual(runtime.apply_radio_materials(scene,frame,cfg),[{'value':1}]);self.assertEqual(apply.call_count,1)
   scene.frequency=25e9;runtime.apply_radio_materials(scene,frame,cfg)
   frame['materials'][0]['model']='CUSTOM';runtime.apply_radio_materials(scene,frame,cfg)
   scene.objects['mesh']=SimpleNamespace(radio_material=mat);runtime.apply_radio_materials(scene,frame,cfg)
   scene2=copy.copy(scene);runtime.apply_radio_materials(scene2,frame,cfg)
   self.assertEqual(apply.call_count,5)
 def test_array_cache_invalidates_on_profile_scene_and_replacement(self):
  scene=SimpleNamespace(tx_array=None);cfg={'PlanarArray':object};profile={'pattern':'iso'}
  factory=lambda config,cls:object()
  runtime.ensure_tx_array(scene,cfg,factory,profile);initial=scene.tx_array
  runtime.ensure_tx_array(scene,cfg,factory,profile);self.assertIs(initial,scene.tx_array)
  profile['pattern']='dipole';runtime.ensure_tx_array(scene,cfg,factory,profile);self.assertIsNot(initial,scene.tx_array)
  scene.tx_array=object();replaced=scene.tx_array;runtime.ensure_tx_array(scene,cfg,factory,profile);self.assertIsNot(replaced,scene.tx_array)
 def test_atomic_status_and_failure_propagation(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'status.json';self.assertTrue(runtime.write_json(p,{'state':'finished'}))
   with patch.object(runtime,'_atomic_replace_with_retry',side_effect=PermissionError('locked')):
    with self.assertRaises(PermissionError):runtime.write_json(p,{'state':'bad'})
    self.assertFalse(runtime.write_status_json(p,{'state':'bad'}))
   self.assertIn('finished',p.read_text())
if __name__=='__main__':unittest.main()
