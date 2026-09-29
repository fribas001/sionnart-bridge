import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import parameter_analysis as a
import geometry_nodes_metadata as g


def fixture():
    config={'output':{'export_run_id':'test_a'},'scene_name':'Tree','procedural_scene':True,
            'antenna':{'tx':{'num_rows':4}},'frames':[]}
    result={'frames':[]}
    for frame in range(1,5):
        config['frames'].append({'frame':frame,'simulation':{'seed':42},'materials':[{'blender_name':'leaves','model':'ITU'}],
            'parameter_study_inputs':{'frame':frame,'parameters':{'density':{'label':'Leaf Density','role':'input','kind':'number','unit':'','value':frame}},'warnings':[]}})
        result['frames'].append({'frame':frame,'channel_analytics':{'source':'all_valid_paths_first_antenna_pair','links':[
            {'frame':frame,'pos_idx':0,'tx_name':'TX','rx_name':'RX','path_count':3,'total_power_db':-100+frame*2,'strongest_path_gain_db':-103+frame*2,'rms_delay_spread_ns':frame*.5,'los_available':False},
            {'frame':frame,'pos_idx':1,'tx_name':'TX','rx_name':'RX2','path_count':1,'total_power_db':-90-frame}]}})
    return config,result


class ParameterTests(unittest.TestCase):
    def test_per_link_statistics_and_correlation(self):
        config,result=fixture();study=a.build_study(config,result)
        stat=a.analyze(study,'density','total_power_db',0)['stats']
        self.assertEqual(stat['n'],4);self.assertEqual(stat['delta'],6)
        self.assertEqual(stat['mean'],-95);self.assertEqual(stat['pearson_r'],1)
        self.assertEqual(a.analyze(study,'density','total_power_db',1)['stats']['pearson_r'],-1)

    def test_missing_path_gain_is_not_a_sentinel(self):
        config,result=fixture();result['frames'][2]['channel_analytics']['links'][0].update(path_count=0,total_power_db=-600)
        study=a.build_study(config,result);values=a.analyze(study,'density','total_power_db',0)
        self.assertIsNone(values['points'][2]['y']);self.assertEqual(values['stats']['missing'],1)
        self.assertEqual(values['stats']['min'],-98)

    def test_missing_frame_and_duplicate_join(self):
        config,result=fixture();result['frames'].pop()
        study=a.build_study(config,result);self.assertTrue(any('No result summaries' in s for s in study['warnings']))
        result['frames'].append(result['frames'][0])
        with self.assertRaisesRegex(ValueError,'Duplicate result'):a.build_study(config,result)

    def test_run_id_mismatch_rejected(self):
        c,r=fixture()
        with self.assertRaisesRegex(ValueError,'identifiers disagree'):
            a.from_export({'run_id':'wrong','categories':{'paths':{'parameters':c,'results_summary':r}}})

    def test_unchanged_and_too_few_points(self):
        self.assertFalse(a.variation([1,1+1e-10])['varies'])
        self.assertIsNone(a.pearson([1,2],[3,4]))
        self.assertIsNone(a.pearson([1,1,1],[3,4,5]))
        self.assertEqual(a.variation([None,float('nan')])['n'],0)

    def test_sequence_protocol_mathutils_fix(self):
        class Sequence:
            def __getitem__(self,i):
                if i>=3:raise IndexError
                return i*.5
        self.assertEqual(g.json_value(Sequence()),[0,.5,1])

    def test_material_diff_and_vector_components(self):
        snapshot={'objects':[{'object':{'name':'Tree'},'modifiers':[{'name':'Tree Nodes','stack_index':0,'show_viewport':True,
            'inputs':[{'identifier':'Socket_1','name':'Scale','value':[1.,2.,3.]}]}]}],
            'node_groups':{'key':{'id':{'name':'Tree group'},'nodes':[{'name':'Set Material','type':'GeometryNodeSetMaterial','mute':False,
                'inputs':[{'identifier':'Material','name':'Material','socket_type':'NodeSocketMaterial','linked':False,'default_value':{'datablock':{'name':'itu_glass'}}}]}]}}}
        captured=a.frame_inputs({'frame':1},snapshot)
        self.assertEqual(len([k for k in captured['parameters'] if k.endswith(('/0','/1','/2'))]),3)
        self.assertTrue(any(v['value']=='itu_glass' for v in captured['parameters'].values()))
        c,r=fixture();one=a.build_study(c,r);two=copy.deepcopy(one);two['context']['antenna/tx/num_rows']=1
        self.assertEqual(a.context_differences([one,two])[0]['label'],'antenna/tx/num_rows')

    def test_import_zip_and_safe_report(self):
        c,r=fixture();c['scene_name']='</script><script>alert(1)</script>'
        export={'run_id':'test_a','categories':{'paths':{'parameters':c,'results_summary':r}}}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'export.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('folder/run.metadata.json',json.dumps(export))
            study=a.load_export(p);report=a.write_report(Path(td)/'report.html',[study]).read_text(encoding='utf-8')
            self.assertNotIn('</script><script>alert(1)</script>',report)
            self.assertNotIn('STUDY_DATA_PLACEHOLDER',report)
            self.assertIn('test_a',report)


if __name__=='__main__':unittest.main()
