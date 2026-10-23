# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric 2D/3D Curve Shape Nodes."""

from __future__ import annotations
import math
from typing import Any, Dict, List

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


# ============================================================================
# 1. Circle Curve Node
# ============================================================================
@register_node
class CircleCurveNode(BaseNode):
    type_id = "curve.circle"
    title = "Circle Curve"
    category = "Curves"
    description = "Generates a closed circular polyline curve and optional planar face."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=2.0, min_val=0.01, step=0.1),
        InputSpec("angle", "Angle (°)", SocketType.FLOAT, default=360.0, min_val=1.0, max_val=360.0, step=5.0),
        InputSpec("segments", "Segments", SocketType.INT, default=32, min_val=3, max_val=256, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, radius: float, angle: float = 360.0, segments: int = 32, center: Vec3 = None) -> Dict[str, Any]:
        r = max(1e-4, float(radius))
        ang_deg = float(angle) if angle is not None else 360.0
        n = max(3, int(segments))
        c = center or Vec3()

        is_full_circle = abs(ang_deg) >= 360.0 or abs(ang_deg) < 1e-4

        pts: List[Vec3] = []
        if is_full_circle:
            for i in range(n):
                ang = 2.0 * math.pi * i / n
                pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
            curve = CurveData(points=pts, closed=True)
            face = curve.to_mesh_face("CircleFace")
        else:
            total_rad = math.radians(ang_deg)
            for i in range(n + 1):
                ang = total_rad * i / n
                pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
            curve = CurveData(points=pts, closed=False)
            sector_curve = CurveData(points=[c] + pts, closed=True)
            face = sector_curve.to_mesh_face("ArcFace")

        return {
            "curve": curve,
            "face": face,
        }


# ============================================================================
# 2. Rectangle Curve Node (with optional Corner Fillet)
# ============================================================================
@register_node
class RectangleCurveNode(BaseNode):
    type_id = "curve.rectangle"
    title = "Rectangle Curve"
    category = "Curves"
    description = "Generates a rectangular polyline with optional rounded fillet corners."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Width (X)", SocketType.FLOAT, default=6.0, min_val=0.01, step=0.5),
        InputSpec("length", "Length (Y)", SocketType.FLOAT, default=4.0, min_val=0.01, step=0.5),
        InputSpec("fillet", "Fillet Radius", SocketType.FLOAT, default=0.0, min_val=0.0, step=0.1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, width: float, length: float, fillet: float, center: Vec3) -> Dict[str, Any]:
        w = max(1e-4, float(width))
        l = max(1e-4, float(length))
        c = center or Vec3()
        hw, hl = w * 0.5, l * 0.5
        r = max(0.0, min(float(fillet), hw - 1e-4, hl - 1e-4))

        pts: List[Vec3] = []
        if r < 1e-4:
            pts = [
                Vec3(c.x - hw, c.y - hl, c.z),
                Vec3(c.x + hw, c.y - hl, c.z),
                Vec3(c.x + hw, c.y + hl, c.z),
                Vec3(c.x - hw, c.y + hl, c.z),
            ]
        else:
            # Generate 4 filleted corners CCW
            corners = [
                (c.x + hw - r, c.y - hl + r, 270.0, 360.0),  # SE
                (c.x + hw - r, c.y + hl - r, 0.0, 90.0),     # NE
                (c.x - hw + r, c.y + hl - r, 90.0, 180.0),   # NW
                (c.x - hw + r, c.y - hl + r, 180.0, 270.0),  # SW
            ]
            segs_per_corner = 6
            for cx, cy, start_deg, end_deg in corners:
                for s in range(segs_per_corner):
                    ang = math.radians(start_deg + (end_deg - start_deg) * s / segs_per_corner)
                    pts.append(Vec3(cx + r * math.cos(ang), cy + r * math.sin(ang), c.z))

        curve = CurveData(points=pts, closed=True)
        return {
            "face": curve.to_mesh_face("RectangleFace"),
        }


# ============================================================================
# 3. Ellipse Curve Node
# ============================================================================
@register_node
class EllipseCurveNode(BaseNode):
    type_id = "curve.ellipse"
    title = "Ellipse Curve"
    category = "Curves"
    description = "Generates an elliptical polyline with independent X and Y radii."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("radius_x", "Radius X (m)", SocketType.FLOAT, default=3.0, min_val=0.01, step=0.2),
        InputSpec("radius_y", "Radius Y (m)", SocketType.FLOAT, default=1.8, min_val=0.01, step=0.2),
        InputSpec("segments", "Segments", SocketType.INT, default=36, min_val=6, max_val=256, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, radius_x: float, radius_y: float, segments: int, center: Vec3) -> Dict[str, Any]:
        rx = max(1e-4, float(radius_x))
        ry = max(1e-4, float(radius_y))
        n = max(6, int(segments))
        c = center or Vec3()
        pts: List[Vec3] = []
        for i in range(n):
            ang = 2.0 * math.pi * i / n
            pts.append(Vec3(c.x + rx * math.cos(ang), c.y + ry * math.sin(ang), c.z))
        curve = CurveData(points=pts, closed=True)
        return {"face": curve.to_mesh_face("EllipseFace")}


