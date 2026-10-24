# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric 2D/3D Curve Shape Nodes."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from ..node_base import BaseNode, DynamicInputsMixin, InputSpec, OutputSpec, register_node, NODE_REGISTRY
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from node_base import BaseNode, DynamicInputsMixin, InputSpec, OutputSpec, register_node, NODE_REGISTRY


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
    description = (
        "Generates a rectangular polyline with optional rounded fillet corners.\n"
        "Supports drawing from corner or centered on origin/plane, with 3D plane orientation."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("width", "Width (X)", SocketType.FLOAT, default=6.0, min_val=0.01, step=0.5),
        InputSpec("length", "Length (Y)", SocketType.FLOAT, default=4.0, min_val=0.01, step=0.5),
        InputSpec("fillet", "Fillet Radius", SocketType.FLOAT, default=0.0, min_val=0.0, step=0.1),
        InputSpec("origin", "Origin / Plane", SocketType.ANY, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("plane", "Plane", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("centered", "Center", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("curve", "Curve", SocketType.CURVE),
        OutputSpec("face", "Face", SocketType.MESH),
    ]

    def compute(
        self,
        width: float = 6.0,
        length: float = 4.0,
        fillet: float = 0.0,
        origin: Any = None,
        centered: Any = True,
        plane: Any = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        # Handle backwards-compatibility and flexible wiring
        if "center" in kwargs:
            c_val = kwargs["center"]
            if isinstance(c_val, bool):
                centered = c_val
            elif c_val is not None:
                origin = c_val

        # If boolean toggle was wired into origin socket
        if isinstance(origin, bool):
            centered = origin
            origin = None

        frame_src = plane if plane is not None else origin
        p0, u, v, n = extract_plane_frame(frame_src)

        w = max(1e-4, float(width))
        l = max(1e-4, float(length))
        is_centered = bool(centered)

        if is_centered:
            hw, hl = w * 0.5, l * 0.5
            x_min, x_max = -hw, hw
            y_min, y_max = -hl, hl
        else:
            x_min, x_max = 0.0, w
            y_min, y_max = 0.0, l

        r = max(0.0, min(float(fillet), (x_max - x_min) * 0.5 - 1e-4, (y_max - y_min) * 0.5 - 1e-4))

        local_pts: List[Tuple[float, float]] = []
        if r < 1e-4:
            local_pts = [
                (x_min, y_min),
                (x_max, y_min),
                (x_max, y_max),
                (x_min, y_max),
            ]
        else:
            # 4 filleted corners CCW: SE, NE, NW, SW
            corners = [
                (x_max - r, y_min + r, 270.0, 360.0),  # SE
                (x_max - r, y_max - r, 0.0, 90.0),     # NE
                (x_min + r, y_max - r, 90.0, 180.0),   # NW
                (x_min + r, y_min + r, 180.0, 270.0),  # SW
            ]
            segs_per_corner = 6
            for cx, cy, start_deg, end_deg in corners:
                for s in range(segs_per_corner):
                    ang = math.radians(start_deg + (end_deg - start_deg) * s / segs_per_corner)
                    local_pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

        # Transform local (lx, ly) to 3D world: P = p0 + lx*u + ly*v
        world_pts: List[Vec3] = []
        for lx, ly in local_pts:
            wx = p0.x + lx * u.x + ly * v.x
            wy = p0.y + lx * u.y + ly * v.y
            wz = p0.z + lx * u.z + ly * v.z
            world_pts.append(Vec3(wx, wy, wz))

        curve = CurveData(points=world_pts, closed=True)
        return {
            "curve": curve,
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


# ============================================================================
# 13. Divide Curve Node
# ============================================================================
@register_node
class DivideCurveNode(BaseNode):
    type_id = "curve.divide"
    title = "Divide Curve"
    category = "Curves"
    description = (
        "Divide a curve or face boundary into equal-length segments, outputting division points, tangent-aligned planes,\n"
        "tangent vectors, normal vectors, and segment curves along the perimeter."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curve", "Curve / Face", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("count", "Count", SocketType.INT, default=10, min_val=1, max_val=500, step=1),
        InputSpec("include_ends", "Include Ends", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("points", "Points", SocketType.VEC3),
        OutputSpec("planes", "Planes", SocketType.ANY),
        OutputSpec("tangents", "Tangents", SocketType.VEC3),
        OutputSpec("normals", "Normals", SocketType.VEC3),
        OutputSpec("segments", "Segments", SocketType.ANY),
        OutputSpec("params", "Parameters (0-1)", SocketType.FLOAT),
        OutputSpec("curve", "Curve", SocketType.CURVE),
    ]

    def compute(self, curve: Any = None, count: int = 10, include_ends: bool = True) -> Dict[str, Any]:
        n_div = max(1, int(count))

        pts: List[Vec3] = []
        is_closed = False
        if isinstance(curve, CurveData) and curve.points:
            pts = [Vec3(p.x, p.y, p.z) for p in curve.points]
            is_closed = curve.closed
        elif isinstance(curve, MeshData):
            c = curve.perimeter_as_curve()
            pts = [Vec3(p.x, p.y, p.z) for p in c.points]
            is_closed = c.closed
        elif isinstance(curve, dict) and "outer" in curve:
            pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in curve.get("outer", [])]
            is_closed = True
        elif isinstance(curve, list) and curve:
            for p in curve:
                if isinstance(p, Vec3):
                    pts.append(p)
                elif isinstance(p, (list, tuple)) and len(p) >= 3:
                    pts.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
            is_closed = False

        if len(pts) < 2:
            pts = [Vec3(0.0, 0.0, 0.0), Vec3(10.0, 0.0, 0.0)]
            is_closed = False

        poly_pts = list(pts)
        if is_closed and (poly_pts[0].distance_to(poly_pts[-1]) > 1e-4):
            poly_pts.append(poly_pts[0])

        cum_lens: List[float] = [0.0]
        for i in range(len(poly_pts) - 1):
            seg_len = poly_pts[i].distance_to(poly_pts[i + 1])
            cum_lens.append(cum_lens[-1] + seg_len)

        total_len = cum_lens[-1]
        out_curve = CurveData(points=pts, closed=is_closed)
        if total_len < 1e-9:
            deg_p = poly_pts[0]
            deg_plane = {
                "origin": (deg_p.x, deg_p.y, deg_p.z),
                "u": (1.0, 0.0, 0.0),
                "v": (0.0, 1.0, 0.0),
                "normal": (0.0, 0.0, 1.0),
            }
            return {
                "points": [deg_p],
                "planes": [deg_plane],
                "tangents": [Vec3(1.0, 0.0, 0.0)],
                "normals": [Vec3(0.0, 1.0, 0.0)],
                "segments": [],
                "params": [0.0],
                "curve": out_curve,
            }

        div_points: List[Vec3] = []
        div_planes: List[Dict[str, Any]] = []
        div_tangents: List[Vec3] = []
        div_normals: List[Vec3] = []
        div_params: List[float] = []

        if is_closed:
            targets = [i * (total_len / n_div) for i in range(n_div)]
        else:
            if include_ends:
                targets = [i * (total_len / n_div) for i in range(n_div + 1)]
            else:
                targets = [(i + 1) * (total_len / (n_div + 1)) for i in range(n_div)]

        def sample_at(dist: float) -> Tuple[Vec3, Vec3]:
            idx = 0
            while idx < len(cum_lens) - 2 and cum_lens[idx + 1] < dist:
                idx += 1
            l0, l1 = cum_lens[idx], cum_lens[idx + 1]
            p0, p1 = poly_pts[idx], poly_pts[idx + 1]
            seg_l = max(1e-9, l1 - l0)
            t = max(0.0, min(1.0, (dist - l0) / seg_l))
            pt = Vec3(p0.x + t * (p1.x - p0.x), p0.y + t * (p1.y - p0.y), p0.z + t * (p1.z - p0.z))
            tang = (p1 - p0).normalized()
            return pt, tang

        for d in targets:
            p, t = sample_at(d)
            u = t.normalized()
            if u.length() < 1e-6:
                u = Vec3(1.0, 0.0, 0.0)

            # Upright guide vector
            if abs(u.z) < 0.95:
                guide = Vec3(0.0, 0.0, 1.0)
            else:
                guide = Vec3(1.0, 0.0, 0.0)

            # Normal vector in horizontal / transverse plane (guide x u)
            v_raw = guide.cross(u)
            v = v_raw.normalized()
            if v.length() < 1e-6:
                v = Vec3(0.0, 1.0, 0.0)

            # Upright vector normal to plane (u x v)
            n = u.cross(v).normalized()

            plane_dict = {
                "origin": (p.x, p.y, p.z),
                "u": (u.x, u.y, u.z),
                "v": (v.x, v.y, v.z),
                "normal": (n.x, n.y, n.z),
            }

            div_points.append(p)
            div_planes.append(plane_dict)
            div_tangents.append(u)
            div_normals.append(v)
            div_params.append(round(d / total_len, 6))

        segments: List[CurveData] = []
        if is_closed:
            for i in range(len(div_points)):
                p_curr = div_points[i]
                p_next = div_points[(i + 1) % len(div_points)]
                segments.append(CurveData(points=[p_curr, p_next], closed=False))
        else:
            for i in range(len(div_points) - 1):
                segments.append(CurveData(points=[div_points[i], div_points[i + 1]], closed=False))

        return {
            "points": div_points,
            "planes": div_planes,
            "tangents": div_tangents,
            "normals": div_normals,
            "segments": segments,
            "params": div_params,
            "curve": out_curve,
        }


# ============================================================================
# 14. Offset Curve Node
# ============================================================================
@register_node
class OffsetCurveNode(BaseNode):
    type_id = "curve.offset"
    title = "Offset Curve"
    category = "Curves"
    description = (
        "Offset a curve or surface in its plane (like walls or window frames in IngeTrazo).\n"
        "Outputs the offset curve, a frame mesh, and the offset curve face (clean planar face, no triangulation)."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curve", "Curve / Surface", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("distance", "Distance (m)", SocketType.FLOAT, default=0.2, min_val=-10.0, max_val=10.0, step=0.05),
        InputSpec("inset", "Inset (Inward)", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("curve", "Offset Curve", SocketType.CURVE),
        OutputSpec("frame", "Frame", SocketType.MESH),
        OutputSpec("face", "Curve Face", SocketType.MESH),
    ]

    @staticmethod
    def _line_intersect_2d(p0: Vec3, u: Vec3, p1: Vec3, v: Vec3, n: Vec3) -> Optional[Vec3]:
        cross_uv = u.cross(v)
        denom = cross_uv.dot(n)
        if abs(denom) < 1e-7:
            return Vec3((p0.x + p1.x) * 0.5, (p0.y + p1.y) * 0.5, (p0.z + p1.z) * 0.5)
        diff = p1 - p0
        diff_cross_v = diff.cross(v)
        s = diff_cross_v.dot(n) / denom
        return Vec3(p0.x + s * u.x, p0.y + s * u.y, p0.z + s * u.z)

    def compute(self, curve: Any = None, distance: float = 0.2, inset: bool = True) -> Dict[str, Any]:
        d = float(distance)
        if inset:
            d = abs(d)
        else:
            d = -abs(d)

        pts: List[Vec3] = []
        is_closed = True

        if isinstance(curve, CurveData) and curve.points:
            pts = [Vec3(p.x, p.y, p.z) for p in curve.points]
            is_closed = curve.closed
        elif isinstance(curve, MeshData):
            c = curve.perimeter_as_curve()
            pts = [Vec3(p.x, p.y, p.z) for p in c.points]
            is_closed = True
        elif isinstance(curve, dict) and "outer" in curve:
            pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in curve.get("outer", [])]
            is_closed = True
        elif isinstance(curve, list) and curve:
            for p in curve:
                if isinstance(p, Vec3):
                    pts.append(p)
                elif isinstance(p, (list, tuple)) and len(p) >= 3:
                    pts.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
            is_closed = True

        # Default fallback: 2.0m x 1.5m window profile at Z=1.0m
        if len(pts) < 3:
            pts = [
                Vec3(0.0, 0.0, 1.0),
                Vec3(2.0, 0.0, 1.0),
                Vec3(2.0, 0.0, 2.5),
                Vec3(0.0, 0.0, 2.5),
            ]
            is_closed = True

        n_pts = len(pts)

        nx = ny = nz = 0.0
        for i in range(n_pts):
            p0 = pts[i]
            p1 = pts[(i + 1) % n_pts]
            nx += (p0.y - p1.y) * (p0.z + p1.z)
            ny += (p0.z - p1.z) * (p0.x + p1.x)
            nz += (p0.x - p1.x) * (p0.y + p1.y)
        norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        if norm_len < 1e-9:
            normal = Vec3(0.0, 0.0, 1.0)
        else:
            normal = Vec3(nx / norm_len, ny / norm_len, nz / norm_len)

        offset_pts: List[Vec3] = []

        if is_closed and n_pts >= 3:
            offset_lines: List[Tuple[Vec3, Vec3]] = []
            for i in range(n_pts):
                a = pts[i]
                b = pts[(i + 1) % n_pts]
                edge = b - a
                e_dir = edge.normalized()
                inward = normal.cross(e_dir).normalized()
                line_pt = Vec3(a.x + inward.x * d, a.y + inward.y * d, a.z + inward.z * d)
                offset_lines.append((line_pt, e_dir))

            for i in range(n_pts):
                p0, u = offset_lines[(i - 1) % n_pts]
                p1, v = offset_lines[i]
                pt = self._line_intersect_2d(p0, u, p1, v, normal)
                if pt is None:
                    pt = pts[i]
                offset_pts.append(pt)

            for i in range(n_pts):
                orig_len = pts[i].distance_to(pts[(i + 1) % n_pts])
                new_len = offset_pts[i].distance_to(offset_pts[(i + 1) % n_pts])
                if new_len < 1e-4 or pts[i].distance_to(offset_pts[i]) > 10.0 * max(0.1, abs(d)):
                    centroid = Vec3(sum(p.x for p in pts) / n_pts, sum(p.y for p in pts) / n_pts, sum(p.z for p in pts) / n_pts)
                    scale_f = max(0.05, 1.0 - (d / max(1.0, orig_len)))
                    offset_pts = [Vec3(centroid.x + (p.x - centroid.x) * scale_f,
                                       centroid.y + (p.y - centroid.y) * scale_f,
                                       centroid.z + (p.z - centroid.z) * scale_f) for p in pts]
                    break
        else:
            for i in range(n_pts):
                if i == 0:
                    tang = (pts[1] - pts[0]).normalized()
                elif i == n_pts - 1:
                    tang = (pts[-1] - pts[-2]).normalized()
                else:
                    tang = (pts[i + 1] - pts[i - 1]).normalized()
                inward = normal.cross(tang).normalized()
                offset_pts.append(Vec3(pts[i].x + inward.x * d, pts[i].y + inward.y * d, pts[i].z + inward.z * d))

        offset_curve = CurveData(points=[Vec3(p.x, p.y, p.z) for p in offset_pts], closed=is_closed)

        frame_verts: List[Tuple[float, float, float]] = []
        frame_faces: List[List[int]] = []
        frame_edges: List[Tuple[int, int]] = []

        if is_closed and n_pts >= 3:
            def polygon_area(poly: List[Vec3], norm: Vec3) -> float:
                nx = ny = nz = 0.0
                k_len = len(poly)
                for k in range(k_len):
                    p0 = poly[k]
                    p1 = poly[(k + 1) % k_len]
                    nx += (p0.y - p1.y) * (p0.z + p1.z)
                    ny += (p0.z - p1.z) * (p0.x + p1.x)
                    nz += (p0.x - p1.x) * (p0.y + p1.y)
                return (nx * norm.x + ny * norm.y + nz * norm.z) * 0.5

            def ensure_ccw(poly: List[Vec3], norm: Vec3) -> List[Vec3]:
                if polygon_area(poly, norm) < 0:
                    return list(reversed(poly))
                return poly

            pts_ccw = ensure_ccw(pts, normal)
            off_ccw = ensure_ccw(offset_pts, normal)

            area_pts = polygon_area(pts_ccw, normal)
            area_off = polygon_area(off_ccw, normal)

            if area_off > area_pts:
                # Outward offset: offset_pts is larger outer ring, original pts is inner hole
                outer_loop = off_ccw
                hole_loop = pts_ccw
            else:
                # Inward offset: original pts is larger outer ring, offset_pts is inner hole
                outer_loop = pts_ccw
                hole_loop = off_ccw

            n_out = len(outer_loop)
            n_hole = len(hole_loop)

            for p in outer_loop:
                frame_verts.append((p.x, p.y, p.z))
            for p in hole_loop:
                frame_verts.append((p.x, p.y, p.z))

            # Single continuous annular face loop (outer loop CCW + bridge slit + inner hole CW + bridge back)
            single_face = list(range(n_out)) + [0, n_out] + [n_out + ((n_hole - 1 - j) % n_hole) for j in range(n_hole)] + [n_out, 0]
            frame_faces.append(single_face)

            # Only outer and inner boundary edges (NO radial dividing curves/edges!)
            for i in range(n_out):
                frame_edges.append((i, (i + 1) % n_out))
            for i in range(n_hole):
                frame_edges.append((n_out + i, n_out + (i + 1) % n_hole))

            frame_mesh = MeshData(
                vertices=frame_verts,
                faces=frame_faces,
                edges=frame_edges,
                name="Frame",
                material_name="Frame",
                color=(0.22, 0.24, 0.28),
                face_materials=["Frame"] * len(frame_faces),
                face_colors=[(0.22, 0.24, 0.28)] * len(frame_faces),
                outer=[(p.x, p.y, p.z) for p in outer_loop],
                holes=[[(p.x, p.y, p.z) for p in hole_loop]],
                holed_faces=[(list(range(n_out)), [list(range(n_out, n_out + n_hole))])],
            )
        else:
            for p in pts:
                frame_verts.append((p.x, p.y, p.z))
            for p in offset_pts:
                frame_verts.append((p.x, p.y, p.z))

            # Open curve ribbon (e.g. arc, polyline, line):
            # Form ONE single continuous planar face loop without interior radial dividing edges
            # Loop travels: 0 -> 1 -> ... -> n_pts - 1, across to 2*n_pts - 1 -> ... -> n_pts, back to 0
            ribbon_face = list(range(n_pts)) + list(range(2 * n_pts - 1, n_pts - 1, -1))

            # Orient ribbon_face so its normal matches the curve plane's normal
            poly_nx = poly_ny = poly_nz = 0.0
            m_poly = len(ribbon_face)
            for k in range(m_poly):
                pa = frame_verts[ribbon_face[k]]
                pb = frame_verts[ribbon_face[(k + 1) % m_poly]]
                poly_nx += (pa[1] - pb[1]) * (pa[2] + pb[2])
                poly_ny += (pa[2] - pb[2]) * (pa[0] + pb[0])
                poly_nz += (pa[0] - pb[0]) * (pa[1] + pb[1])

            if (poly_nx * normal.x + poly_ny * normal.y + poly_nz * normal.z) < 0:
                ribbon_face.reverse()

            frame_faces.append(ribbon_face)

            # Perimeter boundary edges only (outer curve + end cap + inner curve + start cap; ZERO radial dividing edges!)
            for i in range(n_pts - 1):
                frame_edges.append((i, i + 1))
                frame_edges.append((n_pts + i, n_pts + i + 1))
            frame_edges.append((0, n_pts))
            frame_edges.append((n_pts - 1, 2 * n_pts - 1))

            frame_mesh = MeshData(
                vertices=frame_verts,
                faces=frame_faces,
                edges=frame_edges,
                name="Frame",
                material_name="Frame",
                color=(0.22, 0.24, 0.28),
                face_materials=["Frame"] * len(frame_faces),
                face_colors=[(0.22, 0.24, 0.28)] * len(frame_faces),
                outer=[frame_verts[idx] for idx in ribbon_face],
                holes=[],
                holed_faces=[],
            )

        face_verts: List[Tuple[float, float, float]] = [(p.x, p.y, p.z) for p in offset_pts]
        face_faces: List[List[int]] = []
        face_edges: List[Tuple[int, int]] = []

        if is_closed and len(offset_pts) >= 3:
            m_off = len(offset_pts)
            # Clean single planar face (NO fan triangulation spokes!)
            face_faces.append(list(range(m_off)))
            for i in range(m_off):
                face_edges.append((i, (i + 1) % m_off))
        elif len(offset_pts) >= 2:
            for i in range(len(offset_pts) - 1):
                face_edges.append((i, i + 1))

        curve_face = MeshData(
            vertices=face_verts,
            faces=face_faces,
            edges=face_edges,
            name="OffsetCurveFace",
            material_name="Face",
            color=(0.55, 0.78, 0.92),
            face_materials=["Face"] * len(face_faces),
            face_colors=[(0.55, 0.78, 0.92)] * len(face_faces),
        )

        return {
            "curve": offset_curve,
            "frame": frame_mesh,
            "face": curve_face,
        }


# ============================================================================
# 15. Join Curves Node
# ============================================================================
@register_node
class JoinCurvesNode(BaseNode):
    type_id = "curve.join"
    title = "Join Curves"
    category = "Curves"
    description = (
        "Joins a list of contiguous open or closed curves/edges into unified polylines or closed loops.\n"
        "Connect directly to Curve Select (Curves output), List nodes (Create List, Merge), or multiple curve wires.\n"
        "Automatically bridges touching endpoints within tolerance and detects closed loops."
    )
    header_color = (68, 108, 179)

    inputs = [
        InputSpec("curves", "Curves List", SocketType.CURVE, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("tolerance", "Tolerance (m)", SocketType.FLOAT, default=0.001, min_val=0.0001, max_val=1.0, step=0.001),
        InputSpec("close", "Close Loop", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("curve", "Joined Curve", SocketType.CURVE),
        OutputSpec("curves", "Joined Curves", SocketType.ANY),
        OutputSpec("closed", "Is Closed", SocketType.BOOL),
        OutputSpec("length", "Length (m)", SocketType.FLOAT),
        OutputSpec("count", "Curve Count", SocketType.INT),
    ]

    @staticmethod
    def _gather_curves(val: Any, out_list: List[CurveData]) -> None:
        if val is None:
            return
        if isinstance(val, CurveData):
            out_list.append(val)
        elif isinstance(val, (list, tuple)):
            for item in val:
                JoinCurvesNode._gather_curves(item, out_list)
        elif isinstance(val, dict) and "points" in val:
            pts_raw = val.get("points", [])
            pts = [
                Vec3(float(p[0]), float(p[1]), float(p[2])) if isinstance(p, (list, tuple)) else p
                for p in pts_raw
                if p is not None
            ]
            if len(pts) >= 2:
                out_list.append(CurveData(points=pts, closed=bool(val.get("closed", False))))

    @staticmethod
    def _chain_curves(curves: List[CurveData], tolerance: float = 0.001, close_loop: bool = False) -> List[CurveData]:
        segments: List[Tuple[Vec3, Vec3]] = []
        for c in curves:
            pts = c.points
            if len(pts) < 2:
                continue
            n_segs = len(pts) if c.closed else len(pts) - 1
            for i in range(n_segs):
                p0 = pts[i]
                p1 = pts[(i + 1) % len(pts)]
                if p0.distance_to(p1) > 1e-6:
                    segments.append((p0, p1))

        if not segments:
            return []

        scale = 1.0 / max(1e-6, tolerance)

        def qkey(p: Vec3) -> Tuple[int, int, int]:
            return (round(p.x * scale), round(p.y * scale), round(p.z * scale))

        key_to_pt: Dict[Tuple[int, int, int], Vec3] = {}
        adj: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
        edges_set = set()

        for p0, p1 in segments:
            k0, k1 = qkey(p0), qkey(p1)
            if k0 == k1:
                continue
            edge_key = (min(k0, k1), max(k0, k1))
            if edge_key in edges_set:
                continue
            edges_set.add(edge_key)

            key_to_pt.setdefault(k0, p0)
            key_to_pt.setdefault(k1, p1)
            adj.setdefault(k0, []).append(k1)
            adj.setdefault(k1, []).append(k0)

        visited_edges = set()
        result_curves: List[CurveData] = []
        nodes = list(adj.keys())
        visited_nodes = set()

        for start_node in nodes:
            if start_node in visited_nodes:
                continue
            comp = []
            q = [start_node]
            visited_nodes.add(start_node)
            while q:
                curr = q.pop(0)
                comp.append(curr)
                for nbr in adj.get(curr, []):
                    if nbr not in visited_nodes:
                        visited_nodes.add(nbr)
                        q.append(nbr)

            deg1 = [k for k in comp if len(adj[k]) == 1]
            start_k = deg1[0] if deg1 else comp[0]

            curr = start_k
            path = [curr]
            while True:
                nbrs = [n for n in adj[curr] if (min(curr, n), max(curr, n)) not in visited_edges]
                if not nbrs:
                    break
                nxt = nbrs[0]
                visited_edges.add((min(curr, nxt), max(curr, nxt)))
                path.append(nxt)
                curr = nxt
                if curr == start_k:
                    break

            pts = [key_to_pt[k] for k in path]
            if len(pts) >= 2:
                is_closed = (path[0] == path[-1]) or (pts[0].distance_to(pts[-1]) <= tolerance) or close_loop
                if is_closed and len(pts) > 2 and (pts[0].distance_to(pts[-1]) <= tolerance):
                    pts = pts[:-1]
                result_curves.append(CurveData(points=pts, closed=is_closed))

        return result_curves

    def compute(
        self,
        curves: Any = None,
        tolerance: float = 0.001,
        close: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        tol = float(tolerance)
        close_loop = bool(close)

        collected: List[CurveData] = []
        if curves is not None:
            self._gather_curves(curves, collected)
        for k, v in kwargs.items():
            if k not in ("tolerance", "close"):
                self._gather_curves(v, collected)

        if not collected:
            fallback = CurveData(points=[Vec3(0, 0, 0), Vec3(1, 0, 0)], closed=False)
            return {
                "curve": fallback,
                "curves": [fallback],
                "closed": False,
                "length": 1.0,
                "count": 0,
            }

        joined_curves = self._chain_curves(collected, tolerance=tol, close_loop=close_loop)
        if not joined_curves:
            joined_curves = collected

        def _curve_length(c: CurveData) -> float:
            total = 0.0
            n_segs = len(c.points) if c.closed else len(c.points) - 1
            for i in range(n_segs):
                total += c.points[i].distance_to(c.points[(i + 1) % len(c.points)])
            return total

        primary = max(joined_curves, key=_curve_length)
        total_len = sum(_curve_length(c) for c in joined_curves)

        return {
            "curve": primary,
            "curves": joined_curves,
            "closed": primary.closed,
            "length": round(total_len, 4),
            "count": len(joined_curves),
        }


# ============================================================================
# Midpoint Node
# ============================================================================
@register_node
class MidpointNode(BaseNode):
    type_id = "curve.midpoint"
    title = "Midpoint"
    category = "Curves"
    description = (
        "Calculates the exact 50% length midpoint along a curve, or the midpoint between two points.\n"
        "Outputs the midpoint position, local tangent vector, and perpendicular alignment plane."
    )
    header_color = (68, 108, 179)
    icon = "point.midpoint.png"

    inputs = [
        InputSpec("curve", "Curve / Point A", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("point_b", "Point B", SocketType.VEC3, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("point", "Midpoint", SocketType.VEC3),
        OutputSpec("points", "Points", SocketType.ANY),
        OutputSpec("tangent", "Tangent", SocketType.VEC3),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, curve: Any = None, point_b: Any = None) -> Dict[str, Any]:
        if isinstance(point_b, Vec3) or (isinstance(curve, Vec3) and point_b is not None):
            pA = curve if isinstance(curve, Vec3) else Vec3(0, 0, 0)
            pB = point_b if isinstance(point_b, Vec3) else Vec3(0, 0, 0)
            mid = (pA + pB) * 0.5
            diff = pB - pA
            length = diff.length()
            tangent = diff * (1.0 / length) if length > 1e-7 else Vec3(1, 0, 0)

            guide = Vec3(0, 0, 1) if abs(tangent.z) < 0.9 else Vec3(0, 1, 0)
            n_raw = Vec3(
                tangent.y * guide.z - tangent.z * guide.y,
                tangent.z * guide.x - tangent.x * guide.z,
                tangent.x * guide.y - tangent.y * guide.x,
            )
            n_len = n_raw.length()
            norm = n_raw * (1.0 / n_len) if n_len > 1e-7 else Vec3(0, 0, 1)
            u = tangent
            v = Vec3(
                norm.y * u.z - norm.z * u.y,
                norm.z * u.x - norm.x * u.z,
                norm.x * u.y - norm.y * u.x,
            )

            plane_dict = {
                "origin": (mid.x, mid.y, mid.z),
                "normal": (tangent.x, tangent.y, tangent.z),
                "u_axis": (norm.x, norm.y, norm.z),
                "v_axis": (v.x, v.y, v.z),
            }
            return {
                "point": mid,
                "points": [mid],
                "tangent": tangent,
                "plane": plane_dict,
            }

        def _mid_curve(c: CurveData) -> Tuple[Vec3, Vec3, Dict[str, Any]]:
            pts = list(c.points)
            if not pts:
                p0 = Vec3(0, 0, 0)
                return p0, Vec3(1, 0, 0), {"origin": (0, 0, 0), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            if len(pts) == 1:
                p0 = pts[0]
                return p0, Vec3(1, 0, 0), {"origin": (p0.x, p0.y, p0.z), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            if c.closed and (pts[-1] - pts[0]).length() > 1e-6:
                pts.append(pts[0])

            seg_lens = []
            total_len = 0.0
            for i in range(len(pts) - 1):
                sl = (pts[i + 1] - pts[i]).length()
                seg_lens.append(sl)
                total_len += sl

            if total_len < 1e-8:
                p0 = pts[0]
                return p0, Vec3(1, 0, 0), {"origin": (p0.x, p0.y, p0.z), "normal": (0, 0, 1), "u_axis": (1, 0, 0), "v_axis": (0, 1, 0)}

            target_len = total_len * 0.5
            accum = 0.0
            mid_pt = pts[-1]
            tan_vec = Vec3(1, 0, 0)

            for i, sl in enumerate(seg_lens):
                if accum + sl >= target_len - 1e-8:
                    sub_t = (target_len - accum) / sl if sl > 1e-8 else 0.0
                    sub_t = max(0.0, min(1.0, sub_t))
                    mid_pt = pts[i] + (pts[i + 1] - pts[i]) * sub_t
                    diff = pts[i + 1] - pts[i]
                    tan_vec = diff * (1.0 / sl) if sl > 1e-8 else Vec3(1, 0, 0)
                    break
                accum += sl

            guide = Vec3(0, 0, 1) if abs(tan_vec.z) < 0.9 else Vec3(0, 1, 0)
            n_raw = Vec3(
                tan_vec.y * guide.z - tan_vec.z * guide.y,
                tan_vec.z * guide.x - tan_vec.x * guide.z,
                tan_vec.x * guide.y - tan_vec.y * guide.x,
            )
            n_len = n_raw.length()
            norm = n_raw * (1.0 / n_len) if n_len > 1e-7 else Vec3(0, 0, 1)
            u = tan_vec
            v = Vec3(
                norm.y * u.z - norm.z * u.y,
                norm.z * u.x - norm.x * u.z,
                norm.x * u.y - norm.y * u.x,
            )

            plane_dict = {
                "origin": (mid_pt.x, mid_pt.y, mid_pt.z),
                "normal": (tan_vec.x, tan_vec.y, tan_vec.z),
                "u_axis": (norm.x, norm.y, norm.z),
                "v_axis": (v.x, v.y, v.z),
            }
            return mid_pt, tan_vec, plane_dict

        if isinstance(curve, list) and curve and isinstance(curve[0], CurveData):
            mids = [_mid_curve(c) for c in curve]
            return {
                "point": mids[0][0],
                "points": [m[0] for m in mids],
                "tangent": mids[0][1],
                "plane": mids[0][2],
            }

        if not isinstance(curve, CurveData):
            curve = CurveData(points=[Vec3(0, 0, 0), Vec3(2, 0, 0)], closed=False)

        mid_pt, tan_vec, pl = _mid_curve(curve)
        return {
            "point": mid_pt,
            "points": [mid_pt],
            "tangent": tan_vec,
            "plane": pl,
        }

NODE_REGISTRY["point.midpoint"] = MidpointNode
