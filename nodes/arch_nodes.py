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


def _offset_points(pts: List[Vec3], dist: float, is_closed: bool = True) -> List[Vec3]:
    """Offsets a 2D/3D polyline or polygon horizontally by `dist`."""
    n = len(pts)
    if n < 2 or abs(dist) < 1e-4:
        return [Vec3(p.x, p.y, p.z) for p in pts]

    if is_closed and n >= 3:
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
    else:
        # Open polyline offset
        lines = []
        for i in range(n - 1):
            p1 = pts[i]
            p2 = pts[i + 1]
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            length = math.hypot(dx, dy)
            if length < 1e-6:
                length = 1e-6
            nx = dy / length * dist
            ny = -dx / length * dist
            lines.append(((p1.x + nx, p1.y + ny), (p2.x + nx, p2.y + ny)))

        if not lines:
            return [Vec3(p.x, p.y, p.z) for p in pts]

        out = [Vec3(lines[0][0][0], lines[0][0][1], pts[0].z)]
        for i in range(len(lines) - 1):
            (x1, y1), (x2, y2) = lines[i]
            (x3, y3), (x4, y4) = lines[i + 1]
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            z = pts[i + 1].z
            if abs(denom) < 1e-6:
                out.append(Vec3(x2, y2, z))
            else:
                t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
                ix = x1 + t * (x2 - x1)
                iy = y1 + t * (y2 - y1)
                if math.hypot(ix - pts[i + 1].x, iy - pts[i + 1].y) > 3.0 * abs(dist):
                    out.append(Vec3(0.5 * (x2 + x3), 0.5 * (y2 + y3), z))
                else:
                    out.append(Vec3(ix, iy, z))
        out.append(Vec3(lines[-1][1][0], lines[-1][1][1], pts[-1].z))
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
        InputSpec("curve", "Curve / Baseline", SocketType.ANY, default=None, hide_widget=True),
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
        elif isinstance(curve, MeshData) and curve.vertices:
            # Accept MeshData (Face output from curve nodes)
            if curve.faces and len(curve.faces[0]) >= 3:
                f_indices = curve.faces[0]
                pts = [Vec3(curve.vertices[idx][0], curve.vertices[idx][1], curve.vertices[idx][2]) for idx in f_indices]
            else:
                pts = [Vec3(v[0], v[1], v[2]) for v in curve.vertices]
            is_closed = True
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
        outer_pts = _offset_points(base_pts, half_th, is_closed=is_closed)
        inner_pts = _offset_points(base_pts, -half_th, is_closed=is_closed)

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

        if is_closed:
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
        else:
            # Open curve wall: n-1 segments with watertight start and end caps
            # 1. Outer vertical side faces (0..n-2)
            for i in range(n - 1):
                faces.append([i, i + 1, n + i + 1, n + i])
                edges.append((i, i + 1))
                edges.append((n + i, n + i + 1))
                edges.append((i, n + i))
            edges.append((n - 1, 2 * n - 1))

            # 2. Inner vertical side faces (0..n-2, facing inward)
            for i in range(n - 1):
                faces.append([2 * n + i + 1, 2 * n + i, 3 * n + i, 3 * n + i + 1])
                edges.append((2 * n + i, 2 * n + i + 1))
                edges.append((3 * n + i, 3 * n + i + 1))
                edges.append((2 * n + i, 3 * n + i))
            edges.append((3 * n - 1, 4 * n - 1))

            # 3. Top cap quads (0..n-2)
            for i in range(n - 1):
                faces.append([n + i, n + i + 1, 3 * n + i + 1, 3 * n + i])

            # 4. Bottom cap quads (0..n-2)
            for i in range(n - 1):
                faces.append([i, 2 * n + i, 2 * n + i + 1, i + 1])

            # 5. Start end-cap quad (at i = 0)
            faces.append([0, n, 3 * n, 2 * n])
            edges.append((0, 2 * n))
            edges.append((n, 3 * n))

            # 6. Finish end-cap quad (at i = n - 1)
            faces.append([n - 1, 2 * n + n - 1, 3 * n + n - 1, n + n - 1])
            edges.append((n - 1, 2 * n + n - 1))
            edges.append((2 * n - 1, 4 * n - 1))

        # Deduplicate edges while preserving order
        unique_edges = list(dict.fromkeys(edges))

        wall_mesh = MeshData(
            vertices=verts,
            faces=faces,
            edges=unique_edges,
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


# ============================================================================
# 3. Architectural Grid Node (Structural Axes)
# ============================================================================
def _parse_grid_spacings(val: Any, fallback: List[float]) -> List[float]:
    """
    Parses distances between axes from:
    - Lists of floats/ints/strings from Panel or Math nodes
    - Multi-line or comma/space separated strings
    - Single float or int
    """
    if val is None:
        return list(fallback)
    if isinstance(val, (int, float)):
        v = float(val)
        return [v] if v > 1e-4 else list(fallback)
    if isinstance(val, str):
        cleaned = val.replace(";", ",").replace("\n", ",")
        parts = [p.strip() for p in cleaned.split(",") if p.strip()]
        if len(parts) <= 1 and " " in val.strip():
            parts = [p.strip() for p in val.strip().split() if p.strip()]
        res: List[float] = []
        for p in parts:
            try:
                num = float(p)
                if num > 1e-4:
                    res.append(num)
            except ValueError:
                pass
        return res if res else list(fallback)
    if isinstance(val, (list, tuple)):
        res: List[float] = []
        for item in val:
            if isinstance(item, (int, float)):
                if float(item) > 1e-4:
                    res.append(float(item))
            elif isinstance(item, str):
                sub = _parse_grid_spacings(item, [])
                res.extend(sub)
        return res if res else list(fallback)
    return list(fallback)


@register_node
class ArchitecturalGridNode(BaseNode):
    type_id = "arch.grid"
    title = "Architectural Grid"
    category = "Architecture"
    description = (
        "Generates parametric architectural grid axes (structural gridlines) from lists of\n"
        "spacing distances between consecutive X and Y axes.\n"
        "Connect directly to Panel nodes (multi-line or comma-separated numbers) or numeric lists.\n"
        "Outputs axis curves (X lines, Y lines), bubble markers, intersection points for columns/foundations, and a 3D wireframe mesh."
    )
    header_color = (191, 97, 106)

    inputs = [
        InputSpec("x_spacings", "X Spacings", SocketType.ANY, default="6.0, 6.0, 6.0", access=AccessMode.LIST),
        InputSpec("y_spacings", "Y Spacings", SocketType.ANY, default="5.0, 5.0", access=AccessMode.LIST),
        InputSpec("extension", "Extension (m)", SocketType.FLOAT, default=1.5, min_val=0.0, max_val=20.0, step=0.5),
        InputSpec("bubble_radius", "Bubble Radius (m)", SocketType.FLOAT, default=0.45, min_val=0.0, max_val=5.0, step=0.05),
        InputSpec("elevation", "Elevation (m)", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("both_ends", "Both Ends Bubbles", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("curves", "All Curves", SocketType.CURVE),
        OutputSpec("x_lines", "X Axis Lines", SocketType.CURVE),
        OutputSpec("y_lines", "Y Axis Lines", SocketType.CURVE),
        OutputSpec("points", "Grid Points", SocketType.VEC3),
        OutputSpec("bubbles", "Bubbles", SocketType.CURVE),
        OutputSpec("mesh", "Grid Wire Mesh", SocketType.MESH),
        OutputSpec("x_coords", "X Coords", SocketType.ANY),
        OutputSpec("y_coords", "Y Coords", SocketType.ANY),
    ]

    def get_card_badge_text(self) -> Optional[str]:
        x_c = self.cached_outputs.get("x_coords")
        y_c = self.cached_outputs.get("y_coords")
        pts = self.cached_outputs.get("points")
        if isinstance(x_c, list) and isinstance(y_c, list):
            pt_count = len(pts) if isinstance(pts, list) else len(x_c) * len(y_c)
            return f"{len(x_c)} × {len(y_c)} Axes ({pt_count} Pts)"
        return None

    def compute(
        self,
        x_spacings: Any = None,
        y_spacings: Any = None,
        extension: float = 1.5,
        bubble_radius: float = 0.45,
        elevation: float = 0.0,
        origin: Vec3 = Vec3(0, 0, 0),
        both_ends: bool = False,
    ) -> Dict[str, Any]:
        x_sp = _parse_grid_spacings(x_spacings, [6.0, 6.0, 6.0])
        y_sp = _parse_grid_spacings(y_spacings, [5.0, 5.0])
        ext = max(0.0, float(extension))
        r_bubble = max(0.0, float(bubble_radius))
        orig = origin if isinstance(origin, Vec3) else Vec3()
        z = orig.z + float(elevation)

        # Accumulate X coordinates
        x_coords = [orig.x]
        for d in x_sp:
            x_coords.append(round(x_coords[-1] + d, 4))

        # Accumulate Y coordinates
        y_coords = [orig.y]
        for d in y_sp:
            y_coords.append(round(y_coords[-1] + d, 4))

        x_min, x_max = x_coords[0], x_coords[-1]
        y_min, y_max = y_coords[0], y_coords[-1]

        y_line_s = y_min - ext
        y_line_e = y_max + ext
        x_line_s = x_min - ext
        x_line_e = x_max + ext

        # Generate vertical axis lines (running along Y, placed at each X)
        x_lines: List[CurveData] = []
        for x in x_coords:
            x_lines.append(CurveData(points=[Vec3(x, y_line_s, z), Vec3(x, y_line_e, z)], closed=False))

        # Generate horizontal axis lines (running along X, placed at each Y)
        y_lines: List[CurveData] = []
        for y in y_coords:
            y_lines.append(CurveData(points=[Vec3(x_line_s, y, z), Vec3(x_line_e, y, z)], closed=False))

        # Intersection grid points
        grid_points: List[Vec3] = []
        for x in x_coords:
            for y in y_coords:
                grid_points.append(Vec3(x, y, z))

        # Grid bubbles (circular curves at axis terminals)
        bubbles: List[CurveData] = []
        num_circle_segs = 24
        if r_bubble > 1e-4:
            # Vertical axes bubbles (at top, and optionally at bottom)
            for x in x_coords:
                top_c = Vec3(x, y_line_e + r_bubble, z)
                top_pts = [
                    Vec3(top_c.x + r_bubble * math.cos(i * 2.0 * math.pi / num_circle_segs),
                         top_c.y + r_bubble * math.sin(i * 2.0 * math.pi / num_circle_segs),
                         z)
                    for i in range(num_circle_segs)
                ]
                bubbles.append(CurveData(points=top_pts, closed=True))

                if both_ends:
                    bot_c = Vec3(x, y_line_s - r_bubble, z)
                    bot_pts = [
                        Vec3(bot_c.x + r_bubble * math.cos(i * 2.0 * math.pi / num_circle_segs),
                             bot_c.y + r_bubble * math.sin(i * 2.0 * math.pi / num_circle_segs),
                             z)
                        for i in range(num_circle_segs)
                    ]
                    bubbles.append(CurveData(points=bot_pts, closed=True))

            # Horizontal axes bubbles (at left, and optionally at right)
            for y in y_coords:
                left_c = Vec3(x_line_s - r_bubble, y, z)
                left_pts = [
                    Vec3(left_c.x + r_bubble * math.cos(i * 2.0 * math.pi / num_circle_segs),
                         left_c.y + r_bubble * math.sin(i * 2.0 * math.pi / num_circle_segs),
                         z)
                    for i in range(num_circle_segs)
                ]
                bubbles.append(CurveData(points=left_pts, closed=True))

                if both_ends:
                    right_c = Vec3(x_line_e + r_bubble, y, z)
                    right_pts = [
                        Vec3(right_c.x + r_bubble * math.cos(i * 2.0 * math.pi / num_circle_segs),
                             right_c.y + r_bubble * math.sin(i * 2.0 * math.pi / num_circle_segs),
                             z)
                        for i in range(num_circle_segs)
                    ]
                    bubbles.append(CurveData(points=right_pts, closed=True))

        all_curves = list(x_lines) + list(y_lines) + list(bubbles)

        # Build combined 3D wireframe MeshData
        mesh_verts: List[Tuple[float, float, float]] = []
        mesh_edges: List[Tuple[int, int]] = []

        def _add_curve_to_mesh(c: CurveData) -> None:
            if not c.points:
                return
            base_idx = len(mesh_verts)
            for p in c.points:
                mesh_verts.append((p.x, p.y, p.z))
            k = len(c.points)
            for i in range(k - 1):
                mesh_edges.append((base_idx + i, base_idx + i + 1))
            if c.closed and k >= 3:
                mesh_edges.append((base_idx + k - 1, base_idx))

        for c in all_curves:
            _add_curve_to_mesh(c)

        grid_mesh = MeshData(
            vertices=mesh_verts,
            faces=[],
            edges=mesh_edges,
            name="Architectural_Grid",
            ifc_class="IfcGrid",
        )

        return {
            "curves": all_curves,
            "x_lines": x_lines,
            "y_lines": y_lines,
            "points": grid_points,
            "bubbles": bubbles,
            "mesh": grid_mesh,
            "x_coords": x_coords,
            "y_coords": y_coords,
        }

