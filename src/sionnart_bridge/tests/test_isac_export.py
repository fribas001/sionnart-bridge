import unittest,tempfile,sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from isac_export import link_statistics,cfr_from_cir,export_frame,finalize
class ISACExportTests(unittest.TestCase):
 def test_coherent_cancellation(self):
  s=link_statistics(np.array([1+0j,-1+0j]),np.array([1e-9,3e-9]))
  self.assertEqual(s['coherent_gain_linear'],0);self.assertIsNone(s['coherent_gain_db'])
  self.assertEqual(s['incoherent_gain_linear'],2);self.assertAlmostEqual(s['rms_delay_spread_s'],1e-9)
 def test_invalid_and_empty(self):
  s=link_statistics(np.array([1+0j]),np.array([-1.]))
  self.assertEqual(s['valid_paths'],0);self.assertIsNone(s['mean_delay_s'])
  self.assertEqual(cfr_from_cir(np.array([1+0j]),np.array([-1.]),[0])[0],0)
 def test_baseband_phase_not_repeated(self):
  h=cfr_from_cir(np.array([1j]),np.array([.25]),np.array([0,1]))
  np.testing.assert_allclose(h,[1j,1],atol=1e-14)
 def test_full_ports_and_absolute_delays(self):
  class Paths:
   def cir(self,**kw):
    assert kw==dict(normalize_delays=False,num_time_steps=1,out_type='numpy')
    a=np.ones((2,2,1,2,3,1),complex)*1j;t=np.ones(a.shape[:-1])*2e-8
    t[...,2]=-1
    return a,t
  with tempfile.TemporaryDirectory() as d:
   cfg={'bridge_version':'1.21.0','isac':{'enabled':True,'csi':True,'csv':True,'plots':False},'output':{'status_json':str(Path(d)/'status.json')},'simulation':{'bandwidth_hz':20e6},'frames':[1,2]}
   f={'frame':1,'time_seconds':0,'transmitters':[{'name':'tx'}],'receivers':[{'name':'rx0'},{'name':'rx1'}]}
   r=export_frame(Paths(),cfg,f);finalize(cfg,[r])
   root=Path(d)/'isac';a=np.load(root/'F000001/channels.npz')
   self.assertEqual(a['cir'].shape,(2,2,1,2,3,1));self.assertEqual(a['valid'].sum(),16)
   np.testing.assert_allclose(a['csi'][...,32],2j)
   self.assertEqual(len((root/'F000001/cir_components.csv').read_text().splitlines()),17)
   self.assertEqual(json.loads((root/'dataset_manifest.json').read_text())['status'],'partial')
   a.close()
 def test_disabled(self):
  self.assertIsNone(export_frame(None,{},{}))
if __name__=='__main__':unittest.main()
