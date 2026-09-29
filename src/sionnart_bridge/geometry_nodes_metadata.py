"""Frame-specific Geometry Nodes input records, independent of simulation output.

Capture runs on Blender's main thread after frame/dependency-graph evaluation.
JSON writing needs no Blender API and is also exercised by the export tests.
The schema records parameters and node defaults, not evaluated geometry fields
or a replacement for the source .blend project.
"""
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "sionna_geometry_nodes_parameters"
SCHEMA_VERSION = 1


def id_reference(value):
    original = getattr(value, "original", value)
    library = getattr(original, "library", None)
    return {
        "name": str(getattr(original, "name_full", getattr(original, "name", ""))),
        "id_type": str(getattr(getattr(original, "bl_rna", None), "identifier", type(original).__name__)),
        "library": str(getattr(library, "filepath", "")) if library else None,
    }


def json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "name_full") and hasattr(value, "library"):
        return {"datablock": id_reference(value)}
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    # mathutils.Vector/Euler implement the sequence protocol (__getitem__)
    # without exposing __iter__ in some Blender builds.
    try:
        iterator = iter(value)
    except TypeError:
        raise TypeError(f"Unsupported metadata value type: {type(value).__name__}") from None
    return [json_value(v) for v in iterator]


def _read_value(value, warnings, label):
    try:
        encoded = json_value(value)
        if isinstance(value, float) and not math.isfinite(value):
            warnings.append(f"{label}: non-finite value recorded as null")
        return encoded
    except (TypeError, ValueError, ReferenceError) as exc:
        warnings.append(f"{label}: {exc}")
        return {"unavailable": type(value).__name__}


def _group_key(group):
    ref = id_reference(group)
    return hashlib.sha256(json.dumps(ref, sort_keys=True).encode("utf-8")).hexdigest()[:20]


def _interface_inputs(group):
    interface = getattr(group, "interface", None)
    if interface is not None:
        return [s for s in interface.items_tree
                if s.item_type == "SOCKET" and s.in_out == "INPUT"]
    return list(getattr(group, "inputs", ()))


def _input_record(modifier, socket, warnings):
    identifier = socket.identifier
    kind = str(getattr(socket, "socket_type", getattr(socket, "bl_socket_idname", "")))
    record = {"identifier": identifier, "name": socket.name, "socket_type": kind}
    if kind == "NodeSocketGeometry":
        return {**record, "source": "geometry", "value": None}
    properties = getattr(modifier, "properties", None)
    inputs = getattr(properties, "inputs", None)
    prop = None
    if inputs is not None:
        try:
            prop = getattr(inputs, identifier)
        except (AttributeError, TypeError):
            try:
                prop = inputs[identifier]
            except (KeyError, TypeError, AttributeError):
                pass
    if prop is not None:
        mode = str(getattr(prop, "type", "VALUE"))
        record.update(source="modifier", api="rna", input_mode=mode)
        if mode != "VALUE":
            # ATTRIBUTE/LAYER inputs are fields, not a scalar socket value.
            record["attribute_name"] = str(getattr(prop, "attribute_name", ""))
            if hasattr(prop, "layer_name"):
                record["layer_name"] = str(prop.layer_name)
            record["value"] = None
        elif hasattr(prop, "value"):
            record["value"] = _read_value(prop.value, warnings, f"{modifier.name}/{socket.name}")
        else:
            record.update(source="unavailable", value=None)
            warnings.append(f"{modifier.name}/{socket.name}: input has no readable value")
        return record
    # Older files/builds may retain ID-property-based inputs.
    if identifier in modifier:
        use_attribute = bool(modifier.get(identifier + "_use_attribute", False))
        record.update(source="modifier", api="id_property", input_mode="ATTRIBUTE" if use_attribute else "VALUE")
        if use_attribute:
            record.update(attribute_name=str(modifier.get(identifier + "_attribute_name", "")), value=None)
        else:
            record["value"] = _read_value(modifier[identifier], warnings, f"{modifier.name}/{socket.name}")
        return record
    if hasattr(socket, "default_value"):
        record.update(source="interface_default", value=_read_value(socket.default_value, warnings, socket.name))
    else:
        record.update(source="unavailable", value=None)
        warnings.append(f"{modifier.name}/{socket.name}: no readable modifier input or default")
    return record


def _record_group(group, depsgraph, groups, warnings):
    key = _group_key(group)
    if key in groups:
        return key
    entry = {"id": id_reference(group), "nodes": [], "links": []}
    groups[key] = entry
    try:
        evaluated = group.evaluated_get(depsgraph)
    except (AttributeError, RuntimeError, ReferenceError):
        evaluated = group
    for node in sorted(evaluated.nodes, key=lambda n: n.name):
        record = {"name": node.name, "type": node.bl_idname, "mute": bool(node.mute), "inputs": []}
        for socket in node.inputs:
            item = {"identifier": socket.identifier, "name": socket.name,
                    "socket_type": socket.bl_idname, "linked": bool(socket.is_linked)}
            if not socket.is_linked and hasattr(socket, "default_value"):
                item["default_value"] = _read_value(socket.default_value, warnings, f"{group.name}/{node.name}/{socket.name}")
            record["inputs"].append(item)
        # Value/RGB nodes expose their literal parameter on an output socket.
        if node.bl_idname in {"ShaderNodeValue", "ShaderNodeRGB"}:
            record["literal_outputs"] = [
                {"identifier": x.identifier, "name": x.name,
                 "value": _read_value(x.default_value, warnings, f"{group.name}/{node.name}")}
                for x in node.outputs if hasattr(x, "default_value")]
        nested = getattr(node, "node_tree", None)
        if nested is not None:
            record["node_group"] = _record_group(nested, depsgraph, groups, warnings)
        entry["nodes"].append(record)
    for link in evaluated.links:
        entry["links"].append({"from_node": link.from_node.name,
                               "from_socket": link.from_socket.identifier,
                               "to_node": link.to_node.name,
                               "to_socket": link.to_socket.identifier})
    return key


