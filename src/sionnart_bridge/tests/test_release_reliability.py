"""Focused reliability contracts that must hold outside Blender."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import path_safety as paths
import worker_runtime
class ReleaseTests(unittest.TestCase):
 def test_worker_exit_preserves_status_and_flushes(self):
  for code in (0,7):
   script='import sys;sys.path.insert(0,'+repr(str(ROOT))+');from worker_runtime import exit_worker;print("receipt",end="");exit_worker('+str(code)+')'
   result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=20)
   self.assertEqual(result.returncode,code);self.assertEqual(result.stdout,'receipt')
 def test_mesh_paths_bounded_and_collision_resistant(self):
  directory='C:\\results\\meshes'
  names=[paths.mesh_asset_filename(directory,'植樹'*100,n,windows=True) for n in [0,1]]
  self.assertNotEqual(*names)
  self.assertTrue(all(len(n)<70 for n in names))
  with self.assertRaises(paths.PathLengthError):paths.validate_path_budget('C:\\'+'x'*245,windows=True)
 def test_empty_channel_has_no_invented_gain(self):
  from sionna_worker import _channel_link_analytics
  result=_channel_link_analytics(1,0,{'name':'TX'},{'name':'RX'},[],{})
  self.assertEqual(result['path_count'],0)
  self.assertIsNone(result['total_power_db']);self.assertIsNone(result['strongest_path_gain_db'])
 def test_partial_receipts_are_atomic(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'status.json';worker_runtime.write_json(p,{'state':'starting'})
   worker_runtime.write_json(p,{'state':'cancelled','reason':'operator'})
   self.assertEqual(json.loads(p.read_text())['state'],'cancelled')
   self.assertEqual(list(Path(td).glob('*.tmp')),[])
if __name__=='__main__':unittest.main()
