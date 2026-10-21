# SPDX-License-Identifier: GPL-3.0-or-later
"""Architectural Building Nodes: Parametric Walls, Slabs, and Openings."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


def _offset_points(pts: List[Vec3], dist: float) -> List[Vec3]:
    """Offsets a 2D/3D polygon horizontally by `dist`."""
    n = len(pts)
    if n < 3 or abs(dist) < 1e-4:
        return [Vec3(p.x, p.y, p.z) for p in pts]
    lines = []
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx = dy / length * dist
        ny = -dx / length * dist
        lines.append(((p1.x + nx, p1.y + ny), (p2.x + nx, p2.y + ny)))

    m = len(lines)
    if m < 3:
        return [Vec3(p.x, p.y, p.z) for p in pts]

    out: List[Vec3] = []
    for i in range(m):
        (x1, y1), (x2, y2) = lines[i]
        (x3, y3), (x4, y4) = lines[(i + 1) % m]
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        z = pts[i].z
        if abs(denom) < 1e-6:
            out.append(Vec3(x2, y2, z))
        else:
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
            out.append(Vec3(x1 + t * (x2 - x1), y1 + t * (y2 - y1), z))
    return out


# ============================================================================
# 1. Parametric Wall from Curve Node
# ============================================================================
@register_node
class WallFromCurveNode(BaseNode):
    type_id = "arch.wall"
    title = "Wall from Curve"
    category = "Architecture"
    description = "Extrudes a 2D polyline or curve into 3D watertight solid walls with thickness and height."
    header_color = (191, 97, 106)

    inputs = [
        InputSpec("curve", "Curve / Baseline", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("thickness", "Thickness (m)", SocketType.FLOAT, default=0.25, min_val=0.05, step=0.05),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=3.0, min_val=0.5, step=0.5),
        InputSpec("elevation", "Elevation (m)", SocketType.FLOAT, default=0.0, step=0.5),
    ]
    outputs = [
        OutputSpec("wall_mesh", "Wall Solid", SocketType.MESH),
        OutputSpec("outer_curve", "Outer Perimeter", SocketType.CURVE),
        OutputSpec("inner_curve", "Inner Perimeter", SocketType.CURVE),
    ]

    def compute(self, curve: Any, thickness: float, height: float, elevation: float) -> Dict[str, Any]:
        pts: List[Vec3] = []
        is_closed = True
        if isinstance(curve, CurveData) and curve.points:
            pts = curve.points
            is_closed = curve.closed
        elif isinstance(curve, list) and curve and isinstance(curve[0], Vec3):
            pts = curve
        else:
            # Default fallback: 12x8m room
            pts = [Vec3(0, 0, 0), Vec3(12, 0, 0), Vec3(12, 8, 0), Vec3(0, 8, 0)]

        th = max(0.05, float(thickness))
        h = max(0.2, float(height))
        z0 = float(elevation)
        z1 = z0 + h

        # Ensure base elevation is applied
        base_pts = [Vec3(p.x, p.y, z0) for p in pts]
        n = len(base_pts)

        # Generate outer and inner loops
        half_th = th * 0.5
        outer_pts = _offset_points(base_pts, half_th)
        inner_pts = _offset_points(base_pts, -half_th)

        verts: List[Tuple[float, float, float]] = []
        faces: List[List[int]] = []
        edges: List[Tuple[int, int]] = []

        # 0..N-1: Outer bottom (z0)
        # N..2N-1: Outer top (z1)
        # 2N..3N-1: Inner bottom (z0)
        # 3N..4N-1: Inner top (z1)
        for p in outer_pts:
            verts.append((p.x, p.y, z0))
        for p in outer_pts:
            verts.append((p.x, p.y, z1))
        for p in inner_pts:
            verts.append((p.x, p.y, z0))
        for p in inner_pts:
            verts.append((p.x, p.y, z1))

        # 1. Outer vertical faces (CCW)
        for i in range(n):
            nxt = (i + 1) % n
            faces.append([i, nxt, n + nxt, n + i])
            edges.append((i, nxt))
            edges.append((n + i, n + nxt))
            edges.append((i, n + i))

        # 2. Inner vertical faces (reversed CCW inward)
        for i in range(n):
            nxt = (i + 1) % n
            faces.append([3 * n + i, 3 * n + nxt, 2 * n + nxt, 2 * n + i])
            edges.append((2 * n + i, 2 * n + nxt))
            edges.append((3 * n + i, 3 * n + nxt))
            edges.append((2 * n + i, 3 * n + i))

        # 3. Top cap quad between outer top and inner top
        for i in range(n):
            nxt = (i + 1) % n
            faces.append([n + i, n + nxt, 3 * n + nxt, 3 * n + i])

        # 4. Bottom cap quad between inner bottom and outer bottom
        for i in range(n):
            nxt = (i + 1) % n
            faces.append([2 * n + i, 2 * n + nxt, nxt, i])

        wall_mesh = MeshData(
            vertices=verts,
            faces=faces,
            edges=edges,
            name="Parametric_Wall",
            ifc_class="IfcWall",
        )

        return {
            "wall_mesh": wall_mesh,
            "outer_curve": CurveData(points=outer_pts, closed=is_closed),
            "inner_curve": CurveData(points=inner_pts, closed=is_closed),
        }


# ============================================================================
# 2. Parametric Floor Slab / Foundation Node
# ============================================================================
@register_node
class SlabNode(BaseNode):
    type_id = "arch.slab"
    title = "Floor / Slab"
    category = "Architecture"
    description = "Generates a 3D watertight solid floor slab or foundation from a boundary curve."
    header_color = (191, 97, 106)

    inputs = [
        InputSpec("boundary", "Boundary", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("thickness", "Thickness (m)", SocketType.FLOAT, default=0.30, min_val=0.05, step=0.05),
        InputSpec("elevation", "Elevation (m)", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("overhang", "Edge Offset (m)", SocketType.FLOAT, default=0.1, step=0.05),
    ]
    outputs = [
        OutputSpec("slab_mesh", "Slab Solid", SocketType.MESH),
        OutputSpec("top_face", "Top Face", SocketType.MESH),
    ]

    def compute(self, boundary: Any, thickness: float, elevation: float, overhang: float) -> Dict[str, Any]:
        pts: List[Vec3] = []
        if isinstance(boundary, CurveData) and boundary.points:
            pts = boundary.points
        elif isinstance(boundary, MeshData) and boundary.vertices:
            pts = [Vec3(v[0], v[1], v[2]) for v in boundary.vertices]
        elif isinstance(boundary, list) and boundary and isinstance(boundary[0], Vec3):
            pts = boundary
        else:
            pts = [Vec3(0, 0, 0), Vec3(12, 0, 0), Vec3(12, 8, 0), Vec3(0, 8, 0)]

        th = max(0.05, float(thickness))
        z_top = float(elevation)
        z_bot = z_top - th

        if abs(overhang) > 1e-4:
            pts = _offset_points(pts, float(overhang))

        n = len(pts)
        verts: List[Tuple[float, float, float]] = []
        # Top loop
        for p in pts:
            verts.append((p.x, p.y, z_top))
        # Bottom loop
        for p in pts:
            verts.append((p.x, p.y, z_bot))

        faces: List[List[int]] = []
        # Top cap (+Z, CCW)
        faces.append(list(range(n)))
        # Bottom cap (-Z, reversed CW)
        faces.append(list(reversed(range(n, 2 * n))))
        # Side quads
        edges: List[Tuple[int, int]] = []
        for i in range(n):
            nxt = (i + 1) % n
            faces.append([i, nxt, n + nxt, n + i])
            edges.append((i, nxt))
            edges.append((n + i, n + nxt))
            edges.append((i, n + i))

        slab_mesh = MeshData(
            vertices=verts,
            faces=faces,
            edges=edges,
            name="Parametric_Slab",
            ifc_class="IfcSlab",
        )
        return {"slab_mesh": slab_mesh, "top_face": CurveData(points=pts, closed=True).to_mesh_face("SlabTop")}
