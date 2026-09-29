import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from human_materials import dielectric
from isac_export import runtime_material_metadata
from types import SimpleNamespace as S
class HumanTests(unittest.TestCase):
 def test_six_ghz(self):
  for key,er,sigma in [('DRY_SKIN',34.945779,3.891112),('MUSCLE',48.217301,5.201957),('FAT',4.936675,.306239)]:
   a,b=dielectric(key,6e9);self.assertAlmostEqual(a,er,places=5);self.assertAlmostEqual(b,sigma,places=5)
 def test_dispersion_and_passivity(self):
  for key in ['DRY_SKIN','MUSCLE','FAT']:
   low=dielectric(key,5.9e9);high=dielectric(key,6.4e9);self.assertGreater(low[0],high[0]);self.assertGreater(high[1],low[1]);self.assertGreater(low[1],0)
 def test_range(self):
  with self.assertRaises(ValueError):dielectric('DRY_SKIN',0)
 def test_resolved_includes_fallback(self):
  m=S(name='fallback',relative_permittivity=[35.],conductivity=[3.9],thickness=[.1],scattering_coefficient=[0.],xpd_coefficient=[0.])
  r=runtime_material_metadata(S(frequency=[6e9],radio_materials={'fallback':m},objects={'body':S(radio_material=m)}))
  self.assertEqual(r['materials'][0]['conductivity_s_m'],3.9);self.assertEqual(r['scene_objects'][0]['radio_material'],'fallback')
