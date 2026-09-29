"""Units and labels shared by Blender capture and offline reports."""
FIELDS = {
    'leaf_surface_area_m2': ('Leaf mesh surface area', 'mÂ²'),
    'leaf_area_estimate_m2': ('One-sided leaf area estimate', 'mÂ²'),
    'wood_surface_area_m2': ('Wood mesh surface area', 'mÂ²'),
    'leaf_component_count': ('Leaf count estimate (mesh islands)', ''),
    'tagged_leaf_count': ('Leaf count from supplied IDs', ''),
    'vegetation_bounds_volume_m3': ('Vegetation bounding-box volume', 'mÂ³'),
    'vegetation_bounds_footprint_m2': ('Vegetation bounding-box footprint', 'mÂ²'),
    'leaf_area_density_bbox_m_inv': ('Leaf area density (bounding-box estimate)', 'mÂ²/mÂ³'),
    'leaf_area_index_bbox': ('Leaf area index (bounding-box estimate)', 'mÂ²/mÂ²'),
    'distance_m': ('TXâ€“RX distance', 'm'),
    'vegetation_bounds_length_m': ('Vegetation depth (bounding-box estimate)', 'm'),
    'leaf_surface_crossings': ('Leaf surface crossings on direct segment', ''),
    'wood_surface_crossings': ('Wood surface crossings on direct segment', ''),
    'corridor_leaf_area_m2': ('Leaf area inside link corridor (estimate)', 'mÂ²'),
    'corridor_volume_m3': ('Link corridor volume', 'mÂ³'),
    'corridor_leaf_area_density_m_inv': ('Leaf area density in link corridor (estimate)', 'mÂ²/mÂ³'),
}
