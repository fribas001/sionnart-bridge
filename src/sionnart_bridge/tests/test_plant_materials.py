import math,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import plant_materials as p
import worker_runtime as w


class PlantMaterialsTests(unittest.TestCase):
    def test_leaf_reference_and_passive_sign(self):
        er,sigma=p.dielectric('LEAF_P833',26e9)
        self.assertAlmostEqual(er,12.544512,places=8)
        self.assertAlmostEqual(sigma,19.620737223661,places=10)
        self.assertAlmostEqual(p.dielectric('LEAF_P833',18e9)[0],17.6376)
        for f in [1e9,2.4e9,5.8e9,18e9,26e9,30e9]:
            e,s=p.dielectric('LEAF_P833',f)
            self.assertGreater(e,1);self.assertGreater(s,0)

    def test_wood_table_and_interpolation(self):
        for ghz,er,tangent in [(1,7.2,.29),(2.4,6.2,.30),(5.8,6,.37),(30,5.3,.43)]:
            e,s=p.dielectric('WOOD40_P833',ghz*1e9)
            self.assertAlmostEqual(e,er)
            self.assertAlmostEqual(s/(2*math.pi*ghz*1e9*p.EPSILON_0),er*tangent)
        self.assertAlmostEqual(p.dielectric('WOOD40_P833',17.9e9)[0],5.65)
        self.assertAlmostEqual(p.dielectric('WOOD40_P833',26e9)[1],3.29072418653335)

    def test_no_extrapolation_or_unknown_model(self):
        for f in [0,-1,999e6,30.001e9,float('nan'),float('inf')]:
            with self.assertRaisesRegex(ValueError,'1–30 GHz'):p.dielectric('LEAF_P833',f)
        with self.assertRaisesRegex(ValueError,'Unknown'):p.dielectric('BARK',26e9)

    def test_float32_frequency_endpoint(self):
        import struct
        f=struct.unpack('f',struct.pack('f',30e9))[0]
        self.assertEqual(p.dielectric('WOOD40_P833',f),p.dielectric('WOOD40_P833',30e9))
        ref=p.reference('WOOD40_P833',f)
        self.assertEqual(ref['frequency_hz'],f)
        self.assertEqual(ref['evaluation_frequency_hz'],30e9)

    def test_units_and_provenance_overrides(self):
        self.assertEqual(p.PRESETS['LEAF']['thickness'],.0002)
        self.assertEqual(p.PRESETS['BRANCH']['thickness'],.056)
        spec={'plant_library_preset':'LEAF','thickness':.0002,'scattering_coefficient':0,'xpd_coefficient':0}
        ref=p.reference('LEAF_P833',26e9,spec)
        self.assertFalse(ref['thickness_overridden'])
        self.assertIn('not a measured',ref['surface_scattering_basis'])
        spec.update(thickness=.0003,scattering_coefficient=.3)
        ref=p.reference('LEAF_P833',26e9,spec)
        self.assertTrue(ref['thickness_overridden']);self.assertIn('User-selected',ref['surface_scattering_basis'])
        self.assertIsNone(p.reference('WOOD40_P833',26e9,spec)['library_preset'])

    def test_worker_recomputes_at_actual_frequency(self):
        mat=SimpleNamespace(name='leaf',id=lambda:'leaf')
        scene=SimpleNamespace(frequency=26e9,radio_materials={'leaf':mat},objects={'leaf_mesh':SimpleNamespace(radio_material=mat)})
        runtime={'LambertianPattern':lambda:'lambertian'}
        spec={'source_name':'leaf','model':'VEGETATION','plant_model':'LEAF_P833','plant_library_preset':'LEAF',
              'relative_permittivity':999,'conductivity':999,'thickness':.0002}
        result=w.apply_radio_materials(scene,{'materials':[spec]},runtime)
        self.assertAlmostEqual(mat.relative_permittivity,12.544512)
        self.assertAlmostEqual(mat.conductivity,19.620737223661)
        self.assertEqual(mat.thickness,.0002);self.assertEqual(result[0]['object_count'],1)
        self.assertEqual(result[0]['plant_reference']['frequency_hz'],26e9)
        scene.frequency=5.8e9
        result=w.apply_radio_materials(scene,{'materials':[spec]},runtime)
        self.assertEqual((mat.relative_permittivity,mat.conductivity),p.dielectric('LEAF_P833',5.8e9))
        self.assertEqual(result[0]['plant_reference']['frequency_hz'],5.8e9)
        scene.frequency=60e9
        with self.assertRaisesRegex(ValueError,'1–30 GHz'):w.apply_radio_materials(scene,{'materials':[spec]},runtime)


if __name__=='__main__':unittest.main()
