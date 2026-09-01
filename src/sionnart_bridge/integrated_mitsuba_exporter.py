"""Blender-native Mitsuba scene exporter for SionnaRT-Bridge.

This module intentionally has no dependency on Mitsuba-Blender or the Mitsuba
Python package inside Blender. It exports the evaluated Blender dependency graph
to the subset of Mitsuba XML/PLY needed by Sionna RT:

* evaluated mesh geometry (including modifiers / realized Geometry Nodes mesh),
* dependency-graph object instances,
* one PLY shape per Blender material assignment,
* material IDs that the bridge later replaces with Sionna radio materials.

Sionna RT, Mitsuba, and Dr.Jit are supplied by the configured bridge runtime.
On Blender 5.2 the default runtime uses Blender's bundled Python plus the
Sionna site-packages already available to Blender.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


_EXPORTABLE_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META"}


def _safe_token(value: str, fallback: str = "mesh") -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not value:
        value = fallback
    # Keep filenames comfortably below Windows path limits when nested in a
    # workspace while retaining a stable collision-resistant suffix.
    digest = hashlib.sha1(str(value).encode("utf-8", errors="replace")).hexdigest()[:8]
    return f"{value[:72]}_{digest}"


def _original_object(obj):
    original = getattr(obj, "original", None)
    return original if original is not None else obj


def _object_pointer(obj):
    obj = _original_object(obj)
    try:
        return int(obj.as_pointer())
    except Exception:
        return id(obj)


def _instance_is_selected(instance, selected_pointers: set[int]) -> bool:
    """Match Mitsuba-Blender's selection semantics without using Blender UI state.

    Normal evaluated objects are included when their original object belongs to
    ``sionna_env/scene``. Generated dependency-graph instances are included when
    either the instanced object itself or the parent that generated the instance
    belongs to that set. This covers collection instances and Geometry Nodes
    instances emitted by an exported source object.
    """
    obj = getattr(instance, "object", None)
    if obj is not None and _object_pointer(obj) in selected_pointers:
        return True

    parent = getattr(instance, "parent", None)
    visited = set()
    while parent is not None:
        pointer = _object_pointer(parent)
        if pointer in selected_pointers:
            return True
        if pointer in visited:
            break
        visited.add(pointer)
        parent = getattr(parent, "parent", None)
    return False


def _triangle_polygon_index(mesh, triangle) -> int:
    polygon_index = getattr(triangle, "polygon_index", None)
    if polygon_index is not None:
        return int(polygon_index)

    # Blender 5 exposes the triangle-to-polygon mapping as a separate collection.
    mapping = mesh.loop_triangle_polygons[int(triangle.index)]
    value = getattr(mapping, "value", mapping)
    return int(value)


def _material_for_index(mesh, material_index: int):
    if material_index < 0 or material_index >= len(mesh.materials):
        return None
    return mesh.materials[material_index]


def _write_binary_ply(path: Path, vertices, faces) -> None:
    """Write a compact binary little-endian triangular PLY accepted by Mitsuba."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        "comment SionnaRT-Bridge integrated Blender exporter\n"
        f"element vertex {len(vertices)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        f"element face {len(faces)}\n"
        "property list uchar int vertex_indices\n"
        "end_header\n"
    ).encode("ascii")

    with path.open("wb") as handle:
        handle.write(header)
        pack_vertex = struct.Struct("<fff").pack
        for x, y, z in vertices:
            handle.write(pack_vertex(float(x), float(y), float(z)))
        pack_face = struct.Struct("<Biii").pack
        for a, b, c in faces:
            handle.write(pack_face(3, int(a), int(b), int(c)))


def _mesh_parts(mesh, matrix_world):
    """Yield ``(material, world_vertices, triangles)`` for each used material."""
    mesh.calc_loop_triangles()
    if not mesh.loop_triangles:
        return

    triangles_by_material = defaultdict(list)
    for triangle in mesh.loop_triangles:
        polygon_index = _triangle_polygon_index(mesh, triangle)
        try:
            material_index = int(mesh.polygons[polygon_index].material_index)
        except Exception:
            material_index = -1
        material = _material_for_index(mesh, material_index)
        key = material_index if material is not None else -1
        triangles_by_material[key].append(tuple(int(v) for v in triangle.vertices))

    # World-space PLYs avoid transform/plugin compatibility differences between
    # Blender/Mitsuba versions. A negative determinant reverses handedness, so
    # reverse triangle winding to preserve outward face orientation.
    try:
        mirrored = float(matrix_world.to_3x3().determinant()) < 0.0
    except Exception:
        mirrored = False

    for material_index, source_faces in triangles_by_material.items():
        used = {}
        world_vertices = []
        faces = []
        for source_face in source_faces:
            target_face = []
            for source_index in source_face:
                target_index = used.get(source_index)
                if target_index is None:
                    co = matrix_world @ mesh.vertices[source_index].co
                    target_index = len(world_vertices)
                    used[source_index] = target_index
                    world_vertices.append((float(co.x), float(co.y), float(co.z)))
                target_face.append(target_index)
            if len(set(target_face)) != 3:
                continue
            if mirrored:
                target_face[1], target_face[2] = target_face[2], target_face[1]
            faces.append(tuple(target_face))

        if faces:
            yield _material_for_index(mesh, material_index), world_vertices, faces


