# SPDX-License-Identifier: GPL-3.0-or-later
"""Core data types, socket specifications, and watertight geometry primitives."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, List, Optional, Tuple


class SocketType(str, Enum):
    FLOAT = "FLOAT"
    INT = "INT"
    BOOL = "BOOL"
    STRING = "STRING"
    VEC3 = "VEC3"
    POINT = "VEC3"
    VECTOR = "VEC3"
    CURVE = "CURVE"
    MESH = "MESH"
    ANY = "ANY"


class AccessMode(str, Enum):
    """Grasshopper-style access mode for node inputs."""
    ITEM = "ITEM"  # Engine auto-broadcasts lists and calls compute() per item
    LIST = "LIST"  # Engine passes the full list directly into compute()


# Color palette (R, G, B) for socket pins and wires
SOCKET_COLORS: dict[SocketType, Tuple[int, int, int]] = {
    SocketType.FLOAT:  (86, 182, 194),   # Cyan
    SocketType.INT:    (97, 175, 239),   # Blue
    SocketType.BOOL:   (224, 108, 117),  # Coral Red
    SocketType.STRING: (229, 192, 123),  # Warm Yellow
    SocketType.VEC3:   (152, 195, 121),  # Green
    SocketType.CURVE:  (209, 154, 102),  # Orange
    SocketType.MESH:   (198, 120, 221),  # Purple
    SocketType.ANY:    (171, 178, 191),  # Grey
}


@dataclass(frozen=True)
class Vec3:
    """Immutable 3D Vector/Point in Z-up meter coordinates."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, o: Vec3) -> Vec3:
        return Vec3(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: Vec3) -> Vec3:
        return Vec3(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, s: float) -> Vec3:
        return Vec3(self.x * s, self.y * s, self.z * s)

    def dot(self, o: Vec3) -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o: Vec3) -> Vec3:
        return Vec3(
            self.y * o.z - self.z * o.y,
            self.z * o.x - self.x * o.z,
            self.x * o.y - self.y * o.x,
        )

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def distance_to(self, o: Vec3) -> float:
        return (self - o).length()

    def normalized(self) -> Vec3:
        ln = self.length()
        return self * (1.0 / ln) if ln > 1e-12 else Vec3(0.0, 0.0, 1.0)

    def to_tuple(self) -> Tuple[float, float, float]:
        return (float(self.x), float(self.y), float(self.z))


@dataclass
class CurveData:
    """3D polyline or closed profile loop."""
    points: List[Vec3] = field(default_factory=list)
    closed: bool = False

    def copy(self) -> CurveData:
        return CurveData(points=[Vec3(p.x, p.y, p.z) for p in self.points], closed=self.closed)

    def transformed(
        self,
        offset: Vec3 = Vec3(),
        rot_z_deg: float = 0.0,
        scale: Vec3 = Vec3(1.0, 1.0, 1.0),
    ) -> CurveData:
        rad = math.radians(rot_z_deg)
        c, s = math.cos(rad), math.sin(rad)
        out_pts: List[Vec3] = []
        for p in self.points:
            sx, sy, sz = p.x * scale.x, p.y * scale.y, p.z * scale.z
            rx = sx * c - sy * s
            ry = sx * s + sy * c
            out_pts.append(Vec3(rx + offset.x, ry + offset.y, sz + offset.z))
        return CurveData(points=out_pts, closed=self.closed)

    def to_mesh_face(self, name: str = "PlanarCurveFace") -> MeshData:
        """Converts a closed planar curve into a single-face MeshData."""
        pts = [p.to_tuple() for p in self.points]
        if not pts or len(pts) < 3:
            return MeshData(name=name)
        # Ensure CCW orientation (positive 2D signed area)
        area2 = sum(
            pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
            for i in range(len(pts))
        )
        if area2 < 0:
            pts.reverse()
        face_idx = list(range(len(pts)))
        edges = [(i, (i + 1) % len(pts)) for i in range(len(pts))]
        return MeshData(vertices=pts, faces=[face_idx], edges=edges, name=name)

    def to_wire_mesh(self, name: str = "CurveWire") -> MeshData:
        """Converts curve into an edge-based wire MeshData for 3D viewport preview."""
        pts = [p.to_tuple() for p in self.points]
        if not pts:
            return MeshData(name=name)
        n = len(pts)
        if n < 2:
            return MeshData(vertices=pts, edges=[], name=name)
        edges = [(i, i + 1) for i in range(n - 1)]
        if self.closed and n >= 3:
            edges.append((n - 1, 0))
        return MeshData(vertices=pts, faces=[], edges=edges, name=name)


