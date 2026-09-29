import copy
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vegetation_metrics as v
import parameter_analysis as a


class VegetationTests(unittest.TestCase):
    def test_leaf_islands_and_supplied_ids(self):
        faces=[(0,1,2),(0,2,3),(4,5,6),(4,6,7)]
        factors,count,tagged,closed,bad=v.leaf_topology(faces,['leaf']*4,[7,7,8,8])
        self.assertEqual((count,tagged,closed,bad),(2,2,0,False))
        np.testing.assert_array_equal(factors,[1,1,1,1])
        self.assertIsNone(v.leaf_topology(faces,['leaf']*4)[2])
        self.assertIsNone(v.leaf_topology(faces,['leaf']*4,[7,0,8,8])[2])

    def test_closed_and_open_leaf_area_convention(self):
        faces=[(0,2,1),(0,1,3),(1,2,3),(2,0,3)]
        factors,count,tagged,closed,bad=v.leaf_topology(faces,['leaf']*4)
        np.testing.assert_array_equal(factors,[.5]*4)
        self.assertEqual(closed,1)
        np.testing.assert_array_equal(v.leaf_topology(faces,['leaf']*4,convention='SINGLE_SURFACE')[0],[1]*4)
        self.assertEqual(v.leaf_topology([(0,1,2)],['leaf'],convention='HALF_SURFACE')[0][0],.5)

    def test_wood_is_not_counted_as_leaf(self):
        self.assertEqual(v.leaf_topology([(0,1,2)],['wood'])[1:4],(0,0,0))

    def test_box_intersections_overlap_and_inside(self):
        self.assertEqual(v.box_interval([-2,0,0],[2,0,0],[-1,-1,-1],[1,1,1]),(1,3))
        self.assertEqual(v.box_interval([0,0,0],[2,0,0],[-1,-1,-1],[1,1,1]),(0,1))
        self.assertIsNone(v.box_interval([-2,2,0],[2,2,0],[-1,-1,-1],[1,1,1]))
        self.assertEqual(v.union_length([(1,3),(2,4),(6,7),None]),4)

    def test_surface_crossings_merge_triangle_diagonal(self):
        triangles=np.array([[[0,-1,-1],[0,1,-1],[0,1,1]],[[0,-1,-1],[0,1,1],[0,-1,1]]],float)
        self.assertEqual(v.surface_hits(triangles,[-2,0,0],[2,0,0]),[2.])
        self.assertEqual(v.surface_hits(triangles,[2,0,0],[-2,0,0]),[2.])
        self.assertEqual(v.surface_hits(triangles,[0,0,0],[2,0,0]),[])
        self.assertEqual(v.surface_hits(triangles,[-2,3,0],[2,3,0]),[])

    def test_corridor_clips_edges_and_endpoints(self):
        triangles=np.array([[[0,-2,-2],[0,2,-2],[0,2,2]],[[0,-2,-2],[0,2,2],[0,-2,2]]],float)
        self.assertAlmostEqual(v.corridor_area(triangles,np.ones(2),[-2,0,0],[2,0,0],1),1)
        self.assertAlmostEqual(v.corridor_area(triangles,np.ones(2)*.5,[-2,0,0],[2,0,0],1),.5)
        self.assertEqual(v.corridor_area(triangles+[-3,0,0],np.ones(2),[-2,0,0],[2,0,0],1),0)
        self.assertIsNone(v.corridor_area(triangles,np.ones(2),[0,0,0],[0,0,0],1))
        # Same square rotated into XY for a vertical link.
        self.assertAlmostEqual(v.corridor_area(triangles[:,:,[1,2,0]],np.ones(2),[0,0,-2],[0,0,2],1),1)

    def test_bounds_and_degenerate_volume(self):
        m=v.bounds_metrics([0,0,0],[2,3,4],12)
        self.assertEqual(m['leaf_area_density_bbox_m_inv'],.5)
        self.assertEqual(m['leaf_area_index_bbox'],2)
        self.assertIsNone(v.bounds_metrics([0,0,0],[2,3,0],12)['leaf_area_density_bbox_m_inv'])

    def test_link_values_follow_pair_identity_not_list_order(self):
        frame={'frame':1,'vegetation_metrics':{'scene':{'leaf_area_estimate_m2':8},'objects':[],
            'links':[{'tx':'T','rx':'B','metrics':{'leaf_surface_crossings':2}},
                     {'tx':'T','rx':'A','metrics':{'leaf_surface_crossings':1}}]}}
        frame['parameter_study_inputs']=a.frame_inputs(frame,{})
        config={'frames':[frame],'output':{'export_run_id':'test'},'procedural_scene':True}
        links=[{'frame':1,'pos_idx':0,'tx_name':'T','rx_name':'A','path_count':1,'total_power_db':-10},
               {'frame':1,'pos_idx':1,'tx_name':'T','rx_name':'B','path_count':1,'total_power_db':-20}]
        study=a.build_study(config,{'frames':[{'frame':1,'channel_analytics':{'links':links}}]})
        for r,expected in zip(study['records'],[1,2]):
            self.assertEqual(r['values']['vegetation/link/leaf_surface_crossings'],expected)
            self.assertEqual(r['values']['vegetation/scene/leaf_area_estimate_m2'],8)
        self.assertEqual(study['parameters']['vegetation/link/leaf_surface_crossings']['role'],'descriptor')

    def test_empty_scene_and_zero_length_link(self):
        result=v.measure_packets([], [{'name':'T','position':[0,0,0]}], [{'name':'R','position':[0,0,0]}])
        self.assertEqual(result['scene']['leaf_component_count'],0)
        self.assertIsNone(result['links'][0]['metrics']['leaf_surface_crossings'])
        self.assertIsNone(result['links'][0]['metrics']['corridor_leaf_area_density_m_inv'])


if __name__=='__main__':unittest.main()
