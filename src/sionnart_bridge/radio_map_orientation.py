"""Planar radio-map coordinates shared by Blender and the external worker.

Sionna orientation is (alpha, beta, gamma) in radians: Rz(alpha) Ry(beta)
Rx(gamma). Blender's XYZ Euler representation stores (gamma, beta, alpha).
Size/cell_size always describe the two local axes of the measurement plane.
"""
import math


def orientation_from_settings(settings):
    plane = str(getattr(settings, "radio_map_plane", "XY")).upper()
    presets = {"XY": (0.0, 0.0, 0.0), "XZ": (0.0, 0.0, math.pi / 2),
               "YZ": (math.pi / 2, 0.0, math.pi / 2)}
    if plane in presets:
        return list(presets[plane])
    if plane != "CUSTOM":
        raise ValueError(f"Unknown radio-map plane: {plane}")
    return [float(getattr(settings, "radio_map_rotation_" + axis, 0.0))
            for axis in ("z", "y", "x")]


def orientation_from_payload(radio):
    angles = radio.get("orientation", (0.0, 0.0, 0.0))
    if len(angles) != 3 or not all(math.isfinite(float(x)) for x in angles):
        raise ValueError("Radio-map orientation requires three finite angles in radians")
    return [float(x) for x in angles]


def plane_basis(orientation):
    """Return unit vectors (u, v, normal) in world coordinates."""
    a, b, g = orientation_from_payload({"orientation": orientation})
    ca, sa, cb, sb, cg, sg = (math.cos(a), math.sin(a), math.cos(b),
                             math.sin(b), math.cos(g), math.sin(g))
    return (
        (ca * cb, sa * cb, -sb),
        (ca * sb * sg - sa * cg, sa * sb * sg + ca * cg, cb * sg),
        (ca * sb * cg + sa * sg, sa * sb * cg - ca * sg, cb * cg),
    )


def center_on_plane(center, target, orientation):
    """Follow a TX in the plane, preserving its normal offset from the plane."""
    normal = plane_basis(orientation)[2]
    offset = sum((float(target[i]) - float(center[i])) * normal[i] for i in range(3))
    return [float(target[i]) - offset * normal[i] for i in range(3)]
