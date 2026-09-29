"""Import the native test outputs and verify Blender result-to-metadata links."""
import bpy
import importlib.util
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[sys.argv.index('--')+1]).resolve()
spec = importlib.util.spec_from_file_location('metadata_results_test',root/'__init__.py',submodule_search_locations=[str(root)])
b = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = b
spec.loader.exec_module(b)
b.register()
b._ensure_bundled_geometry_nodes(verbose=False)
for category,collection,group,kind in [
    ('paths','simulated_paths','Sionna_Paths','paths_pointcloud'),
    ('coverage_2d','radio_maps','Sionna_radio_map_pathgain_node','radio_map_pointcloud'),
    ('coverage_3d','radio_maps_3d','Sionna_radio_map_3d_pathgain_node','radio_map_3d_pointcloud'),
]:
    config = json.loads((source/category/'config.json').read_text(encoding='utf-8'))
    obj,count,_ = b._create_embedded_point_object(bpy.context.scene,config['output']['results_csv'],config,
        prefix=category,collection_key=collection,group_name=group,result_type=kind,modifier_name='Simulation Results')
    assert count > 0 and len(obj.data.vertices) == count
    assert Path(obj['sionna_geometry_nodes_metadata_json']).is_file()
    assert obj['sionna_export_run_id'] == config['output']['export_run_id']
    assert obj['sionna_export_category'] == category
    assert obj.data.attributes.get('frame') is not None
    if category == 'paths':
        bpy.context.scene.sionna_bridge.workspace_dir = str(source/'analysis')
        manifest = json.loads(Path(config['output']['frames_manifest_json']).read_text(encoding='utf-8'))
        b._attach_channel_analytics_from_manifest(obj, Path(config['output']['frames_manifest_json']).parent)
        study = b._parameter_study.attach(b,bpy.context.scene,obj,config,manifest)
        assert study and study['result_frames'] == 2 and len(study['records']) == 2
        assert all(r['metrics']['path_count'] > 0 for r in study['records'])
        assert Path(obj['sionna_parameter_report']).is_file()
        del obj['sionna_parameter_study']
        legacy = b._parameter_study.dataset_from_object(obj)
        assert [r['metrics'] for r in legacy['records']] == [r['metrics'] for r in study['records']]
        assert b._parameter_study.write_selected(b,bpy.context.scene).is_file()
    print(category,'RESULT_IMPORT_PASS',count)
bpy.ops.wm.save_as_mainfile(filepath=str(source/'verified_results.blend'))
b.unregister()
print('METADATA_RESULT_LINKS_PASS')
