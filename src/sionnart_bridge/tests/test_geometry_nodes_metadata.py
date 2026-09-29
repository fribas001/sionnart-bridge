import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import geometry_nodes_metadata as m


class MetadataTests(unittest.TestCase):
    def test_legacy_modifier_values_and_fields(self):
        socket = SimpleNamespace(identifier='Socket_7',name='Seed',socket_type='NodeSocketInt',default_value=0)
        class Modifier(dict):
            name = 'Plant'
        modifier = Modifier(Socket_7=42)
        self.assertEqual(m._input_record(modifier,socket,[])['value'],42)
        modifier['Socket_7_use_attribute'] = 1
        modifier['Socket_7_attribute_name'] = 'seed_field'
        record = m._input_record(modifier,socket,[])
        self.assertEqual(record['attribute_name'],'seed_field')
        self.assertIsNone(record['value'])

    def test_missing_value_identifies_fallback(self):
        socket = SimpleNamespace(identifier='Socket_1',name='Growth',socket_type='NodeSocketFloat',default_value=3.0)
        record = m._input_record({},socket,[])
        self.assertEqual(record['source'],'interface_default')
        self.assertEqual(record['value'],3.0)

    def test_strict_json_and_unavailable_values(self):
        warnings = []
        self.assertIsNone(m._read_value(float('nan'),warnings,'Seed'))
        self.assertEqual(len(warnings),1)
        self.assertEqual(m._read_value(object(),warnings,'Unknown'),{'unavailable':'object'})
        self.assertEqual(m.json_value([float('inf'),1,True,None]),[None,1,True,None])

    def test_opt_out_creates_no_directory(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td)/'metadata'
            self.assertIsNone(m.write_run({'frames':[{'frame':1}]},output))
            self.assertFalse(output.exists())

    def test_negative_frames_join_and_content_hash(self):
        config = {'bridge_version':'1.22.0','procedural_scene':False,'scene_xml_sha256':'hash',
                  'output':{'export_category':'paths','export_run_id':'experiment_a','export_format':'NONE'},
                  'frames':[{'frame':-1,'geometry_nodes_parameters':{'objects':[]},'simulation':{'seed':9}}]}
        with tempfile.TemporaryDirectory() as td:
            descriptor = m.write_run(config,td)
            manifest = json.loads(Path(descriptor['manifest_json']).read_text(encoding='utf-8'))
            entry = manifest['frames'][0]
            path = Path(td)/entry['file']
            record = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(record['frame'],-1)
            self.assertEqual(record['run_id'],'experiment_a')
            self.assertEqual(record['simulation_category'],'paths')
            self.assertEqual(record['record_kind'],'prepared_simulation_inputs')
            self.assertFalse(record['scene_source']['evaluated_per_frame'])
            self.assertEqual(entry['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(config['frames'][0]['geometry_nodes_metadata_file'],str(path))


if __name__ == '__main__':
    unittest.main()