def _placeholder_bsdf(material_id: str) -> ET.Element:
    bsdf = ET.Element("bsdf", {"type": "diffuse", "id": material_id})
    ET.SubElement(bsdf, "rgb", {"name": "reflectance", "value": "0.5 0.5 0.5"})
    return bsdf


def export_scene(context, xml_path, export_objects, *, progress_callback=None):
    """Export ``export_objects`` as a Mitsuba XML/PLY package.

    Returns a dictionary with ``shape_count``, ``material_ids`` and diagnostic
    counts. The XML intentionally contains simple optical placeholder BSDFs;
    SionnaRT-Bridge replaces them with radio-material declarations immediately
    after this function returns.
    """
    import bpy

    xml_path = Path(xml_path)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    mesh_dir = xml_path.parent / "meshes"
    mesh_dir.mkdir(parents=True, exist_ok=True)

    selected_pointers = {_object_pointer(obj) for obj in export_objects}
    depsgraph = context.evaluated_depsgraph_get()
    try:
        depsgraph.update()
    except Exception:
        pass

    root = ET.Element("scene", {"version": "3.0.0"})
    emitted_material_ids = set()
    shape_count = 0
    skipped_objects = 0
    emitted_instances = 0

    # DepsgraphObjectInstance values are temporary RNA iterator wrappers. Blender
    # 5 invalidates them as the iterator advances/completes, so never materialize
    # ``depsgraph.object_instances`` with ``list(...)`` or retain an instance
    # wrapper beyond the current iteration. Count in a separate pass, then copy
    # the few values we need before calling any API that could trigger evaluation.
    filename_counts = defaultdict(int)
    try:
        total = max(1, sum(1 for _ in depsgraph.object_instances))
    except Exception:
        total = max(1, len(getattr(depsgraph, "objects", ())))

    for index, instance in enumerate(depsgraph.object_instances):
        if progress_callback is not None:
            progress_callback(index, total)
        if not _instance_is_selected(instance, selected_pointers):
            continue

        # Snapshot all data that belongs to the temporary iterator item while it
        # is still alive. ``matrix_world.copy()`` is especially important: the
        # RNA-backed matrix must not outlive DepsgraphObjectInstance either.
        evaluated_obj = getattr(instance, "object", None)
        if evaluated_obj is None:
            continue
        try:
            matrix_world = instance.matrix_world.copy()
        except Exception:
            matrix_world = evaluated_obj.matrix_world.copy()
        is_instance = bool(getattr(instance, "is_instance", False))

        if bool(getattr(evaluated_obj, "hide_render", False)):
            continue
        if str(getattr(evaluated_obj, "type", "")) not in _EXPORTABLE_TYPES:
            skipped_objects += 1
            continue

        mesh = None
        try:
            # Blender 5 Object.to_mesh() returns the current evaluated state and
            # must be paired with to_mesh_clear().
            mesh = evaluated_obj.to_mesh(
                preserve_all_data_layers=False,
                depsgraph=depsgraph,
            )
            if mesh is None:
                skipped_objects += 1
                continue

            object_name = str(getattr(evaluated_obj, "name_full", evaluated_obj.name))
            if is_instance:
                emitted_instances += 1

            for part_index, (material, vertices, faces) in enumerate(
                _mesh_parts(mesh, matrix_world)
            ):
                material_name = material.name if material is not None else "default"
                material_id = f"mat-{material_name}" if material is not None else "default-bsdf"
                if material_id not in emitted_material_ids:
                    root.append(_placeholder_bsdf(material_id))
                    emitted_material_ids.add(material_id)

                base = _safe_token(f"{object_name}-{material_name}")
                collision_index = filename_counts[base]
                filename_counts[base] += 1
                if collision_index:
                    base = f"{base}-{collision_index:04d}"
                filename = f"{base}.ply"
                _write_binary_ply(mesh_dir / filename, vertices, faces)

                shape = ET.SubElement(
                    root,
                    "shape",
                    {
                        "type": "ply",
                        "id": f"mesh-{_safe_token(base, 'shape')}-{shape_count:06d}",
                    },
                )
                ET.SubElement(
                    shape,
                    "string",
                    {"name": "filename", "value": f"meshes/{filename}"},
                )
                ET.SubElement(
                    shape,
                    "boolean",
                    {"name": "face_normals", "value": "true"},
                )
                ET.SubElement(shape, "ref", {"id": material_id, "name": "bsdf"})
                shape_count += 1
        except ReferenceError as exc:
            raise RuntimeError(
                f"Evaluated dependency-graph instance became invalid while exporting "
                f"{getattr(evaluated_obj, 'name', '<unknown>')}: {exc}"
            ) from exc
        finally:
            if mesh is not None:
                try:
                    evaluated_obj.to_mesh_clear()
                except Exception:
                    pass

    if progress_callback is not None:
        progress_callback(total, total)

    if shape_count == 0:
        raise RuntimeError(
            "The selected Sionna scene produced no triangular mesh geometry. "
            "Check that objects are visible for render and that procedural instances "
            "are realized or generated from objects inside sionna_env/scene."
        )

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="    ")
    except AttributeError:
        pass
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    return {
        "shape_count": shape_count,
        "material_ids": sorted(emitted_material_ids),
        "skipped_objects": skipped_objects,
        "emitted_instances": emitted_instances,
        "blender_version": ".".join(str(v) for v in bpy.app.version),
    }


__all__ = ["export_scene"]