# ============================================================================
# 4. Regular Polygon Curve Node
# ============================================================================
@register_node
class RegularPolygonCurveNode(BaseNode):
    type_id = "curve.polygon"
    title = "Polygon Curve"
    category = "Curves"
    description = "Generates a regular polygon (triangle, pentagon, hexagon, octagon, etc.)."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=2.5, min_val=0.01, step=0.2),
        InputSpec("sides", "Sides", SocketType.INT, default=6, min_val=3, max_val=64, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, radius: float, sides: int, center: Vec3) -> Dict[str, Any]:
        r = max(1e-4, float(radius))
        s = max(3, int(sides))
        c = center or Vec3()
        pts: List[Vec3] = []
        for i in range(s):
            ang = 2.0 * math.pi * i / s
            pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
        curve = CurveData(points=pts, closed=True)
        return {"face": curve.to_mesh_face("PolygonFace")}


# ============================================================================
# 5. Star Curve Node
# ============================================================================
@register_node
class StarCurveNode(BaseNode):
    type_id = "curve.star"
    title = "Star Curve"
    category = "Curves"
    description = "Generates an n-pointed parametric star polyline."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("inner_radius", "Inner Radius", SocketType.FLOAT, default=1.2, min_val=0.01, step=0.1),
        InputSpec("outer_radius", "Outer Radius", SocketType.FLOAT, default=2.8, min_val=0.01, step=0.1),
        InputSpec("points_count", "Points Count", SocketType.INT, default=5, min_val=3, max_val=32, step=1),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, inner_radius: float, outer_radius: float, points_count: int, center: Vec3) -> Dict[str, Any]:
        r_in = max(1e-4, float(inner_radius))
        r_out = max(r_in + 1e-4, float(outer_radius))
        n = max(3, int(points_count))
        c = center or Vec3()
        pts: List[Vec3] = []
        for i in range(2 * n):
            ang = math.pi * i / n
            r = r_out if (i % 2 == 0) else r_in
            pts.append(Vec3(c.x + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
        curve = CurveData(points=pts, closed=True)
        return {"face": curve.to_mesh_face("StarFace")}


# ============================================================================
# 6. Slot / Capsule Curve Node
# ============================================================================
@register_node
class SlotCapsuleCurveNode(BaseNode):
    type_id = "curve.slot"
    title = "Slot / Capsule"
    category = "Curves"
    description = "Generates a pill / stadium / elongated slot polyline."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("length", "Length (m)", SocketType.FLOAT, default=5.0, min_val=0.1, step=0.5),
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.2),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, length: float, width: float, center: Vec3) -> Dict[str, Any]:
        l = max(0.1, float(length))
        w = max(0.05, float(width))
        c = center or Vec3()
        r = w * 0.5
        d = max(0.0, l * 0.5 - r)

        pts: List[Vec3] = []
        segs = 12
        # Right semicircular cap
        for i in range(segs + 1):
            ang = -math.pi * 0.5 + math.pi * i / segs
            pts.append(Vec3(c.x + d + r * math.cos(ang), c.y + r * math.sin(ang), c.z))
        # Left semicircular cap
        for i in range(segs + 1):
            ang = math.pi * 0.5 + math.pi * i / segs
            pts.append(Vec3(c.x - d + r * math.cos(ang), c.y + r * math.sin(ang), c.z))

        curve = CurveData(points=pts, closed=True)
        return {"face": curve.to_mesh_face("SlotFace")}


# ============================================================================
# 7. Architectural L-Shape Profile Curve Node
# ============================================================================
@register_node
class LShapeCurveNode(BaseNode):
    type_id = "curve.l_shape"
    title = "L-Shape Profile"
    category = "Curves"
    description = "Generates an architectural or structural L-shape polyline."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=8.0, min_val=0.5, step=0.5),
        InputSpec("length", "Length (m)", SocketType.FLOAT, default=10.0, min_val=0.5, step=0.5),
        InputSpec("leg_x", "Leg X (m)", SocketType.FLOAT, default=3.5, min_val=0.2, step=0.5),
        InputSpec("leg_y", "Leg Y (m)", SocketType.FLOAT, default=4.0, min_val=0.2, step=0.5),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, width: float, length: float, leg_x: float, leg_y: float, center: Vec3) -> Dict[str, Any]:
        w = max(0.5, float(width))
        l = max(0.5, float(length))
        lx = min(w - 0.1, max(0.1, float(leg_x)))
        ly = min(l - 0.1, max(0.1, float(leg_y)))
        c = center or Vec3()

        pts = [
            Vec3(c.x, c.y, c.z),
            Vec3(c.x + w, c.y, c.z),
            Vec3(c.x + w, c.y + ly, c.z),
            Vec3(c.x + lx, c.y + ly, c.z),
            Vec3(c.x + lx, c.y + l, c.z),
            Vec3(c.x, c.y + l, c.z),
        ]
        curve = CurveData(points=pts, closed=True)
        return {"face": curve.to_mesh_face("LShapeFace")}