@dataclass
class MeshData:
    """
    Pure-Python B-Rep/Polygon Mesh container compatible with IngeTrazo's core.mesh.Mesh.
    All faces use Counter-Clockwise (CCW) outward winding so solids pass IngeTrazo's
    hermeticity guard (`is_closed` / `solid_report`) and report accurate IFC volumes.
    """
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    edges: List[Tuple[int, int]] = field(default_factory=list)
    color: Optional[Tuple[float, float, float]] = None
    material_name: str = ""
    opacity: Optional[float] = None
    face_materials: List[str] = field(default_factory=list)
    face_colors: List[Optional[Tuple[float, float, float]]] = field(default_factory=list)
    face_opacities: List[Optional[float]] = field(default_factory=list)
    ifc_class: str = ""
    name: str = "ParametricSolid"

    def copy(self) -> MeshData:
        return MeshData(
            vertices=list(self.vertices),
            faces=[list(f) for f in self.faces],
            edges=list(self.edges),
            color=self.color,
            material_name=self.material_name,
            opacity=self.opacity,
            face_materials=list(self.face_materials),
            face_colors=list(self.face_colors),
            face_opacities=list(self.face_opacities),
            ifc_class=self.ifc_class,
            name=self.name,
        )

    def transformed(
        self,
        offset: Vec3 = Vec3(),
        rot_z_deg: float = 0.0,
        scale: Vec3 = Vec3(1.0, 1.0, 1.0),
    ) -> MeshData:
        rad = math.radians(rot_z_deg)
        c, s = math.cos(rad), math.sin(rad)
        new_verts: List[Tuple[float, float, float]] = []
        for vx, vy, vz in self.vertices:
            sx, sy, sz = vx * scale.x, vy * scale.y, vz * scale.z
            rx = sx * c - sy * s
            ry = sx * s + sy * c
            new_verts.append((rx + offset.x, ry + offset.y, sz + offset.z))
        out = self.copy()
        out.vertices = new_verts
        # If reflection occurred (negative determinant), flip face winding to stay outward CCW
        if (scale.x * scale.y * scale.z) < 0:
            out.faces = [list(reversed(f)) for f in out.faces]
        return out

    @staticmethod
    def merge(meshes: List[MeshData], name: str = "MergedMesh") -> MeshData:
        result = MeshData(name=name)
        for m in meshes:
            if not isinstance(m, MeshData):
                continue
            v_offset = len(result.vertices)
            result.vertices.extend(m.vertices)
            for f_idx, f in enumerate(m.faces):
                result.faces.append([idx + v_offset for idx in f])
                mat = m.face_materials[f_idx] if f_idx < len(m.face_materials) else m.material_name
                col = m.face_colors[f_idx] if f_idx < len(m.face_colors) else m.color
                op = m.face_opacities[f_idx] if f_idx < len(m.face_opacities) else m.opacity
                result.face_materials.append(mat)
                result.face_colors.append(col)
                result.face_opacities.append(op)
            for e0, e1 in m.edges:
                result.edges.append((e0 + v_offset, e1 + v_offset))
            if m.color and not result.color:
                result.color = m.color
            if m.material_name and not result.material_name:
                result.material_name = m.material_name
            if m.opacity is not None and result.opacity is None:
                result.opacity = m.opacity
            if m.ifc_class and not result.ifc_class:
                result.ifc_class = m.ifc_class
        return result
        return result

    @staticmethod
    def create_box(origin: Vec3, dx: float, dy: float, dz: float) -> MeshData:
        """Creates a watertight 6-face rectangular solid with outward CCW normals."""
        x0, y0, z0 = origin.x, origin.y, origin.z
        x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
        if x0 > x1: x0, x1 = x1, x0
        if y0 > y1: y0, y1 = y1, y0
        if z0 > z1: z0, z1 = z1, z0

        verts = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),  # 0..3 bottom
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),  # 4..7 top
        ]
        faces = [
            [0, 3, 2, 1],  # Bottom (-Z)
            [4, 5, 6, 7],  # Top (+Z)
            [0, 1, 5, 4],  # Front (-Y)
            [1, 2, 6, 5],  # Right (+X)
            [2, 3, 7, 6],  # Back (+Y)
            [3, 0, 4, 7],  # Left (-X)
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        return MeshData(vertices=verts, faces=faces, edges=edges, name="Box")

    @staticmethod
    def create_cylinder(center: Vec3, radius: float, height: float, segments: int = 24) -> MeshData:
        """Creates a watertight n-gon prism cylinder with outward CCW normals."""
        segments = max(3, int(segments))
        radius = max(1e-4, float(radius))
        z0 = center.z
        z1 = center.z + height
        if z0 > z1:
            z0, z1 = z1, z0

        verts: List[Tuple[float, float, float]] = []
        for z in (z0, z1):
            for i in range(segments):
                ang = 2.0 * math.pi * i / segments
                verts.append((
                    center.x + radius * math.cos(ang),
                    center.y + radius * math.sin(ang),
                    z,
                ))

        faces: List[List[int]] = []
        # Bottom cap (-Z): reversed for outward normal pointing down
        faces.append(list(reversed(range(0, segments))))
        # Top cap (+Z): CCW looking from above
        faces.append(list(range(segments, 2 * segments)))
        # Side quads
        for i in range(segments):
            nxt = (i + 1) % segments
            faces.append([i, nxt, segments + nxt, segments + i])

        edges: List[Tuple[int, int]] = []
        for i in range(segments):
            nxt = (i + 1) % segments
            edges.append((i, nxt))
            edges.append((segments + i, segments + nxt))
            edges.append((i, segments + i))

        return MeshData(vertices=verts, faces=faces, edges=edges, name="Cylinder")

    @staticmethod
    def create_sphere(
        center: Vec3 = Vec3(0, 0, 0),
        radius: float = 1.0,
        rings: int = 16,
        segments: int = 32,
    ) -> MeshData:
        """Creates a watertight UV sphere with shared vertices and outward CCW normals."""
        rings = max(3, int(rings))
        segments = max(4, int(segments))
        r = max(1e-4, float(radius))
        c = center or Vec3()

        verts: List[Tuple[float, float, float]] = []
        # North pole: index 0
        verts.append((c.x, c.y, c.z + r))

        # Intermediate rings
        for i in range(1, rings):
            phi = math.pi * i / rings
            sin_phi = math.sin(phi)
            cos_phi = math.cos(phi)
            z = c.z + r * cos_phi
            for j in range(segments):
                theta = 2.0 * math.pi * j / segments
                x = c.x + r * sin_phi * math.cos(theta)
                y = c.y + r * sin_phi * math.sin(theta)
                verts.append((x, y, z))

        # South pole: last index
        south_pole_idx = len(verts)
        verts.append((c.x, c.y, c.z - r))

        faces: List[List[int]] = []
        edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            if a > b:
                a, b = b, a
            edges_set.add((a, b))

        # North pole fan
        for j in range(segments):
            nxt_j = (j + 1) % segments
            v1 = 1 + j
            v2 = 1 + nxt_j
            faces.append([0, v1, v2])
            _add_edge(0, v1)
            _add_edge(v1, v2)
            _add_edge(v2, 0)

        # Middle quads
        for i in range(rings - 2):
            ring1 = 1 + i * segments
            ring2 = 1 + (i + 1) * segments
            for j in range(segments):
                nxt_j = (j + 1) % segments
                v00 = ring1 + j
                v01 = ring1 + nxt_j
                v10 = ring2 + j
                v11 = ring2 + nxt_j
                faces.append([v00, v10, v11, v01])
                _add_edge(v00, v10)
                _add_edge(v10, v11)
                _add_edge(v11, v01)
                _add_edge(v01, v00)

        # South pole fan
        last_ring = 1 + (rings - 2) * segments
        for j in range(segments):
            nxt_j = (j + 1) % segments
            v1 = last_ring + j
            v2 = last_ring + nxt_j
            faces.append([south_pole_idx, v2, v1])
            _add_edge(south_pole_idx, v2)
            _add_edge(v2, v1)
            _add_edge(v1, south_pole_idx)

        return MeshData(vertices=verts, faces=faces, edges=list(edges_set), name="Sphere")

    @staticmethod
    def extrude_curve(curve: CurveData, height: float, cap: bool = True) -> MeshData:
        """Extrudes a 2D/3D CurveData along Z by `height`."""
        pts = curve.points
        if len(pts) < 2 or abs(height) < 1e-6:
            return MeshData()
        n = len(pts)
        dz = float(height)
        verts = [p.to_tuple() for p in pts] + [(p.x, p.y, p.z + dz) for p in pts]
        faces: List[List[int]] = []

        # Ensure 2D signed area is positive (CCW in XY) when extruding +Z
        area2 = 0.0
        for i in range(n):
            p1, p2 = pts[i], pts[(i + 1) % n]
            area2 += (p1.x * p2.y - p2.x * p1.y)
        flip = (area2 < 0) ^ (dz < 0)

        seg_count = n if curve.closed else n - 1
        for i in range(seg_count):
            nxt = (i + 1) % n
            quad = [i, nxt, n + nxt, n + i]
            faces.append(list(reversed(quad)) if flip else quad)

        if curve.closed and cap and n >= 3:
            bot = list(range(0, n))
            top = list(range(n, 2 * n))
            if not flip:
                bot.reverse()
            else:
                top.reverse()
            faces.insert(0, bot)
            faces.append(top)

        edges: List[Tuple[int, int]] = []
        for i in range(seg_count):
            nxt = (i + 1) % n
            edges.append((i, nxt))
            edges.append((n + i, n + nxt))
            edges.append((i, n + i))
        if not curve.closed:
            edges.append((n - 1, 2 * n - 1))

        return MeshData(vertices=verts, faces=faces, edges=edges, name="Extrusion")

    @staticmethod
    def create_from_points(
        pts: List[Any],
        u_count: int = 10,
        v_count: int = 0,
        closed_u: bool = False,
        closed_v: bool = False,
        swap_uv: bool = False,
        triangulate: bool = False,
        flip_normals: bool = False,
        name: str = "MeshFromPoints",
    ) -> MeshData:
        """Constructs a 3D quad or triangulated mesh surface from a structured grid of points."""
        flat_pts: List[Tuple[float, float, float]] = []
        u_override: Optional[int] = None
        v_override: Optional[int] = None

        if pts and isinstance(pts, (list, tuple)) and len(pts) > 0 and isinstance(pts[0], (list, tuple)):
            if len(pts[0]) > 0 and (isinstance(pts[0][0], (Vec3, tuple, list)) or (hasattr(pts[0][0], "x") and hasattr(pts[0][0], "y"))):
                v_override = len(pts)     # Number of rows (V)
                u_override = len(pts[0])  # Number of columns (U)
                for row in pts:
                    for p in row:
                        if isinstance(p, Vec3):
                            flat_pts.append((p.x, p.y, p.z))
                        elif isinstance(p, (tuple, list)) and len(p) >= 3:
                            flat_pts.append((float(p[0]), float(p[1]), float(p[2])))
                        elif hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                            flat_pts.append((float(p.x), float(p.y), float(p.z)))

        if not flat_pts:
            for p in pts:
                if isinstance(p, Vec3):
                    flat_pts.append((p.x, p.y, p.z))
                elif isinstance(p, (tuple, list)) and len(p) >= 3:
                    flat_pts.append((float(p[0]), float(p[1]), float(p[2])))
                elif hasattr(p, "x") and hasattr(p, "y") and hasattr(p, "z"):
                    flat_pts.append((float(p.x), float(p.y), float(p.z)))

        total = len(flat_pts)
        if total < 4:
            return MeshData(name=name)

        final_u = u_override if u_override is not None else max(2, int(u_count))
        final_v = v_override if v_override is not None else int(v_count)
        if final_v <= 0:
            final_v = max(2, total // final_u)

        if total < final_u * final_v:
            return MeshData(name=name)

        # Standard row-major indexing: row is v (0 to final_v-1), col is u (0 to final_u-1).
        # point (u, v) is at v * final_u + u
        def get_idx(u_idx: int, v_idx: int) -> int:
            if swap_uv:
                return u_idx * final_v + v_idx
            return v_idx * final_u + u_idx

        u_cells = final_u if closed_u else final_u - 1
        v_cells = final_v if closed_v else final_v - 1
        faces: List[List[int]] = []
        edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            edges_set.add((min(a, b), max(a, b)))

        for u in range(u_cells):
            u_next = (u + 1) % final_u
            for v in range(v_cells):
                v_next = (v + 1) % final_v
                i00 = get_idx(u, v)
                i10 = get_idx(u_next, v)
                i11 = get_idx(u_next, v_next)
                i01 = get_idx(u, v_next)

                if triangulate:
                    if flip_normals:
                        faces.append([i00, i11, i10])
                        faces.append([i00, i01, i11])
                    else:
                        faces.append([i00, i10, i11])
                        faces.append([i00, i11, i01])
                    _add_edge(i00, i10)
                    _add_edge(i10, i11)
                    _add_edge(i11, i00)
                    _add_edge(i11, i01)
                    _add_edge(i01, i00)
                else:
                    if flip_normals:
                        faces.append([i00, i01, i11, i10])
                    else:
                        faces.append([i00, i10, i11, i01])
                    _add_edge(i00, i10)
                    _add_edge(i10, i11)
                    _add_edge(i11, i01)
                    _add_edge(i01, i00)

        return MeshData(
            vertices=flat_pts[:final_u * final_v],
            faces=faces,
            edges=list(edges_set),
            name=name,
        )


def coerce_value(val: Any, target: SocketType) -> Any:
    """Safely casts incoming socket values to the expected SocketType."""
    if val is None or target == SocketType.ANY:
        return val
    if isinstance(val, list):
        return [coerce_value(v, target) for v in val]
    try:
        if target == SocketType.FLOAT:
            return float(val)
        if target == SocketType.INT:
            return int(round(float(val)))
        if target == SocketType.BOOL:
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "on")
            return bool(val)
        if target == SocketType.STRING:
            return str(val)
        if target == SocketType.VEC3:
            if isinstance(val, Vec3):
                return val
            if isinstance(val, dict):
                return Vec3(float(val.get("x", 0.0)), float(val.get("y", 0.0)), float(val.get("z", 0.0)))
            if isinstance(val, (tuple, list)) and len(val) >= 3:
                return Vec3(float(val[0]), float(val[1]), float(val[2]))
            if isinstance(val, (int, float)):
                return Vec3(float(val), float(val), float(val))
        if target == SocketType.CURVE:
            if isinstance(val, CurveData):
                return val
        if target == SocketType.MESH:
            if isinstance(val, MeshData):
                return val
    except (ValueError, TypeError):
        pass
    return val
