"""Blender workflow panels. Dependencies are supplied once by the entry module.
No import of the entry module, registration side effects, or runtime probes here.
"""
import bpy

def build_panels(bridge):

    def draw_runtime(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        box.prop(settings, 'runtime_mode', text='Runtime')
        if bridge._runtime_mode(settings) == 'BLENDER':
            box.label(text='Blender 5.2 Python; no external interpreter required', icon='CHECKMARK')
            box.prop(settings, 'sionna_site_packages')
            detected_packages = bridge._resolve_sionna_site_packages(settings)
            if detected_packages is not None:
                box.label(text=f'Sionna packages: {detected_packages}', icon='CHECKMARK')
            else:
                box.label(text='Sionna packages not detected', icon='ERROR')
        else:
            box.prop(settings, 'sionna_python')
        box.label(text='Scene Export: Integrated Blender 5.2 Mitsuba XML/PLY', icon='CHECKMARK')
        box.prop(settings, 'drjit_libllvm_path')
        resolved_python, python_error = bridge._resolve_python_executable(settings)
        if resolved_python is not None:
            box.label(text=f'Worker Python: {resolved_python}', icon='CHECKMARK')
        else:
            box.label(text=python_error, icon='ERROR')
        detected_llvm = bridge._resolve_drjit_libllvm(settings, resolved_python) if resolved_python else bridge._resolve_drjit_libllvm(settings)
        if detected_llvm is not None:
            box.label(text=f'Dr.Jit LLVM: {detected_llvm}', icon='CHECKMARK')
        elif bridge.os.name == 'nt':
            box.label(text='LLVM-C.dll not detected (only needed if CUDA is unavailable)', icon='INFO')
        box.prop(settings, 'workspace_dir')
        row = box.row(align=True)
        row.operator('sionna_bridge.test_environment', text='Test Runtime')
        row.operator('sionna_bridge.open_workspace', text='Open Workspace')

    def draw_scene(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        row = box.row(align=True)
        row.operator('sionna_bridge.create_environment', text='Create / Repair Env')
        row.operator('sionna_bridge.move_selected_to_scene', text='Move to Static Scene')
        box.operator('sionna_bridge.move_selected_to_procedural', text='Move to Procedural Geometry', icon='GEOMETRY_NODES')

    def draw_solver(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        box.prop(settings, 'frequency_ghz')
        noise = box.column(align=True)
        noise.label(text='Power and Noise', icon='LIGHT')
        row = noise.row(align=True)
        row.prop(settings, 'bandwidth_mhz', text='Bandwidth (MHz)')
        row.prop(settings, 'temperature_k', text='Temperature (K)')
        arrays = box.column(align=True)
        arrays.label(text='Antenna Arrays — shared by role', icon='OUTLINER_OB_LIGHT')
        tx_box = arrays.column(align=True)
        tx_box.label(text='Transmitters (TX)')
        tx_box.prop(settings, 'tx_antenna_pattern', text='Pattern')
        row = tx_box.row(align=True)
        row.prop(settings, 'tx_array_rows', text='Rows')
        row.prop(settings, 'tx_array_cols', text='Columns')
        row = tx_box.row(align=True)
        row.prop(settings, 'tx_vertical_spacing', text='Vertical λ')
        row.prop(settings, 'tx_horizontal_spacing', text='Horizontal λ')
        row = tx_box.row(align=True)
        row.prop(settings, 'tx_polarization', text='Polarization')
        row.prop(settings, 'tx_polarization_model', text='Model')
        op = tx_box.operator('sionna_bridge.sync_role_names', text='Sync TX Names')
        op.role = 'TX'
        if settings.simulate_paths:
            rx_box = arrays.column(align=True)
            rx_box.label(text='Receivers (RX)')
            rx_box.prop(settings, 'rx_antenna_pattern', text='Pattern')
            row = rx_box.row(align=True)
            row.prop(settings, 'rx_array_rows', text='Rows')
            row.prop(settings, 'rx_array_cols', text='Columns')
            row = rx_box.row(align=True)
            row.prop(settings, 'rx_vertical_spacing', text='Vertical λ')
            row.prop(settings, 'rx_horizontal_spacing', text='Horizontal λ')
            row = rx_box.row(align=True)
            row.prop(settings, 'rx_polarization', text='Polarization')
            row.prop(settings, 'rx_polarization_model', text='Model')
            op = rx_box.operator('sionna_bridge.sync_role_names', text='Sync RX Names')
            op.role = 'RX'
        row = box.row(align=True)
        row.prop(settings, 'max_depth')
        row.prop(settings, 'seed')
        box.prop(settings, 'samples_per_src')
        if settings.simulate_paths:
            box.prop(settings, 'deterministic_paths')
        if settings.simulate_paths:
            box.prop(settings, 'max_num_paths_per_src')
        box.prop(settings, 'sim_numeric_id')
        box.prop(settings, 'timeline_mode')
        if settings.timeline_mode != 'CURRENT':
            box.prop(settings, 'timeline_step')
        if settings.simulate_paths:
            box.prop(settings, 'enable_mobility_doppler')
        grid = box.grid_flow(row_major=True, columns=2, even_columns=True)
        grid.prop(settings, 'enable_los')
        grid.prop(settings, 'enable_reflection')
        grid.prop(settings, 'enable_refraction')
        grid.prop(settings, 'enable_diffuse')
        grid.prop(settings, 'enable_diffraction')
        grid.prop(settings, 'enable_edge_diffraction')
        grid.prop(settings, 'diffraction_lit_region')

    def draw_materials(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        row = box.row(align=True)
        row.operator('sionna_bridge.create_default_materials', text='Create Default Materials', icon='ADD')
        row.operator('sionna_bridge.pick_active_material', text='Use Active', icon='EYEDROPPER')
        row = box.row(align=True)
        row.prop(settings, 'plant_library_choice', text='Plant')
        row.operator('sionna_bridge.select_plant_material', text='Load Preset', icon='MATERIAL')
        box.prop(settings, 'material_selection', text='Material')
        material = settings.material_selection
        if material is not None:
            config = material.sionna_radio
            row = box.row(align=True)
            row.operator('sionna_bridge.enable_material', text='Enable / Prefix itu_', icon='CHECKMARK')
            row.operator('sionna_bridge.assign_material', text='Assign to Selected', icon='MATERIAL')
            if not material.name.lower().startswith('itu_'):
                box.label(text='Material name must start with itu_ for export.', icon='ERROR')
            if config.enabled or material.name.lower().startswith('itu_'):
                box.prop(config, 'model')
                if config.model == 'ITU':
                    box.prop(config, 'itu_type')
                elif config.model == 'VEGETATION':
                    bridge._plant_blender.draw(bridge, box, context, config)
                else:
                    row = box.row(align=True)
                    row.prop(config, 'relative_permittivity')
                    row.prop(config, 'conductivity')
                box.prop(config, 'thickness')
                row = box.row(align=True)
                row.prop(config, 'scattering_coefficient')
                row.prop(config, 'xpd_coefficient')
                box.prop(config, 'scattering_pattern')
                if config.scattering_pattern == 'directive':
                    box.prop(config, 'directive_alpha_r')
                elif config.scattering_pattern == 'backscattering':
                    row = box.row(align=True)
                    row.prop(config, 'backscatter_alpha_r')
                    row.prop(config, 'backscatter_alpha_i')
                    box.prop(config, 'backscatter_lambda')

    def draw_procedural(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        box.prop(settings, 'procedural_geometry_enabled')
        if settings.procedural_geometry_enabled:
            box.prop(settings, 'procedural_capture_analytics')
            box.prop(settings, 'procedural_skip_failed_frames')
        box.operator('sionna_bridge.move_selected_to_procedural', text='Move Selected to Procedural Geometry')

    def draw_devices(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        row = box.row(align=True)
        op = row.operator('sionna_bridge.add_device', text='Add TX', icon='ADD')
        op.role = 'TX'
        op = row.operator('sionna_bridge.add_device', text='Add RX', icon='ADD')
        op.role = 'RX'
        row = box.row(align=True)
        op = row.operator('sionna_bridge.mark_selected', text='Mark TX')
        op.role = 'TX'
        op = row.operator('sionna_bridge.mark_selected', text='Mark RX')
        op.role = 'RX'
        row.operator('sionna_bridge.clear_role', text='Clear', icon='X')
        active = context.active_object
        active_role = str(active.get('sionna_role', '')).upper() if active is not None else ''
        sub = box.column(align=True)
        expanded_antenna = bool(settings.ui_show_device_antenna)
        sub.prop(settings, 'ui_show_device_antenna', text='Per-device Orientation', icon='TRIA_DOWN' if expanded_antenna else 'TRIA_RIGHT', emboss=False)
        if expanded_antenna:
            if active is None or active_role not in {'TX', 'RX'}:
                sub.label(text='Select a marked TX or RX', icon='INFO')
            else:
                config = active.sionna_device_config
                if active_role == 'TX':
                    sub.prop(config, 'tx_power_dbm', text='Transmit Power (dBm)')
                sub.prop(config, 'orientation_mode')
                if config.orientation_mode == 'LOOK_AT':
                    sub.prop(config, 'look_at_target')
                    if config.look_at_target == active:
                        sub.label(text='A device cannot look at itself', icon='ERROR')
                elif config.orientation_mode == 'FIXED':
                    row = sub.row(align=True)
                    row.prop(config, 'fixed_alpha')
                    row.prop(config, 'fixed_beta')
                    row.prop(config, 'fixed_gamma')
                row = sub.row(align=True)
                row.operator('sionna_bridge.read_device_name', text='Read Name', icon='IMPORT')
                row.operator('sionna_bridge.apply_device_name', text='Apply Compact Name', icon='CHECKMARK')


    def draw_motion(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        motion_box = box.column(align=True)
        motion_box.prop(settings, 'motion_template_enabled', text='TX / RX Motion Path', icon='ANIM')
        if settings.motion_template_enabled:
            motion_box.prop(settings, 'motion_template_style', text='Style')
            motion_box.prop(settings, 'motion_template_device', text='Associated TX / RX')
            if settings.motion_template_style == 'GRID':
                row = motion_box.row(align=True)
                row.prop(settings, 'motion_template_grid_columns', text='Columns')
                row.prop(settings, 'motion_template_grid_rows', text='Rows')
                row = motion_box.row(align=True)
                row.prop(settings, 'motion_template_grid_column_spacing', text='Column Spacing')
                row.prop(settings, 'motion_template_grid_row_spacing', text='Row Spacing')
                motion_box.prop(settings, 'motion_template_start_frame', text='Start Frame')
                motion_box.prop(settings, 'motion_template_set_scene_range', text='Set Scene Range to Path')
                count = int(settings.motion_template_grid_columns) * int(settings.motion_template_grid_rows)
                end_frame = int(settings.motion_template_start_frame) + max(0, count - 1)
                motion_box.label(text=f'{count} points = frames {int(settings.motion_template_start_frame)}-{end_frame}; serpentine order.', icon='INFO')
                motion_box.label(text='Use Timeline Auto/Range to compute the complete grid sweep.', icon='INFO')
            elif settings.motion_template_style == 'POINT_CLOUD':
                motion_box.prop(settings, 'motion_template_pointcloud', text='PointCloud Path')
                motion_box.prop(settings, 'motion_template_start_frame', text='Start Frame')
                motion_box.prop(settings, 'motion_template_set_scene_range', text='Set Scene Range to Path')
                source = settings.motion_template_pointcloud
                count = len(source.data.points) if source is not None and source.data is not None else 0
                end_frame = int(settings.motion_template_start_frame) + max(0, count - 1)
                if source is None:
                    motion_box.label(text='Choose a PointCloud with the eyedropper.', icon='EYEDROPPER')
                elif count < 1:
                    motion_box.label(text=f'{source.name} contains no points.', icon='ERROR')
                else:
                    motion_box.label(text=f'{count} points = frames {int(settings.motion_template_start_frame)}-{end_frame}.', icon='INFO')
                    motion_box.label(text='Mapping: point index i → frame Start+i (one frame per point).', icon='INFO')
            template_device = settings.motion_template_device
            existing_template = bridge._sweep_template_object(template_device) if template_device is not None else None
            row = motion_box.row(align=True)
            source_ready = settings.motion_template_style != 'POINT_CLOUD' or settings.motion_template_pointcloud is not None
            row.enabled = template_device is not None and source_ready
            is_pc = settings.motion_template_style == 'POINT_CLOUD'
            row.operator('sionna_bridge.generate_motion_template', text='Update PointCloud Path' if existing_template is not None and is_pc else 'Connect PointCloud Path' if is_pc else 'Update Grid' if existing_template is not None else 'Generate Grid', icon='ANIM')
            if existing_template is not None:
                row = motion_box.row(align=True)
                row.operator('sionna_bridge.select_motion_template', text='Select Source' if is_pc else 'Select Grid', icon='POINTCLOUD_DATA' if is_pc else 'EMPTY_AXIS')
                row.operator('sionna_bridge.remove_motion_template', text='Disconnect', icon='X')
                if is_pc:
                    source_obj = bridge._sweep_source_object(template_device)
                    source_name = source_obj.name if source_obj is not None else 'missing source'
                    motion_box.label(text=f'Live index follow: {source_name}; point index follows the current frame.', icon='INFO')
                    if source_obj is not None:
                        try:
                            start = int(template_device.get('sionna_sweep_start_frame', 1))
                            raw_index = int(context.scene.frame_current) - start
                            count_now = len(source_obj.data.points)
                            index_now = max(0, min(raw_index, max(0, count_now - 1)))
                            expected = source_obj.matrix_world @ source_obj.data.points[index_now].co
                            actual = template_device.matrix_world.translation
                            error_m = float((actual - expected).length)
                            motion_box.label(text=f'Frame {context.scene.frame_current} → point {index_now}; alignment error {error_m:.6g} m', icon='CHECKMARK' if error_m <= 1e-05 else 'ERROR')
                        except Exception:
                            pass
                else:
                    motion_box.label(text=f'Connected: {existing_template.name}. Move/rotate/scale the grid to reposition the sweep.', icon='INFO')
            elif template_device is None:
                motion_box.label(text='Choose a marked TX or RX to create the sweep.', icon='INFO')
            elif is_pc and settings.motion_template_pointcloud is None:
                motion_box.label(text='Choose the PointCloud path before connecting.', icon='INFO')
            elif not is_pc:
                motion_box.label(text='The grid is centered on the device when generated and stays fully movable.', icon='INFO')


    def draw_execution(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        dynamic_box = box.column(align=True)
        dynamic_box.prop(settings, 'dynamic_mode', text='Dynamic Mode', icon='FILE_REFRESH')
        if settings.dynamic_mode:
            dynamic_box.label(text='TX/RX movement watcher active', icon='CHECKMARK')
            dynamic_box.prop(settings, 'auto_compute_paths_delay', text='Move Debounce')
        else:
            dynamic_box.label(text='Off: no movement-driven Sionna background watcher', icon='INFO')
        box.prop(settings, 'refresh_scene_before_run')
        if not settings.refresh_scene_before_run and not bridge._procedural_scene_active(context.scene):
            box.label(text='Using cached geometry: refresh after mesh edits.', icon='INFO')
        metadata_box = box.column(align=True)
        metadata_box.prop(settings, 'export_geometry_nodes_metadata')
        metadata_box.prop(settings, 'parameter_analysis_enabled')
        metadata_box.prop(settings, 'vegetation_metrics_enabled')
        if settings.vegetation_metrics_enabled:
            vegetation = metadata_box.box()
            vegetation.prop(settings, 'vegetation_corridor_width')
            vegetation.prop(settings, 'vegetation_leaf_area_convention')
            vegetation.operator('sionna_bridge.vegetation_measurements', text='Inspect Vegetation', icon='VIEWZOOM')
            vegetation.operator('sionna_bridge.vegetation_measurements', text='Vegetation Definitions & References', icon='HELP').show_definitions = True
            vegetation.label(text='Per object and frame; vegetation materials only.')
        if settings.export_geometry_nodes_metadata:
            metadata_box.label(text='scene + subcollections; one JSON per simulation frame.', icon='INFO')
            metadata_box.label(text='Saved independently of result export.')
        if settings.last_geometry_nodes_metadata_path:
            metadata_box.operator('sionna_bridge.open_geometry_nodes_metadata', text='Open Geometry Nodes Metadata', icon='FILE_FOLDER')
        box.prop(settings, 'export_format', text='Export Results')
        if settings.export_format == 'NONE':
            box.label(text='ISAC dataset is retained.' if settings.isac_enabled and settings.simulate_paths else 'Results stay in Blender; temporary worker files are removed.', icon='INFO')
        elif settings.export_format == 'CSV':
            box.label(text='Keeps one simulation-specific CSV + metadata JSON.', icon='INFO')
        else:
            box.label(text='Keeps one HDF5 with frame-stacked coverage + metadata JSON.', icon='INFO')
            tile_dataset = bridge._find_tile_spatial_dataset()
            if tile_dataset is not None:
                box.label(text=f'Tile_spacial_dataset detected: {len(tile_dataset.data.points)} tiles will be linked', icon='LINKED')
            else:
                box.label(text='No Tile_spacial_dataset detected; HDF5 coverage exports remain standalone', icon='INFO')
        selected = []
        if settings.simulate_paths:
            selected.append('Paths')
        if settings.simulate_radio_map:
            selected.append('Radio Map')
        if settings.simulate_radio_map_3d:
            selected.append('3D Radio Map')
        row = box.row()
        row.scale_y = 1.5
        row.enabled = bridge._processes_idle() and bool(selected)
        row.operator('sionna_bridge.run_selected', text='Run Simulation', icon='PLAY')
        row = box.row(align=True)
        row.operator('sionna_bridge.export_scene', text='Refresh Scene Cache')
        row.operator('sionna_bridge.open_last_run', text='Open Last Run')

    def draw_paths(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        live_box = box.column(align=True)
        live_box.enabled = bool(settings.dynamic_mode)
        live_box.prop(settings, 'auto_compute_paths_on_tx_move', text='Auto Compute on TX / RX Move', icon='FILE_REFRESH')
        if not settings.dynamic_mode:
            live_box.label(text='Enable Dynamic Mode in Simulation for live updates.', icon='INFO')
        elif settings.auto_compute_paths_on_tx_move:
            if tx_count == 0:
                live_box.label(text='Add at least one TX to enable automatic runs.', icon='ERROR')
            elif rx_count == 0:
                live_box.label(text='Add at least one RX to enable automatic runs.', icon='ERROR')
            else:
                live_box.label(text='Current frame only; newest TX/RX position wins while busy.', icon='INFO')
        box.prop(settings, 'isac_enabled')
        if settings.isac_enabled:
            box.prop(settings, 'isac_capture_pose')
            if settings.isac_capture_pose:
                box.prop(settings, 'isac_subject')
                box.prop(settings, 'isac_tissue_preset')
                box.prop(settings, 'isac_proxy_thickness')
                box.operator('sionna_bridge.human_material')
            box.prop(settings, 'isac_activity')
            row=box.column(align=True)
            row.prop(settings, 'isac_plots');row.prop(settings, 'isac_csv');row.prop(settings, 'isac_csi')
            if settings.isac_csi:box.prop(settings, 'isac_csi_bins')
            box.prop(settings,'isac_show_metadata',icon='TRIA_DOWN' if settings.isac_show_metadata else 'TRIA_RIGHT',emboss=False)
            if settings.isac_show_metadata:
                for prop in ['isac_subject_id','isac_episode_id','isac_environment_id','isac_license']:box.prop(settings,prop)
            box.label(text='Full CIR export is independent of display path limits.')
        box.prop(settings,'isac_show_hud',icon='TRIA_DOWN' if settings.isac_show_hud else 'TRIA_RIGHT',emboss=False)
        if settings.isac_show_hud:
            body=box.column()
            body.prop(settings,'isac_hud')
            row=body.row(align=True);row.prop(settings,'isac_hud_tx');row.prop(settings,'isac_hud_rx')
            body.prop(settings,'isac_hud_corner');body.prop(settings,'isac_hud_scale')
            body.operator('sionna_bridge.isac_overlay')
        box.prop(settings, 'pointcloud_top_paths_per_pair')
        box.prop(settings, 'post_run_action')
        if settings.post_run_action == 'CURVES':
            box.prop(settings, 'max_imported_paths')
            box.prop(settings, 'path_thickness')
        box.prop(settings, 'geometry_nodes_group_name')
        if settings.export_format == 'CSV':
            row = box.row(align=True)
            row.operator('sionna_bridge.copy_csv_path', text='Copy Exported CSV')

    def draw_map2d(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        live_box = box.column(align=True)
        live_box.enabled = bool(settings.dynamic_mode)
        live_box.prop(settings, 'auto_compute_radio_map_on_device_move', text='Auto Compute on TX Move', icon='FILE_REFRESH')
        if not settings.dynamic_mode:
            live_box.label(text='Enable Dynamic Mode in Simulation for live updates.', icon='INFO')
        elif settings.auto_compute_radio_map_on_device_move:
            live_box.prop(settings, 'radio_map_auto_center_on_tx', text='Center Map on Moving TX', icon='PIVOT_BOUNDBOX')
            if tx_count == 0:
                live_box.label(text='Add at least one TX to enable automatic coverage.', icon='ERROR')
            elif bridge._normalize_radio_map_surface_mode(settings.radio_map_surface_mode) == 'PROJECTED':
                live_box.label(text='TX centering applies to Planar Grid only; Projected Mesh uses its mesh surface.', icon='INFO')
            elif settings.radio_map_auto_center_on_tx:
                live_box.label(text='Follow TX within the map plane; normal offset stays fixed.', icon='INFO')
            else:
                live_box.label(text='Current frame only; RX movement does not affect coverage maps.', icon='INFO')
        box.prop(settings, 'radio_map_surface_mode', text='Map Surface')
        box.prop(settings, 'radio_map_metric', text='Map Metric')
        surface_mode = bridge._normalize_radio_map_surface_mode(settings.radio_map_surface_mode)
        if surface_mode == 'PROJECTED':
            box.prop(settings, 'radio_map_reference_mesh', text='Reference Mesh')
            if settings.radio_map_reference_mesh is None:
                box.label(text='Select the mesh that will receive the radio map.', icon='ERROR')
            if settings.radio_map_metric != 'path_gain':
                box.label(text='Projected Mesh currently supports Path Gain only.', icon='ERROR')
        else:
            box.prop(settings, 'radio_map_plane')
            plane = settings.radio_map_plane
            if plane == 'CUSTOM':
                col = box.column(align=True)
                for axis in ('x', 'y', 'z'):
                    col.prop(settings, 'radio_map_rotation_' + axis)
            axes = {'XY': ('X', 'Y'), 'XZ': ('X', 'Z'), 'YZ': ('Y', 'Z')}.get(plane, ('U', 'V'))
            row = box.row(align=True)
            row.prop(settings, 'radio_map_center_x')
            row.prop(settings, 'radio_map_center_y')
            box.prop(settings, 'radio_map_height', text='Height' if plane == 'XY' else 'Center Z')
            row = box.row(align=True)
            row.prop(settings, 'radio_map_size_x', text='Area Size ' + axes[0])
            row.prop(settings, 'radio_map_size_y', text='Area Size ' + axes[1])
            row = box.row(align=True)
            row.prop(settings, 'radio_map_cell_size_x', text='Cell Size ' + axes[0])
            row.prop(settings, 'radio_map_cell_size_y', text='Cell Size ' + axes[1])
        box.prop(settings, 'radio_map_point_radius')
        box.prop(settings, 'radio_map_replace_existing')
        if settings.export_format == 'CSV':
            row = box.row(align=True)
            row.operator('sionna_bridge.copy_radio_map_csv', text='Copy Exported CSV')

    def draw_map3d(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        live_box = box.column(align=True)
        live_box.enabled = bool(settings.dynamic_mode)
        live_box.prop(settings, 'auto_compute_radio_map_3d_on_device_move', text='Auto Compute on TX Move', icon='FILE_REFRESH')
        if not settings.dynamic_mode:
            live_box.label(text='Enable Dynamic Mode in Simulation for live updates.', icon='INFO')
        elif settings.auto_compute_radio_map_3d_on_device_move:
            live_box.prop(settings, 'radio_map_3d_auto_center_on_tx', text='Center Volume on Moving TX', icon='PIVOT_BOUNDBOX')
            if tx_count == 0:
                live_box.label(text='Add at least one TX to enable automatic 3D coverage.', icon='ERROR')
            elif settings.radio_map_3d_auto_center_on_tx:
                live_box.label(text='Auto runs follow the moved TX in X/Y/Z; volume size stays unchanged.', icon='INFO')
            else:
                live_box.label(text='Current frame only; RX movement does not affect coverage maps.', icon='INFO')
        box.prop(settings, 'radio_map_3d_metric', text='Map Metric')
        row = box.row(align=True)
        row.prop(settings, 'radio_map_3d_center_x')
        row.prop(settings, 'radio_map_3d_center_y')
        box.prop(settings, 'radio_map_3d_center_z')
        row = box.row(align=True)
        row.prop(settings, 'radio_map_3d_size_x')
        row.prop(settings, 'radio_map_3d_size_y')
        box.prop(settings, 'radio_map_3d_size_z')
        row = box.row(align=True)
        row.prop(settings, 'radio_map_3d_cell_size_x')
        row.prop(settings, 'radio_map_3d_cell_size_y')
        box.prop(settings, 'radio_map_3d_cell_size_z')
        box.prop(settings, 'radio_map_3d_point_radius')
        box.prop(settings, 'radio_map_3d_replace_existing')

    def draw_status(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        width = max(52, int(getattr(context.region, 'width', 700) / 7.2))
        bridge._draw_wrapped_text(box, settings.last_status, width=width, icon='INFO')
        if settings.last_status_details:
            detail_box = box.column(align=True)
            detail_box.label(text='Full details', icon='TEXT')
            bridge._draw_wrapped_text(detail_box, settings.last_status_details, width=width)
        row = box.row(align=True)
        row.operator('sionna_bridge.copy_full_status', text='Copy Full Status', icon='COPY_ID')
        row.operator('sionna_bridge.open_status_log', text='Open Log / Run Folder', icon='FILE_FOLDER')
        try:
            export_report = bridge.json.loads(settings.procedural_export_report_json) if settings.procedural_export_report_json else {}
        except Exception:
            export_report = {}
        failed_exports = export_report.get('failed_frames', []) if isinstance(export_report, dict) else []
        if failed_exports:
            sub = box.column(align=True)
            sub.label(text=f"Procedural export: {len(export_report.get('exported_frames', []))} succeeded, {len(failed_exports)} skipped", icon='ERROR')
            for item in failed_exports[:20]:
                reason = str(item.get('reason', 'Unknown export error')).replace('\n', ' ')
                if len(reason) > 105:
                    reason = reason[:102] + '...'
                sub.label(text=f"F{int(item.get('frame', 0)):04d}: {reason}")
            if len(failed_exports) > 20:
                sub.label(text=f'...and {len(failed_exports) - 20} more failed frame(s)')
            if settings.procedural_export_report_path:
                sub.label(text=f'Report: {bridge.Path(settings.procedural_export_report_path).name}')
        if settings.last_paths_object:
            box.label(text=f'Paths object: {settings.last_paths_object}', icon='POINTCLOUD_DATA')
        if settings.last_radio_map_object:
            box.label(text=f'Radio map object: {settings.last_radio_map_object}', icon='POINTCLOUD_DATA')
        if settings.last_radio_map_3d_object:
            box.label(text=f'3D radio map: {settings.last_radio_map_3d_object}', icon='VOLUME_DATA')
        if settings.last_export_path:
            export_label = 'HDF5' if str(settings.last_export_path).lower().endswith(('.h5', '.hdf5')) else 'CSV'
            box.label(text=f'Last {export_label} export: {bridge.Path(settings.last_export_path).name}', icon='FILE')
        if settings.last_export_metadata_path:
            box.label(text=f'Metadata: {bridge.Path(settings.last_export_metadata_path).name}', icon='TEXT')

    def draw_parameters(self, context):
        box = self.layout
        settings = context.scene.sionna_bridge
        box.prop(settings, 'parameter_analysis_enabled')
        box.prop(settings, 'parameter_study_source', text='Analyze')
        if settings.parameter_study_source == 'RESULT':
            box.prop(settings, 'parameter_study_object')
            if settings.parameter_study_object is None:
                box.label(text='Uses the active or latest paths result.', icon='INFO')
        else:
            box.prop(settings, 'parameter_study_imported')
        row = box.row(align=True)
        row.operator('sionna_bridge.import_parameter_run', text='Import Export JSON / ZIP', icon='IMPORT')
        box.prop(settings, 'parameter_study_reference', text='Compare with')
        op = box.operator('sionna_bridge.import_parameter_run', text='Import Reference Run', icon='IMPORT')
        op.as_reference = True
        row = box.row()
        row.scale_y = 1.3
        row.operator('sionna_bridge.open_parameter_plots', text='Open Parameter Plots', icon='GRAPH')
        box.label(text='Choose X, Y and TX/RX link in the report.')
        box.label(text='First antenna pair; descriptive statistics.')
        box.label(text=settings.parameter_study_status)

    def draw_analytics(self, context):
        layout = self.layout
        box = layout
        settings = context.scene.sionna_bridge
        tx_count = len(bridge._device_objects(context.scene, 'TX'))
        rx_count = len(bridge._device_objects(context.scene, 'RX'))
        row = box.row(align=True)
        row.prop(settings, 'analytics_source', text='')
        row.prop(settings, 'analytics_scope', text='')
        box.prop(settings, 'analytics_auto_refresh')
        if settings.analytics_source == 'PATHS':
            controls = box.column(align=True)
            controls.label(text='Channel analysis')
            row = controls.row(align=True)
            row.prop(settings, 'analytics_pair_index')
            row.prop(settings, 'analytics_delay_reference', text='')
            row = controls.row(align=True)
            row.prop(settings, 'analytics_significant_path_threshold_db')
            row.prop(settings, 'analytics_pdp_bins')
            controls.prop(settings, 'analytics_cir_component_limit')
            controls.label(text='CIR component and PDP limits apply to the next simulation.', icon='INFO')
        else:
            box.prop(settings, 'analytics_map_threshold')
        if settings.analytics_scope == 'ALL':
            box.prop(settings, 'analytics_geometry_metric')
        row = box.row(align=True)
        row.operator('sionna_bridge.refresh_analytics', text='Refresh', icon='FILE_REFRESH')
        row.operator('sionna_bridge.open_analytics_dashboard', text='Open Plots', icon='GRAPH')
        try:
            analytics = bridge.json.loads(settings.analytics_json) if settings.analytics_json else {}
        except Exception:
            analytics = {}
        if not analytics:
            box.label(text='Run a simulation or press Refresh.', icon='INFO')
        elif analytics.get('source') == 'PATHS':
            box.label(text=f"Source: {analytics.get('object', '—')}", icon='POINTCLOUD_DATA')
            row = box.row(align=True)
            row.label(text=f"Paths: {int(analytics.get('path_count', 0)):,}")
            row.label(text=f"Links: {int(analytics.get('link_count', 0)):,}")
            row.label(text=f"Frames: {int(analytics.get('frame_count', 0)):,}")
            gain = analytics.get('gain_db', {})
            distance = analytics.get('distance_m', {})
            channel_power = analytics.get('channel_total_power_db', {})
            rms_delay = analytics.get('rms_delay_spread_ns', {})
            first_arrival = analytics.get('first_arrival_ns', {})
            dominant = analytics.get('dominant_to_rest_db', {})
            row = box.row(align=True)
            row.label(text=f"Channel power: {float(channel_power.get('mean', 0.0)):.2f} dB")
            row.label(text=f"RMS delay: {float(rms_delay.get('mean', 0.0)):.3g} ns")
            row = box.row(align=True)
            row.label(text=f"First arrival: {float(first_arrival.get('mean', 0.0)):.3g} ns")
            row.label(text=f"LoS links: {float(analytics.get('los_link_percent', 0.0)):.1f}%")
            row = box.row(align=True)
            row.label(text=f"Dominant/rest: {float(dominant.get('mean', 0.0)):.2f} dB")
            row.label(text=f"Best path: {float(gain.get('max', 0.0)):.2f} dB")
            row = box.row(align=True)
            row.label(text=f"TX/RX mean: {float(distance.get('mean', 0.0)):.3g} m")
            row.label(text=f"Links analyzed: {int(analytics.get('channel_link_count', 0)):,}")
            if analytics.get('mobility_available'):
                doppler_abs = analytics.get('doppler_abs_hz', {})
                doppler_spread = analytics.get('rms_doppler_spread_hz', {})
                tx_speed = analytics.get('tx_speed_m_s', {})
                rx_speed = analytics.get('rx_speed_m_s', {})
                row = box.row(align=True)
                row.label(text=f"Max |Doppler|: {float(doppler_abs.get('max', 0.0)):.3g} Hz")
                row.label(text=f"RMS Doppler: {float(doppler_spread.get('mean', 0.0)):.3g} Hz")
                row = box.row(align=True)
                row.label(text=f"TX speed: {float(tx_speed.get('mean', 0.0)):.3g} m/s")
                row.label(text=f"RX speed: {float(rx_speed.get('mean', 0.0)):.3g} m/s")
            selected_channel = analytics.get('selected_channel') or {}
            if selected_channel:
                sub = box.column(align=True)
                sub.label(text=f"CIR/PDP selection: F{int(selected_channel.get('frame', 0))} · Pair {int(selected_channel.get('pos_idx', 0))}")
                row = sub.row(align=True)
                row.label(text=f"Paths: {int(selected_channel.get('path_count', 0)):,}")
                row.label(text=f"RMS: {float(selected_channel.get('rms_delay_spread_ns', 0.0) or 0.0):.3g} ns")
                row = sub.row(align=True)
                row.label(text=f"Power: {bridge._optional_number(selected_channel.get('total_power_db'), '.2f')} dB")
                row.label(text=f"LoS: {('Yes' if selected_channel.get('los_available') else 'No')}")
                if analytics.get('mobility_available'):
                    row = sub.row(align=True)
                    row.label(text=f"Mean Doppler: {float(selected_channel.get('doppler_mean_hz', 0.0)):.3g} Hz")
                    row.label(text=f"RMS spread: {float(selected_channel.get('rms_doppler_spread_hz', 0.0)):.3g} Hz")
            types = analytics.get('path_types', {})
            if types:
                sub = box.column(align=True)
                sub.label(text='Path types')
                total = max(1, int(analytics.get('path_count', 0)))
                for name, value in sorted(types.items(), key=lambda item: (-item[1], item[0])):
                    row = sub.row(align=True)
                    row.label(text=name)
                    row.label(text=f'{int(value):,}  ({100.0 * int(value) / total:.1f}%)')
            top_paths = analytics.get('top_paths', [])[:int(settings.analytics_top_rows)]
            if top_paths:
                box.prop(settings, 'analytics_top_rows')
                sub = box.column(align=True)
                sub.label(text='Strongest paths')
                for item in top_paths:
                    sub.label(text=f"F{int(item.get('frame', 0))} Pair {int(item.get('pos_idx', 0))} · {item.get('path_type', 'Other')} · {float(item.get('path_gain_db', 0.0)):.2f} dB · {float(item.get('delay_ns', 0.0)):.3g} ns · {float(item.get('doppler_hz', 0.0)):+.3g} Hz")
        else:
            label = '2D radio map' if analytics.get('source') == 'RADIO_MAP' else '3D radio map'
            box.label(text=f"Source: {analytics.get('object', '—')}", icon='POINTCLOUD_DATA')
            row = box.row(align=True)
            row.label(text=f"{label}: {int(analytics.get('point_count', 0)):,} points")
            row.label(text=f"Frames: {int(analytics.get('frame_count', 0)):,}")
            gain = analytics.get('gain_db', {})
            percentiles = analytics.get('percentiles', {})
            metric_label = analytics.get('metric_label', 'Metric')
            metric_unit = analytics.get('metric_unit', 'dB')
            row = box.row(align=True)
            row.label(text=f"P5: {float(percentiles.get('5', 0.0)):.2f} {metric_unit}")
            row.label(text=f"Median: {float(percentiles.get('50', 0.0)):.2f} {metric_unit}")
            row.label(text=f"P95: {float(percentiles.get('95', 0.0)):.2f} {metric_unit}")
            row = box.row(align=True)
            threshold = float(analytics.get('coverage_threshold', 0.0))
            row.label(text=f"Coverage ≥ {threshold:g}: {float(analytics.get('coverage_above_threshold_percent', 0.0)):.1f}%")
            row.label(text=f"Outage: {float(analytics.get('outage_below_threshold_percent', 0.0)):.1f}%")
            row = box.row(align=True)
            row.label(text=f"Strongest: {float(gain.get('max', 0.0)):.2f} {metric_unit}")
            row.label(text=f"Valid values: {float(analytics.get('valid_percent', 0.0)):.1f}%")
            association = analytics.get('tx_association') or {}
            if association.get('available'):
                dominant = association.get('dominant') or {}
                row = box.row(align=True)
                row.label(text=f"Associated TXs: {int(association.get('tx_count', 0))}")
                row.label(text=f"Dominant: {dominant.get('name', '—')} ({float(dominant.get('share_percent', 0.0)):.1f}%)")
                row = box.row(align=True)
                row.label(text=f"Unassociated: {float(association.get('unassociated_percent', 0.0)):.1f}%")
                row.label(text=f"Attribute: associated_tx ({analytics.get('metric_label', 'metric')})")
            if analytics.get('source') == 'RADIO_MAP_3D':
                row.label(text=f"Layers: {int(analytics.get('layer_count', 0)):,}")
        animation = analytics.get('procedural_animation') or {}
        if animation:
            sub = box.column(align=True)
            sub.label(text='Procedural animation', icon='ANIM')
            row = sub.row(align=True)
            row.label(text=f"Frames: {int(animation.get('frame_count', 0)):,}")
            row.label(text=f"States: {int(animation.get('distinct_geometry_states', 0)):,}")
            row.label(text=f"Descriptor: {animation.get('geometry_label', 'Geometry')}")
            geometry = animation.get('geometry_stats', {})
            unit = animation.get('geometry_unit', '')
            row = sub.row(align=True)
            row.label(text=f"Range: {float(geometry.get('min', 0.0)):.4g}–{float(geometry.get('max', 0.0)):.4g}{(' ' + unit if unit else '')}")
            row.label(text=f"Largest change: F{int(animation.get('max_change_frame', 0))} ({float(animation.get('max_change_percent', 0.0)):+.2f}%)")
            row = sub.row(align=True)
            if analytics.get('source') == 'PATHS':
                row.label(text=f"Power r: {bridge._correlation_text(animation.get('correlation_channel_power'))}")
                row.label(text=f"RMS delay r: {bridge._correlation_text(animation.get('correlation_rms_delay'))}")
                row.label(text=f"Paths r: {bridge._correlation_text(animation.get('correlation_path_count'))}")
            else:
                row.label(text=f"Metric r: {bridge._correlation_text(animation.get('correlation_metric'))}")
                row.label(text=f"Coverage r: {bridge._correlation_text(animation.get('correlation_coverage'))}")
            sub.label(text='Open Plots for frame trends, correlations, and the frame table.', icon='INFO')
        elif settings.analytics_scope == 'ALL' and bridge._procedural_scene_active(context.scene):
            box.label(text='Run a new procedural simulation with geometry statistics enabled.', icon='INFO')

    class SIONNA_PT_MainPanel(bpy.types.Panel):
        bl_label = 'SionnaRT-Bridge'
        bl_idname = 'SIONNA_PT_main'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'Sionna RT'

        def draw(self, context):
            settings = context.scene.sionna_bridge
            layout = self.layout
            tx = len(bridge._device_objects(context.scene, 'TX'))
            rx = len(bridge._device_objects(context.scene, 'RX'))
            info = bridge.json.loads(settings.runtime_probe_json or '{}')
            signature = bridge._runtime_probe_signature(settings)
            current = info.get('bridge_signature') == signature
            if info and current:
                layout.label(text=f"RT {info.get('sionna_rt', '?')} · {('CUDA GPU' if 'cuda' in info.get('variant', '') else 'LLVM CPU' if 'llvm' in info.get('variant', '') else info.get('variant', '?'))}", icon='CHECKMARK')
            else:
                layout.operator('sionna_bridge.test_environment', text='Check Runtime', icon='CONSOLE')
            layout.label(text=f"{tx} TX · {rx} RX · {settings.simulation_mode.replace('_', ' ')}")
            cache = bool(settings.last_scene_xml) if hasattr(settings, 'last_scene_xml') else False
            layout.label(text='Scene cache recorded' if cache else 'Scene exported on Run', icon='SCENE_DATA')
            if not bridge._processes_idle():
                layout.label(text='Simulation running', icon='TIME')
                layout.operator('sionna_bridge.cancel_run', text='Stop Simulation', icon='CANCEL')
            elif tx == 0 or (settings.simulate_paths and rx == 0):
                layout.label(text='Add required TX / RX devices', icon='ERROR')
            else:
                layout.label(text='Devices ready' + (' · runtime checked' if current else ' · runtime unchecked'), icon='INFO')

    class SIONNA_PT_Simulation(bpy.types.Panel):
        bl_label = 'Simulation'
        bl_idname = 'SIONNA_PT_simulation'
        bl_parent_id = 'SIONNA_PT_main'
        bl_space_type = 'VIEW_3D'
        bl_region_type = 'UI'
        bl_category = 'Sionna RT'

        def draw(self, context):
            settings = context.scene.sionna_bridge
            layout = self.layout
            layout.prop(settings, 'simulation_mode', text='Type')
            if settings.simulation_mode == 'BATCH':
                row = layout.row(align=True)
                for prop in ('simulate_paths', 'simulate_radio_map', 'simulate_radio_map_3d'):
                    row.prop(settings, prop)
            layout.prop(settings, 'frequency_ghz')
            layout.prop(settings, 'max_depth')
            layout.prop(settings, 'samples_per_src')
            row = layout.row()
            row.scale_y = 1.4
            row.enabled = bridge._processes_idle()
            row.operator('sionna_bridge.run_selected', text='Run Simulation', icon='PLAY')

    def panel(name, label, parent, draw=None, poll=None, collapsed=True):
        attrs = dict(bl_idname=name, bl_label=label, bl_parent_id=parent, bl_space_type='VIEW_3D', bl_region_type='UI', bl_category='Sionna RT', __module__=__name__, draw=draw or (lambda self, context: None))
        if collapsed:
            attrs['bl_options'] = {'DEFAULT_CLOSED'}
        if poll:
            attrs['poll'] = classmethod(lambda cls, context: poll(context.scene.sionna_bridge))
        return type(name, (bpy.types.Panel,), attrs)
    classes = [SIONNA_PT_MainPanel]
    classes += [panel('SIONNA_PT_setup', 'Setup', 'SIONNA_PT_main', draw_runtime)]
    classes += [panel('SIONNA_PT_scene', 'Scene & Devices', 'SIONNA_PT_main', draw_scene)]
    for name, label, draw in (('devices', 'Devices & Motion', draw_devices), ('materials', 'Radio Materials', draw_materials), ('procedural', 'Procedural Geometry', draw_procedural)):
        classes.append(panel('SIONNA_PT_' + name, label, 'SIONNA_PT_scene', draw))
    classes.append(SIONNA_PT_Simulation)
    classes += [panel('SIONNA_PT_solver', 'Solver & Antennas — Advanced', 'SIONNA_PT_simulation', draw_solver)]
    classes += [panel('SIONNA_PT_execution', 'Execution, Cache & Export', 'SIONNA_PT_simulation', draw_execution)]
    for name, label, draw, poll in (('paths', 'Path Results & Live Updates', draw_paths, lambda s: s.simulate_paths), ('map2d', '2D Radio Map', draw_map2d, lambda s: s.simulate_radio_map), ('map3d', '3D Radio Map', draw_map3d, lambda s: s.simulate_radio_map_3d)):
        classes.append(panel('SIONNA_PT_' + name, label, 'SIONNA_PT_simulation', draw, poll, collapsed=False))
    classes += [panel('SIONNA_PT_results', 'Results', 'SIONNA_PT_main', draw_status)]
    classes += [panel('SIONNA_PT_parameters', 'Parameter Analysis — Paths', 'SIONNA_PT_results', draw_parameters)]
    classes += [panel('SIONNA_PT_analytics', 'Analytics', 'SIONNA_PT_results', draw_analytics)]
    classes += [panel('SIONNA_PT_motion', 'Device Motion Paths', 'SIONNA_PT_scene', draw_motion)]
    return tuple(classes)