# ============================================================================
# 8. Structural I-Beam / H-Profile Curve Node
# ============================================================================
@register_node
class IShapeCurveNode(BaseNode):
    type_id = "curve.i_shape"
    title = "I-Beam Profile"
    category = "Curves"
    description = "Generates a structural steel I-beam or H-profile cross section."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Flange Width (m)", SocketType.FLOAT, default=0.30, min_val=0.05, step=0.05),
        InputSpec("height", "Total Height (m)", SocketType.FLOAT, default=0.50, min_val=0.05, step=0.05),
        InputSpec("flange_thick", "Flange Thick (m)", SocketType.FLOAT, default=0.04, min_val=0.01, step=0.01),
        InputSpec("web_thick", "Web Thick (m)", SocketType.FLOAT, default=0.025, min_val=0.01, step=0.01),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(self, width: float, height: float, flange_thick: float, web_thick: float, center: Vec3) -> Dict[str, Any]:
        bf = max(0.05, float(width))
        d = max(0.05, float(height))
        tf = min(d * 0.4, max(0.005, float(flange_thick)))
        tw = min(bf * 0.8, max(0.005, float(web_thick)))
        c = center or Vec3()

        hw, hh = bf * 0.5, d * 0.5
        htw = tw * 0.5

        # 12 CCW vertices of an I-beam
        pts = [
            Vec3(c.x - hw, c.y - hh, c.z),
            Vec3(c.x + hw, c.y - hh, c.z),
            Vec3(c.x + hw, c.y - hh + tf, c.z),
            Vec3(c.x + htw, c.y - hh + tf, c.z),
            Vec3(c.x + htw, c.y + hh - tf, c.z),
            Vec3(c.x + hw, c.y + hh - tf, c.z),
            Vec3(c.x + hw, c.y + hh, c.z),
            Vec3(c.x - hw, c.y + hh, c.z),
            Vec3(c.x - hw, c.y + hh - tf, c.z),
            Vec3(c.x - htw, c.y + hh - tf, c.z),
            Vec3(c.x - htw, c.y - hh + tf, c.z),
            Vec3(c.x - hw, c.y - hh + tf, c.z),
        ]
        curve = CurveData(points=pts, closed=True)
        return {"face": curve.to_mesh_face("IBeamFace")}


# ============================================================================
# 9. Spiral / Helix Curve Node
# ============================================================================
@register_node
class SpiralCurveNode(BaseNode):
    type_id = "curve.spiral"
    title = "Spiral / Helix"
    category = "Curves"
    description = "Generates a 2D or 3D Archimedean spiral or helical stair path."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("start_radius", "Start Radius", SocketType.FLOAT, default=1.0, min_val=0.0, step=0.2),
        InputSpec("end_radius", "End Radius", SocketType.FLOAT, default=3.0, min_val=0.0, step=0.2),
        InputSpec("turns", "Turns", SocketType.FLOAT, default=3.0, min_val=0.5, max_val=20.0, step=0.5),
        InputSpec("height", "Total Height", SocketType.FLOAT, default=2.5, min_val=0.0, step=0.5),
        InputSpec("segments", "Segments", SocketType.INT, default=96, min_val=12, max_val=512, step=12),
        InputSpec("center", "Center", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
    ]

    def compute(
        self,
        start_radius: float,
        end_radius: float,
        turns: float,
        height: float,
        segments: int,
        center: Vec3,
    ) -> Dict[str, Any]:
        r0 = max(0.0, float(start_radius))
        r1 = max(0.0, float(end_radius))
        t = max(0.1, float(turns))
        h = float(height)
        n = max(12, int(segments))
        c = center or Vec3()

        total_angle = 2.0 * math.pi * t
        pts: List[Vec3] = []
        for i in range(n + 1):
            frac = i / n
            ang = total_angle * frac
            cur_r = r0 + (r1 - r0) * frac
            cur_z = c.z + h * frac
            pts.append(Vec3(c.x + cur_r * math.cos(ang), c.y + cur_r * math.sin(ang), cur_z))

        curve = CurveData(points=pts, closed=False)
        return {"curve": curve}