def capture(context, collection, depsgraph):
    """Capture each collection-member object's evaluated modifiers once.

    Includes all nested subcollections, disabled modifiers, and every exposed
    socket. Visibility/enable flags describe participation; membership alone is
    not a claim that an object was included in a cached solver scene.
    """
    if collection is None:
        raise RuntimeError("Create the Sionna scene collection before exporting Geometry Nodes metadata")
    result = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
              "scene_name": context.scene.name, "frame": int(context.scene.frame_current),
              "subframe": float(context.scene.frame_subframe),
              "collection": id_reference(collection), "objects": [], "node_groups": {}, "warnings": []}
    warnings = result["warnings"]
    for obj in sorted(collection.all_objects, key=lambda o: (o.name_full, str(getattr(o.library, "filepath", "")))):
        evaluated = obj.evaluated_get(depsgraph)
        record = {"object": id_reference(obj), "object_type": obj.type,
                  "collections": sorted(c.name_full for c in obj.users_collection),
                  "hide_viewport": bool(obj.hide_viewport), "hide_render": bool(obj.hide_render),
                  "excluded_by_bridge": bool(obj.get("sionna_blender_only", False)),
                  "modifiers": []}
        for index, modifier in enumerate(evaluated.modifiers):
            if modifier.type != "NODES" or modifier.node_group is None:
                continue
            group = modifier.node_group
            group_key = _record_group(group, depsgraph, result["node_groups"], warnings)
            record["modifiers"].append({"name": modifier.name, "stack_index": index,
                                        "show_viewport": bool(modifier.show_viewport),
                                        "show_render": bool(modifier.show_render),
                                        "node_group": group_key,
                                        "inputs": [_input_record(modifier, s, warnings) for s in _interface_inputs(group)]})
        if record["modifiers"]:
            result["objects"].append(record)
    return result


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_run(config, directory):
    """Write one JSON per sampled simulation frame plus a joinable manifest.

    Called after scene XMLs and output paths have been assigned. Input snapshots
    remain in config too, so normal CSV metadata/HDF5 frame records retain them.
    The manifest describes prepared inputs; it never claims solver completion.
    """
    frames = [p for p in config.get("frames", ()) if "geometry_nodes_parameters" in p]
    if not frames:
        return None
    directory = Path(directory)
    output = config["output"]
    category = output["export_category"]
    run_id = output["export_run_id"]
    manifest_path = directory / "manifest.json"
    descriptor = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
                  "run_id": run_id, "simulation_category": category,
                  "manifest_json": str(manifest_path), "frame_count": len(frames)}
    manifest = {**descriptor, "record_kind": "prepared_simulation_inputs",
                "bridge_version": config.get("bridge_version"),
                "created_utc": config.get("created_utc"), "blend_file": config.get("blend_file"),
                "scene_name": config.get("scene_name"),
                "result_export": {k: output.get(k, "") for k in ("export_file", "export_metadata_json", "export_format")},
                "frames": []}
    for frame in frames:
        number = int(frame["frame"])
        name = f"frame_{number:06d}.json"
        record = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION,
                  "record_kind": "prepared_simulation_inputs", "bridge_version": config.get("bridge_version"),
                  "run_id": run_id, "simulation_category": category,
                  "frame": number, "time_seconds": frame.get("time_seconds"),
                  "scene_name": config.get("scene_name"), "blend_file": config.get("blend_file"),
                  "created_utc": config.get("created_utc"),
                  "scene_source": {"path": frame.get("scene_xml", config.get("scene_xml")),
                                   "sha256": frame.get("scene_xml_sha256", config.get("scene_xml_sha256")),
                                   "evaluated_per_frame": bool(config.get("procedural_scene", False))},
                  "simulation": frame.get("simulation", {}), "antenna": config.get("antenna", {}),
                  "materials": frame.get("materials", []),
                  "transmitters": frame.get("transmitters", []), "receivers": frame.get("receivers", []),
                  "result_files": frame.get("output", {}),
                  "geometry_nodes": frame["geometry_nodes_parameters"]}
        for key in ("radio_map", "radio_map_3d", "procedural_geometry_stats", "vegetation_metrics"):
            if key in frame:
                record[key] = frame[key]
        write_json(directory / name, record)
        frame["geometry_nodes_metadata_file"] = str(directory / name)
        manifest["frames"].append({"frame": number, "file": name,
                                    "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()})
    write_json(manifest_path, manifest)
    config["geometry_nodes_metadata"] = descriptor
    config["output"]["geometry_nodes_metadata_json"] = str(manifest_path)
    return descriptor