@register_node
class LineNode(BaseNode):
    type_id = "curve.line"
    title = "Line Segment"
    category = "Curves"
    description = "Generates a straight 3D line curve connecting start point A and end point B."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("start", "Start Pt A", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("end", "End Pt B", SocketType.VEC3, default=Vec3(5, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
    ]

    def compute(self, start: Vec3, end: Vec3) -> Dict[str, Any]:
        p0 = start or Vec3()
        p1 = end or Vec3(1, 0, 0)
        curve = CurveData(points=[p0, p1], closed=False)
        length = (p1 - p0).length()
        return {"curve": curve, "length": length}


@register_node
class FaceFromPointsNode(BaseNode):
    type_id = "curve.face_from_points"
    title = "Face from Points"
    category = "Curves"
    description = "Generates a planar 2D/3D polygon face mesh from boundary vertices and optional hole loops."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("points", "Boundary Points", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("holes", "Holes", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("face", "Face Mesh", SocketType.MESH),
    ]

    def compute(self, points: Any, holes: Any = None) -> Dict[str, Any]:
        outer: List[Vec3] = []
        if isinstance(points, CurveData):
            outer = list(points.points)
        elif isinstance(points, list):
            for p in points:
                if isinstance(p, Vec3):
                    outer.append(p)
                elif isinstance(p, (tuple, list)) and len(p) >= 3:
                    outer.append(Vec3(float(p[0]), float(p[1]), float(p[2])))

        if len(outer) < 3:
            outer = [Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(4, 4, 0), Vec3(0, 4, 0)]

        outer_curve = CurveData(points=outer, closed=True)
        face_mesh = outer_curve.to_mesh_face("PlanarPolygonFace")
        return {"face": face_mesh}

# ============================================================================
# 11. Curve / Surface Points Extraction Node
# ============================================================================
@register_node
class CurvePointsNode(BaseNode):
    type_id = "curve.points"
    title = "Curve Points"
    category = "Curves"
    description = "Extracts vertices or boundary points from any input curve or surface / planar mesh."
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("geometry", "Curve / Surface", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("curve", "Boundary Curve", SocketType.CURVE),
        OutputSpec("count", "Count", SocketType.INT),
    ]

    def compute(self, geometry: Any = None) -> Dict[str, Any]:
        pts: List[Vec3] = []
        is_closed = True

        if isinstance(geometry, CurveData):
            pts = [Vec3(p.x, p.y, p.z) for p in geometry.points]
            is_closed = geometry.closed
        elif isinstance(geometry, MeshData):
            verts = geometry.vertices
            faces = geometry.faces
            if faces:
                if len(faces) == 1:
                    pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in faces[0]]
                else:
                    half_edges = set()
                    edge_counts = {}
                    for face in faces:
                        fn = len(face)
                        for i in range(fn):
                            u, v = face[i], face[(i + 1) % fn]
                            half_edges.add((u, v))
                            undir = (min(u, v), max(u, v))
                            edge_counts[undir] = edge_counts.get(undir, 0) + 1

                    boundary_next = {}
                    for (u, v) in half_edges:
                        if (v, u) not in half_edges or edge_counts.get((min(u, v), max(u, v)), 0) == 1:
                            boundary_next[u] = v

                    if boundary_next:
                        visited = set()
                        loops = []
                        for start_node in list(boundary_next.keys()):
                            if start_node in visited:
                                continue
                            loop = []
                            curr = start_node
                            while curr is not None and curr not in visited:
                                visited.add(curr)
                                loop.append(curr)
                                curr = boundary_next.get(curr)
                                if curr == start_node:
                                    break
                            if len(loop) >= 2:
                                loops.append(loop)

                        if loops:
                            def loop_perimeter(lp):
                                p = 0.0
                                for i in range(len(lp)):
                                    p0 = verts[lp[i]]
                                    p1 = verts[lp[(i + 1) % len(lp)]]
                                    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
                                    p += (dx*dx + dy*dy + dz*dz)**0.5
                                return p

                            largest_loop = max(loops, key=loop_perimeter)
                            pts = [Vec3(verts[i][0], verts[i][1], verts[i][2]) for i in largest_loop]
                        else:
                            pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                    else:
                        pts = [Vec3(v[0], v[1], v[2]) for v in verts]
            elif geometry.edges:
                pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                is_closed = False
            elif verts:
                pts = [Vec3(v[0], v[1], v[2]) for v in verts]
                is_closed = False
        elif isinstance(geometry, list):
            for item in geometry:
                if isinstance(item, Vec3):
                    pts.append(item)
                elif isinstance(item, (tuple, list)) and len(item) >= 3:
                    pts.append(Vec3(float(item[0]), float(item[1]), float(item[2])))
            is_closed = False
        elif isinstance(geometry, Vec3):
            pts = [geometry]
            is_closed = False

        curve = CurveData(points=pts, closed=is_closed)
        return {
            "points": pts,
            "curve": curve,
            "count": len(pts),
        }

