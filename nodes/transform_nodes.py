# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric Geometry Transformation, Extrusion, Revolve, and Array Nodes."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node, NODE_REGISTRY
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3, extract_plane_frame
    from node_base import BaseNode, InputSpec, OutputSpec, register_node, NODE_REGISTRY


# ============================================================================
# 1. Extrude Solid Node
# ============================================================================
@register_node
class ExtrudeSolidNode(BaseNode):
    type_id = "solid.extrude"
    title = "Extrude Curve"
    category = "3D Solids"
    description = "Extrudes any 2D closed curve or polygon into a 3D watertight solid with capped ends."
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("curve", "Curve / Face", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("height", "Height (Z)", SocketType.FLOAT, default=3.0, step=0.5),
        InputSpec("capped", "Cap Ends", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("solid", "Solid Mesh", SocketType.MESH),
    ]

    def compute(self, curve: Any, height: float, capped: bool) -> Dict[str, Any]:
        if isinstance(curve, MeshData) or (isinstance(curve, dict) and ("outer" in curve or "faces" in curve)):
            mesh = MeshData.extrude_face(curve, float(height), cap=bool(capped))
            return {"solid": mesh}
        if not isinstance(curve, CurveData) or not curve.points:
            curve = CurveData(
                points=[Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(4, 3, 0), Vec3(0, 3, 0)],
                closed=True,
            )
        mesh = MeshData.extrude_curve(curve, float(height), cap=bool(capped))
        return {"solid": mesh}


# ============================================================================
# 1b. Extrude Face Node
# ============================================================================
@register_node
class ExtrudeFaceNode(BaseNode):
    type_id = "solid.extrude_face"
    title = "Extrude Face"
    category = "3D Solids"
    description = "Extrudes any 2D planar face, surface, or annular frame (including holes) into a watertight 3D solid with capped ends."
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("face", "Face / Surface", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=3.0, step=0.5),
        InputSpec("capped", "Cap Ends", SocketType.BOOL, default=True),
        InputSpec("direction", "Extrusion Vector", SocketType.VEC3, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("solid", "Solid Mesh", SocketType.MESH),
        OutputSpec("outer", "Outer Perimeter", SocketType.CURVE),
        OutputSpec("holes", "Holes", SocketType.ANY),
    ]

    def compute(self, face: Any = None, height: float = 3.0, capped: bool = True, direction: Any = None) -> Dict[str, Any]:
        mesh = MeshData.extrude_face(face, float(height), cap=bool(capped), direction=direction)
        outer_pts = getattr(mesh, "outer", None) or []
        outer_c = CurveData(points=[Vec3(p[0], p[1], p[2]) for p in outer_pts], closed=True) if outer_pts else CurveData()
        holes_pts = getattr(mesh, "holes", None) or []
        holes_c = [CurveData(points=[Vec3(p[0], p[1], p[2]) for p in h], closed=True) for h in holes_pts]
        return {
            "solid": mesh,
            "mesh": mesh,
            "outer": outer_c,
            "holes": holes_c,
        }


# ============================================================================
# 2. Revolve Solid Node
# ============================================================================
@register_node
class RevolveSolidNode(BaseNode):
    type_id = "solid.revolve"
    title = "Revolve Curve"
    category = "3D Solids"
    description = "Revolves a 2D profile curve around the Z axis into a 3D solid."
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("curve", "Profile Curve", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("angle", "Angle (°)", SocketType.FLOAT, default=360.0, min_val=10.0, max_val=360.0, step=15.0),
        InputSpec("segments", "Segments", SocketType.INT, default=32, min_val=6, max_val=128, step=2),
    ]
    outputs = [
        OutputSpec("solid", "Revolved Solid", SocketType.MESH),
    ]

    def compute(self, curve: Any, angle: float, segments: int) -> Dict[str, Any]:
        pts: List[Vec3] = []
        if isinstance(curve, CurveData) and curve.points:
            pts = curve.points
        else:
            # Default: tapered column profile
            pts = [Vec3(0.6, 0.0, 0.0), Vec3(0.5, 0.0, 1.0), Vec3(0.4, 0.0, 3.0), Vec3(0.7, 0.0, 3.5)]

        n_pts = len(pts)
        n_segs = max(6, int(segments))
        tot_rad = math.radians(min(360.0, max(10.0, float(angle))))
        is_full = abs(tot_rad - 2.0 * math.pi) < 1e-4

        verts: List[Tuple[float, float, float]] = []
        # Generate vertices by rings
        num_rings = n_segs if is_full else n_segs + 1
        for s in range(num_rings):
            ang = tot_rad * s / n_segs
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            for p in pts:
                # Radial distance in XY plane
                r = math.hypot(p.x, p.y)
                verts.append((r * cos_a, r * sin_a, p.z))

        faces: List[List[int]] = []
        edges: List[Tuple[int, int]] = []

        for s in range(n_segs):
            s_nxt = (s + 1) % num_rings
            for i in range(n_pts - 1):
                p0 = s * n_pts + i
                p1 = s * n_pts + i + 1
                p2 = s_nxt * n_pts + i + 1
                p3 = s_nxt * n_pts + i
                faces.append([p0, p3, p2, p1])
                edges.append((p0, p1))
                edges.append((p0, p3))

        mesh = MeshData(vertices=verts, faces=faces, edges=edges, name="RevolvedSolid")
        return {"solid": mesh}


# ============================================================================
# 3. Transform Move Node
# ============================================================================
@register_node
class TransformMoveNode(BaseNode):
    type_id = "xform.move"
    title = "Move / Translate"
    category = "Transforms"
    description = "Moves 3D geometry or points by translation vector (dX, dY, dZ)."
    header_color = (230, 126, 34)

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("translation", "Vector", SocketType.VEC3, default=Vec3(0, 0, 1.0)),
    ]
    outputs = [
        OutputSpec("result", "Moved", SocketType.ANY),
    ]

    def compute(self, geometry: Any, translation: Vec3) -> Dict[str, Any]:
        t = translation or Vec3()
        if isinstance(geometry, MeshData):
            return {"result": geometry.transformed(offset=t)}
        if isinstance(geometry, CurveData):
            return {"result": geometry.transformed(offset=t)}
        if isinstance(geometry, Vec3):
            return {"result": geometry + t}
        if isinstance(geometry, list):
            out = []
            for item in geometry:
                if isinstance(item, MeshData):
                    out.append(item.transformed(offset=t))
                elif isinstance(item, CurveData):
                    out.append(item.transformed(offset=t))
                elif isinstance(item, Vec3):
                    out.append(item + t)
                else:
                    out.append(item)
            return {"result": out}
        return {"result": geometry}


# ============================================================================
# 4. Transform Rotate Node
# ============================================================================
@register_node
class TransformRotateNode(BaseNode):
    type_id = "xform.rotate"
    title = "Rotate (Z Axis)"
    category = "Transforms"
    description = "Rotates 3D geometry around Z axis by angle in degrees."
    header_color = (230, 126, 34)

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("angle", "Angle (°)", SocketType.FLOAT, default=45.0, step=5.0),
    ]
    outputs = [
        OutputSpec("result", "Rotated", SocketType.ANY),
    ]

    def compute(self, geometry: Any, angle: float) -> Dict[str, Any]:
        deg = float(angle)
        if isinstance(geometry, MeshData):
            return {"result": geometry.transformed(rot_z_deg=deg)}
        if isinstance(geometry, CurveData):
            return {"result": geometry.transformed(rot_z_deg=deg)}
        if isinstance(geometry, Vec3):
            rad = math.radians(deg)
            c, s = math.cos(rad), math.sin(rad)
            return {"result": Vec3(geometry.x * c - geometry.y * s, geometry.x * s + geometry.y * c, geometry.z)}
        if isinstance(geometry, list):
            return {"result": [self.compute(item, angle)["result"] for item in geometry]}
        return {"result": geometry}


# ============================================================================
# 5. Linear Array Node
# ============================================================================
@register_node
class LinearArrayNode(BaseNode):
    type_id = "xform.linear_array"
    title = "Linear Array"
    category = "Transforms"
    description = "Duplicates geometry N times along a step vector."
    header_color = (230, 126, 34)

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("count", "Count", SocketType.INT, default=5, min_val=1, max_val=100, step=1),
        InputSpec("step", "Step Vector", SocketType.VEC3, default=Vec3(2.5, 0.0, 0.0)),
    ]
    outputs = [
        OutputSpec("array", "Array", SocketType.ANY),
    ]

    def compute(self, geometry: Any, count: int, step: Vec3) -> Dict[str, Any]:
        n = max(1, int(count))
        s = step or Vec3(1, 0, 0)
        items: List[Any] = []
        for i in range(n):
            offset = Vec3(s.x * i, s.y * i, s.z * i)
            if isinstance(geometry, MeshData):
                items.append(geometry.transformed(offset=offset))
            elif isinstance(geometry, CurveData):
                items.append(geometry.transformed(offset=offset))
            elif isinstance(geometry, Vec3):
                items.append(geometry + offset)
            elif isinstance(geometry, list):
                for sub in geometry:
                    if isinstance(sub, MeshData):
                        items.append(sub.transformed(offset=offset))
                    elif isinstance(sub, CurveData):
                        items.append(sub.transformed(offset=offset))
                    elif isinstance(sub, Vec3):
                        items.append(sub + offset)
            else:
                items.append(geometry)
        return {"array": items}


# ============================================================================
# 6. Polar / Radial Array Node
# ============================================================================
@register_node
class PolarArrayNode(BaseNode):
    type_id = "xform.polar_array"
    title = "Polar Array"
    category = "Transforms"
    description = "Duplicates geometry N times in a circular radial pattern around an origin."
    header_color = (230, 126, 34)

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("count", "Count", SocketType.INT, default=6, min_val=2, max_val=128, step=1),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=4.0, min_val=0.0, step=0.5),
        InputSpec("total_angle", "Total Angle (°)", SocketType.FLOAT, default=360.0, min_val=10.0, max_val=360.0, step=15.0),
    ]
    outputs = [
        OutputSpec("array", "Array", SocketType.ANY),
    ]

    def compute(self, geometry: Any, count: int, radius: float, total_angle: float) -> Dict[str, Any]:
        n = max(2, int(count))
        r = float(radius)
        tot_deg = float(total_angle)
        step_deg = tot_deg / n if abs(tot_deg - 360.0) < 1e-4 else tot_deg / (n - 1)

        items: List[Any] = []
        for i in range(n):
            deg = step_deg * i
            rad = math.radians(deg)
            pos = Vec3(r * math.cos(rad), r * math.sin(rad), 0.0)
            if isinstance(geometry, MeshData):
                items.append(geometry.transformed(offset=pos, rot_z_deg=deg))
            elif isinstance(geometry, CurveData):
                items.append(geometry.transformed(offset=pos, rot_z_deg=deg))
            elif isinstance(geometry, Vec3):
                items.append(Vec3(geometry.x + pos.x, geometry.y + pos.y, geometry.z))
            elif isinstance(geometry, list):
                for sub in geometry:
                    if isinstance(sub, MeshData):
                        items.append(sub.transformed(offset=pos, rot_z_deg=deg))
            else:
                items.append(geometry)
        return {"array": items}


# ============================================================================
# 7. Mesh Join Node
# ============================================================================
@register_node
class MeshJoinNode(BaseNode):
    type_id = "solid.join"
    title = "Join Meshes"
    category = "3D Solids"
    description = "Joins a list of meshes into a single combined watertight mesh."
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("meshes", "Meshes", SocketType.MESH, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("name", "Joined Name", SocketType.STRING, default="Compound_Mesh"),
    ]
    outputs = [
        OutputSpec("mesh", "Joined Mesh", SocketType.MESH),
    ]

    def compute(self, meshes: List[Any], name: str) -> Dict[str, Any]:
        flat: List[MeshData] = []
        for item in meshes:
            if isinstance(item, MeshData):
                flat.append(item)
            elif isinstance(item, list):
                flat.extend([m for m in item if isinstance(m, MeshData)])
        joined = MeshData.merge(flat, name=name or "JoinedMesh")
        return {"mesh": joined}


# ============================================================================
# 8. Sweep Solid Node
# ============================================================================
@register_node
class SweepNode(BaseNode):
    type_id = "solid.sweep"
    title = "Sweep Solid"
    category = "3D Solids"
    description = (
        "Sweeps a 2D/3D profile curve along a rail trajectory path using rotation-minimizing\n"
        "parallel transport frames to produce a smooth watertight solid or tubular surface.\n"
        "Supports angle-bisector mitered corners (Follow Me parity), open or closed profiles and paths,\n"
        "and automatic start and end capping with outward face normals."
    )
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("profile", "Profile Curve", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("rail", "Rail Path", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("capped", "Cap Ends", SocketType.BOOL, default=True),
        InputSpec("miter", "Miter Corners", SocketType.BOOL, default=True),
        InputSpec("flip_z", "Flip Upright", SocketType.BOOL, default=False),
        InputSpec("scale_end", "Scale End", SocketType.FLOAT, default=1.0, min_val=0.01, max_val=10.0, step=0.1),
    ]
    outputs = [
        OutputSpec("solid", "Sweep Solid", SocketType.MESH),
    ]

    @staticmethod
    def _newell_normal(pts: List[Vec3]) -> Vec3:
        if len(pts) < 3:
            return Vec3(0, 0, 1)
        nx, ny, nz = 0.0, 0.0, 0.0
        n = len(pts)
        for i in range(n):
            p0 = pts[i]
            p1 = pts[(i + 1) % n]
            nx += (p0.y - p1.y) * (p0.z + p1.z)
            ny += (p0.z - p1.z) * (p0.x + p1.x)
            nz += (p0.x - p1.x) * (p0.y + p1.y)
        v = Vec3(nx, ny, nz)
        return v.normalized() if v.length() > 1e-6 else Vec3(0, 0, 1)

    def _sweep_single_rail(
        self,
        profile: CurveData,
        rail: CurveData,
        capped: bool = True,
        miter: bool = True,
        flip_z: bool = False,
        scale_end: float = 1.0,
    ) -> MeshData:
        pts_rail = list(rail.points)
        if len(pts_rail) < 2:
            return MeshData(name="Sweep_Solid")

        # Filter out consecutive duplicate points along rail
        clean_rail: List[Vec3] = [pts_rail[0]]
        for p in pts_rail[1:]:
            if p.distance_to(clean_rail[-1]) > 1e-5:
                clean_rail.append(p)
        pts_rail = clean_rail
        k_count = len(pts_rail)
        if k_count < 2:
            return MeshData(name="Sweep_Solid")

        # Check if rail is closed
        is_rail_closed = bool(getattr(rail, "closed", False))
        if k_count > 2 and pts_rail[0].distance_to(pts_rail[-1]) < 0.01:
            is_rail_closed = True
            pts_rail = pts_rail[:-1]
            k_count = len(pts_rail)

        # Clean profile points
        prof_pts = list(profile.points)
        clean_prof: List[Vec3] = [prof_pts[0]]
        for p in prof_pts[1:]:
            if p.distance_to(clean_prof[-1]) > 1e-5:
                clean_prof.append(p)
        if profile.closed and len(clean_prof) > 2 and clean_prof[0].distance_to(clean_prof[-1]) < 0.01:
            clean_prof = clean_prof[:-1]
        prof_pts = clean_prof
        m_count = len(prof_pts)
        if m_count < 2:
            return MeshData(name="Sweep_Solid")

        # 1. Segment tangents along rail
        seg_tangents: List[Vec3] = []
        seg_count = k_count if is_rail_closed else k_count - 1
        for i in range(seg_count):
            nxt = (i + 1) % k_count
            t = (pts_rail[nxt] - pts_rail[i]).normalized()
            seg_tangents.append(t if t.length() > 1e-6 else Vec3(1, 0, 0))

        t0 = seg_tangents[0]

        # 2. Check profile orientation (3D oriented near rail start vs 2D local)
        c_prof = Vec3(
            sum(p.x for p in prof_pts) / m_count,
            sum(p.y for p in prof_pts) / m_count,
            sum(p.z for p in prof_pts) / m_count,
        )
        n_prof = self._newell_normal(prof_pts)
        p0 = pts_rail[0]
        min_dist_to_p0 = min(p.distance_to(p0) for p in prof_pts)

        is_3d_oriented = (min_dist_to_p0 < 0.5) and (abs(n_prof.dot(t0)) > 0.7)

        if is_3d_oriented:
            closest_p = min(prof_pts, key=lambda pt: pt.distance_to(p0))
            anchor = p0 if closest_p.distance_to(p0) < 0.2 else closest_p
            offsets_0 = [p - anchor for p in prof_pts]
        else:
            # 2D parametric profile in XY plane - build natural upright right-handed frame
            if abs(t0.z) < 0.99:
                up = Vec3(0, 0, 1)
                prof_x0 = up.cross(t0).normalized()       # Horizontal cross-width
                prof_y0 = t0.cross(prof_x0).normalized()  # Upright vertical height
            else:
                guide = Vec3(0, 1, 0) if t0.z > 0 else Vec3(0, -1, 0)
                prof_x0 = guide.cross(t0).normalized()
                prof_y0 = t0.cross(prof_x0).normalized()
            y_mult = -1.0 if flip_z else 1.0
            offsets_0 = [prof_x0 * p.x + prof_y0 * (p.y * y_mult) + t0 * p.z for p in prof_pts]

        # 3. Parallel transport & miter along rail
        # Corner 0 miter when rail is closed (Follow Me parity: seamless closed loop)
        if miter and is_rail_closed and len(seg_tangents) >= 2:
            t_in_0 = seg_tangents[-1]
            t_out_0 = seg_tangents[0]
            t_bisect_0 = (t_in_0 + t_out_0).normalized()
            denom_0 = t_out_0.dot(t_bisect_0)
            if denom_0 > 1e-4:
                denom_0 = max(0.25, denom_0)  # Clamp miter spike on sharp hairpin turns
                mitered_0 = [off - t_out_0 * (off.dot(t_bisect_0) / denom_0) for off in offsets_0]
                station_offsets: List[List[Vec3]] = [mitered_0]
            else:
                station_offsets = [offsets_0]
        else:
            station_offsets = [offsets_0]

        curr_offsets = list(offsets_0)

        for i in range(1, k_count):
            t_prev = seg_tangents[i - 1]
            t_curr = seg_tangents[i if i < len(seg_tangents) else -1]
            p_prev = pts_rail[i - 1]
            p_curr = pts_rail[i]

            # Double reflection from segment i-1 to segment i
            v1 = p_curr - p_prev
            c1 = v1.dot(v1)
            next_offsets: List[Vec3] = []
            for off in curr_offsets:
                if c1 > 1e-12:
                    r_l_t = t_prev - v1 * ((2.0 / c1) * v1.dot(t_prev))
                    r_l_n = off - v1 * ((2.0 / c1) * v1.dot(off))
                    v2 = t_curr - r_l_t
                    c2 = v2.dot(v2)
                    if c2 > 1e-12:
                        off_next = r_l_n - v2 * ((2.0 / c2) * v2.dot(r_l_n))
                    else:
                        off_next = r_l_n
                else:
                    off_next = off
                next_offsets.append(off_next)
            curr_offsets = next_offsets

            # Apply angle-bisector miter at corner (Follow Me parity)
            if miter and (i < k_count - 1 or is_rail_closed):
                t_in = seg_tangents[i - 1]
                t_out = seg_tangents[i if i < len(seg_tangents) else -1]
                t_bisect = (t_in + t_out).normalized()
                denom = t_out.dot(t_bisect)
                if denom > 1e-4:
                    denom = max(0.25, denom)  # Clamp miter spike on sharp hairpin turns
                    mitered = [off - t_out * (off.dot(t_bisect) / denom) for off in curr_offsets]
                    station_offsets.append(mitered)
                else:
                    station_offsets.append(curr_offsets)
            else:
                station_offsets.append(curr_offsets)

        # 4. Generate mesh vertices
        mesh_verts: List[Tuple[float, float, float]] = []
        s_end = float(scale_end)
        for i in range(k_count):
            origin = pts_rail[i]
            scale = 1.0 if is_rail_closed else (1.0 + (s_end - 1.0) * (i / float(k_count - 1)))
            for off in station_offsets[i]:
                pos = origin + off * scale
                mesh_verts.append((pos.x, pos.y, pos.z))

        # 5. Outward CCW Quad faces connecting consecutive stations
        mesh_faces: List[List[int]] = []
        mesh_edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            mesh_edges_set.add((min(a, b), max(a, b)))

        station_rings = k_count if is_rail_closed else k_count - 1
        prof_segs = m_count if profile.closed else m_count - 1

        for i in range(station_rings):
            nxt_i = (i + 1) % k_count
            base_a = i * m_count
            base_b = nxt_i * m_count
            for j in range(prof_segs):
                nxt_j = (j + 1) % m_count
                i00 = base_a + j
                i01 = base_a + nxt_j
                i11 = base_b + nxt_j
                i10 = base_b + j
                # Standard CCW outward face (adjust winding if upright flipped)
                if flip_z:
                    mesh_faces.append([i00, i10, i11, i01])
                else:
                    mesh_faces.append([i00, i01, i11, i10])
                _add_edge(i00, i01)
                _add_edge(i01, i11)
                _add_edge(i11, i10)
                _add_edge(i10, i00)

        # 6. End Capping (only for open rails with closed profile)
        if capped and profile.closed and not is_rail_closed and m_count >= 3:
            # Start cap (must face backward: -t0)
            c0_pts = [Vec3(*mesh_verts[j]) for j in range(m_count)]
            n_cap0 = self._newell_normal(c0_pts)
            if n_cap0.dot(t0) > 0:
                start_cap = list(reversed(range(0, m_count)))
            else:
                start_cap = list(range(0, m_count))

            # End cap (must face forward: +t_end)
            t_end = seg_tangents[-1]
            end_base = (k_count - 1) * m_count
            c_end_pts = [Vec3(*mesh_verts[end_base + j]) for j in range(m_count)]
            n_cap_end = self._newell_normal(c_end_pts)
            if n_cap_end.dot(t_end) < 0:
                end_cap = list(reversed(range(end_base, end_base + m_count)))
            else:
                end_cap = list(range(end_base, end_base + m_count))

            mesh_faces.insert(0, start_cap)
            mesh_faces.append(end_cap)

        return MeshData(
            vertices=mesh_verts,
            faces=mesh_faces,
            edges=list(mesh_edges_set),
            name="Sweep_Solid",
        )

    def compute(
        self,
        profile: Any = None,
        rail: Any = None,
        capped: bool = True,
        miter: bool = True,
        flip_z: bool = False,
        scale_end: float = 1.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        # Handle list unwrapping if profile was passed as single-element list
        if isinstance(profile, (list, tuple)) and profile:
            profile = profile[0]

        # Fallback profile: 0.3m radius 12-segment circle
        if not isinstance(profile, CurveData) or len(profile.points) < 3:
            prof_pts: List[Vec3] = []
            for seg in range(12):
                ang = seg * 2.0 * math.pi / 12.0
                prof_pts.append(Vec3(0.3 * math.cos(ang), 0.3 * math.sin(ang), 0.0))
            profile = CurveData(points=prof_pts, closed=True)

        # Collect rail curve(s)
        rail_curves: List[CurveData] = []
        if isinstance(rail, (list, tuple)):
            for r in rail:
                if isinstance(r, CurveData) and len(r.points) >= 2:
                    rail_curves.append(r)
        elif isinstance(rail, CurveData) and len(rail.points) >= 2:
            rail_curves.append(rail)

        # Fallback rail: curved trajectory
        if not rail_curves:
            rail_pts: List[Vec3] = [
                Vec3(0.0, 0.0, 0.0),
                Vec3(1.5, 0.5, 1.0),
                Vec3(3.0, 1.8, 2.5),
                Vec3(4.5, 1.2, 4.0),
                Vec3(6.0, 0.0, 5.0),
            ]
            rail_curves = [CurveData(points=rail_pts, closed=False)]

        solids: List[MeshData] = []
        for rc in rail_curves:
            m = self._sweep_single_rail(
                profile=profile,
                rail=rc,
                capped=capped,
                miter=miter,
                flip_z=flip_z,
                scale_end=scale_end,
            )
            if m.vertices or m.faces:
                solids.append(m)

        if len(solids) > 1:
            combined = MeshData.merge(solids, name="Sweep_Solid")
            return {"solid": combined}
        elif len(solids) == 1:
            return {"solid": solids[0]}
        else:
            return {"solid": MeshData(name="Sweep_Solid")}


# ============================================================================
# 9. Pipe Solid Node
# ============================================================================
@register_node
class PipeNode(BaseNode):
    type_id = "solid.pipe"
    title = "Pipe Solid"
    category = "3D Solids"
    description = (
        "Creates a watertight cylindrical pipe or hollow tube solid along rail curve(s).\n"
        "Uses rotation-minimizing parallel transport frames to avoid twisting.\n"
        "Supports radius, wall thickness, radial segments, and capping options."
    )
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("curve", "Curve / Rail", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=0.10, min_val=0.001, max_val=10.0, step=0.01, decimals=3),
        InputSpec("thickness", "Thickness (m)", SocketType.FLOAT, default=0.0, min_val=0.0, max_val=5.0, step=0.005, decimals=3),
        InputSpec("segments", "Segments", SocketType.INT, default=16, min_val=3, max_val=64, step=1),
        InputSpec("capped", "Cap Ends", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("solid", "Pipe Solid", SocketType.MESH),
        OutputSpec("centerline", "Centerline", SocketType.CURVE),
    ]

    def get_card_badge_text(self) -> Optional[str]:
        r = float(self.param_values.get("radius", 0.1))
        th = float(self.param_values.get("thickness", 0.0))
        if 0.0 < th < r:
            return f"R: {r:.2f}m (Wall: {th:.2f}m)"
        return f"R: {r:.2f}m"

    def compute(
        self,
        curve: Any = None,
        radius: float = 0.10,
        thickness: float = 0.0,
        segments: int = 16,
        capped: bool = True,
    ) -> Dict[str, Any]:
        # Fallback trajectory if unwired
        if not isinstance(curve, CurveData) or len(curve.points) < 2:
            rail_pts = [
                Vec3(0.0, 0.0, 0.0),
                Vec3(0.0, 0.0, 1.5),
                Vec3(1.0, 0.0, 2.5),
                Vec3(2.5, 0.0, 2.5),
            ]
            curve = CurveData(points=rail_pts, closed=False)

        pts = curve.points
        if len(pts) < 2:
            return {"solid": MeshData(name="Pipe_Solid"), "centerline": curve}

        # Filter out duplicate consecutive points
        clean_pts = [pts[0]]
        for p in pts[1:]:
            if (p - clean_pts[-1]).length() > 1e-6:
                clean_pts.append(p)
        if len(clean_pts) < 2:
            return {"solid": MeshData(name="Pipe_Solid"), "centerline": curve}

        n = len(clean_pts)
        is_closed = curve.closed or (clean_pts[0].distance_to(clean_pts[-1]) < 1e-4 and n >= 3)
        if is_closed and clean_pts[0].distance_to(clean_pts[-1]) < 1e-4:
            clean_pts = clean_pts[:-1]
            n = len(clean_pts)
            if n < 3:
                return {"solid": MeshData(name="Pipe_Solid"), "centerline": curve}

        # 1. Compute tangents along the curve
        tangents: List[Vec3] = []
        for i in range(n):
            if is_closed:
                p_prev = clean_pts[(i - 1) % n]
                p_next = clean_pts[(i + 1) % n]
                t = (p_next - p_prev).normalized()
            else:
                if i == 0:
                    t = (clean_pts[1] - clean_pts[0]).normalized()
                elif i == n - 1:
                    t = (clean_pts[n - 1] - clean_pts[n - 2]).normalized()
                else:
                    t = (clean_pts[i + 1] - clean_pts[i - 1]).normalized()
            tangents.append(t if t.length() > 1e-6 else Vec3(0, 0, 1))

        # 2. Parallel Transport Frame (Double Reflection Method / Wang et al.)
        normals: List[Vec3] = []
        binormals: List[Vec3] = []

        t0 = tangents[0]
        guide = Vec3(0, 0, 1) if abs(t0.z) < 0.9 else Vec3(1, 0, 0)
        n0 = t0.cross(guide).normalized()
        b0 = t0.cross(n0).normalized()
        normals.append(n0)
        binormals.append(b0)

        for i in range(1, n):
            p_prev = clean_pts[i - 1]
            p_curr = clean_pts[i]
            v1 = p_curr - p_prev
            c1 = v1.dot(v1)

            t_prev = tangents[i - 1]
            t_curr = tangents[i]
            n_prev = normals[i - 1]

            if c1 > 1e-12:
                r_l_t = t_prev - v1 * ((2.0 / c1) * v1.dot(t_prev))
                r_l_n = n_prev - v1 * ((2.0 / c1) * v1.dot(n_prev))
                v2 = t_curr - r_l_t
                c2 = v2.dot(v2)
                if c2 > 1e-12:
                    n_curr = (r_l_n - v2 * ((2.0 / c2) * v2.dot(r_l_n))).normalized()
                else:
                    n_curr = r_l_n.normalized()
            else:
                n_curr = n_prev

            b_curr = t_curr.cross(n_curr).normalized()
            normals.append(n_curr)
            binormals.append(b_curr)

        r_out = max(1e-4, float(radius))
        has_wall = 0.0 < float(thickness) < r_out
        r_in = r_out - float(thickness) if has_wall else 0.0
        segs = max(3, int(segments))

        mesh_verts: List[Tuple[float, float, float]] = []
        # Outer rings
        for i in range(n):
            c = clean_pts[i]
            ni, bi = normals[i], binormals[i]
            for j in range(segs):
                ang = 2.0 * math.pi * j / segs
                p = c + ni * (r_out * math.cos(ang)) + bi * (r_out * math.sin(ang))
                mesh_verts.append((p.x, p.y, p.z))

        inner_offset = len(mesh_verts)
        if has_wall:
            for i in range(n):
                c = clean_pts[i]
                ni, bi = normals[i], binormals[i]
                for j in range(segs):
                    ang = 2.0 * math.pi * j / segs
                    p = c + ni * (r_in * math.cos(ang)) + bi * (r_in * math.sin(ang))
                    mesh_verts.append((p.x, p.y, p.z))

        mesh_faces: List[List[int]] = []
        mesh_edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            mesh_edges_set.add((min(a, b), max(a, b)))

        station_count = n if is_closed else n - 1

        # Outer cylinder quads
        for i in range(station_count):
            nxt_i = (i + 1) % n
            base_a = i * segs
            base_b = nxt_i * segs
            for j in range(segs):
                nxt_j = (j + 1) % segs
                i00 = base_a + j
                i01 = base_a + nxt_j
                i11 = base_b + nxt_j
                i10 = base_b + j
                mesh_faces.append([i00, i01, i11, i10])
                _add_edge(i00, i01)
                _add_edge(i01, i11)
                _add_edge(i11, i10)
                _add_edge(i10, i00)

        # Inner cylinder quads (reversed winding so normal points into the void)
        if has_wall:
            for i in range(station_count):
                nxt_i = (i + 1) % n
                base_a = inner_offset + i * segs
                base_b = inner_offset + nxt_i * segs
                for j in range(segs):
                    nxt_j = (j + 1) % segs
                    i00 = base_a + j
                    i01 = base_a + nxt_j
                    i11 = base_b + nxt_j
                    i10 = base_b + j
                    mesh_faces.append([i00, i10, i11, i01])
                    _add_edge(i00, i10)
                    _add_edge(i10, i11)
                    _add_edge(i11, i01)
                    _add_edge(i01, i00)

        # Capping for open curves
        if capped and not is_closed:
            if has_wall:
                # Annular ring caps
                # Start cap (facing backwards: reversed)
                for j in range(segs):
                    nxt_j = (j + 1) % segs
                    o0 = j
                    o1 = nxt_j
                    i0 = inner_offset + j
                    i1 = inner_offset + nxt_j
                    mesh_faces.append([o0, i0, i1, o1])
                    _add_edge(o0, i0)
                    _add_edge(i0, i1)
                    _add_edge(i1, o1)
                    _add_edge(o1, o0)
                # End cap (facing forward)
                end_out = (n - 1) * segs
                end_in = inner_offset + (n - 1) * segs
                for j in range(segs):
                    nxt_j = (j + 1) % segs
                    o0 = end_out + j
                    o1 = end_out + nxt_j
                    i0 = end_in + j
                    i1 = end_in + nxt_j
                    mesh_faces.append([o0, o1, i1, i0])
                    _add_edge(o0, o1)
                    _add_edge(o1, i1)
                    _add_edge(i1, i0)
                    _add_edge(i0, o0)
            else:
                # Solid circular disc caps
                # Start cap (facing backwards: reversed)
                start_cap = list(reversed(range(0, segs)))
                mesh_faces.insert(0, start_cap)
                for j in range(segs):
                    _add_edge(j, (j + 1) % segs)
                # End cap (facing forward)
                end_base = (n - 1) * segs
                end_cap = list(range(end_base, end_base + segs))
                mesh_faces.append(end_cap)
                for j in range(segs):
                    _add_edge(end_base + j, end_base + (j + 1) % segs)

        solid_mesh = MeshData(
            vertices=mesh_verts,
            faces=mesh_faces,
            edges=list(mesh_edges_set),
            name="Pipe_Solid",
            ifc_class="IfcBuildingElementProxy",
        )

        return {"solid": solid_mesh, "centerline": curve}


# ============================================================================
# 10. Flip Normals / Faces Node
# ============================================================================
@register_node
class FlipNormalsNode(BaseNode):
    type_id = "mesh.flip_normals"
    title = "Flip Faces / Normals"
    category = "Transforms"
    description = (
        "Reverses the face winding / normal orientation of a 3D mesh (turning inside-out),\n"
        "or reverses the direction of a curve."
    )
    header_color = (208, 120, 60)

    inputs = [
        InputSpec("geometry", "Geometry / Mesh", SocketType.ANY, default=None, hide_widget=True),
    ]
    outputs = [
        OutputSpec("geometry", "Flipped Geometry", SocketType.ANY),
    ]

    def compute(self, geometry: Any = None) -> Dict[str, Any]:
        if geometry is None:
            return {"geometry": None}

        if isinstance(geometry, MeshData):
            flipped_faces = [list(reversed(f)) for f in geometry.faces]
            flipped_mesh = MeshData(
                vertices=list(geometry.vertices),
                faces=flipped_faces,
                edges=list(geometry.edges),
                name=f"{geometry.name}_Flipped" if geometry.name else "FlippedMesh",
                face_materials=list(geometry.face_materials),
                face_colors=list(geometry.face_colors),
                face_opacities=list(geometry.face_opacities),
                ifc_class=geometry.ifc_class,
            )
            return {"geometry": flipped_mesh}

        if isinstance(geometry, CurveData):
            flipped_curve = CurveData(
                points=list(reversed(geometry.points)),
                closed=geometry.closed,
            )
            return {"geometry": flipped_curve}

        if isinstance(geometry, list):
            out_list = []
            for item in geometry:
                if isinstance(item, MeshData):
                    out_list.append(MeshData(
                        vertices=list(item.vertices),
                        faces=[list(reversed(f)) for f in item.faces],
                        edges=list(item.edges),
                        name=f"{item.name}_Flipped" if item.name else "FlippedMesh",
                        face_materials=list(item.face_materials),
                        face_colors=list(item.face_colors),
                        face_opacities=list(item.face_opacities),
                        ifc_class=item.ifc_class,
                    ))
                elif isinstance(item, CurveData):
                    out_list.append(CurveData(points=list(reversed(item.points)), closed=item.closed))
                else:
                    out_list.append(item)
            return {"geometry": out_list}

        return {"geometry": geometry}


# ============================================================================
# Loft Solid Node
# ============================================================================
@register_node
class LoftNode(BaseNode):
    type_id = "solid.loft"
    title = "Loft"
    category = "3D Solids"
    description = (
        "Create a 3D transitional surface or solid by lofting through a series of section curves or faces.\n"
        "Accepts a list of cross-sections or discrete section inputs (Section A, B, C)."
    )
    header_color = (219, 133, 44)

    inputs = [
        InputSpec("sections", "Sections (List)", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("section_a", "Section A", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("section_b", "Section B", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("section_c", "Section C", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("close_loft", "Close Loft", SocketType.BOOL, default=False),
        InputSpec("cap_ends", "Cap Ends", SocketType.BOOL, default=True),
        InputSpec("rebuild_count", "Sample Count", SocketType.INT, default=32, min_val=4, max_val=256, step=2),
    ]
    outputs = [
        OutputSpec("mesh", "Loft Mesh", SocketType.MESH),
        OutputSpec("curves", "Section Curves", SocketType.ANY),
    ]

    @staticmethod
    def _resample_curve(pts: List[Vec3], count: int, is_closed: bool) -> List[Vec3]:
        n = len(pts)
        if n < 2:
            return [Vec3(p.x, p.y, p.z) for p in pts]
        poly = list(pts)
        if is_closed and (poly[0].distance_to(poly[-1]) > 1e-4):
            poly.append(poly[0])

        cum = [0.0]
        for i in range(len(poly) - 1):
            cum.append(cum[-1] + poly[i].distance_to(poly[i + 1]))
        total_len = cum[-1]
        if total_len < 1e-9:
            return [poly[0]] * count

        resampled: List[Vec3] = []
        if is_closed:
            targets = [i * (total_len / count) for i in range(count)]
        else:
            targets = [i * (total_len / (count - 1)) for i in range(count)]

        idx = 0
        for d in targets:
            while idx < len(cum) - 2 and cum[idx + 1] < d:
                idx += 1
            l0, l1 = cum[idx], cum[idx + 1]
            p0, p1 = poly[idx], poly[idx + 1]
            seg_l = max(1e-9, l1 - l0)
            t = max(0.0, min(1.0, (d - l0) / seg_l))
            resampled.append(Vec3(p0.x + t * (p1.x - p0.x), p0.y + t * (p1.y - p0.y), p0.z + t * (p1.z - p0.z)))
        return resampled

    def compute(
        self,
        sections: Any = None,
        section_a: Any = None,
        section_b: Any = None,
        section_c: Any = None,
        close_loft: bool = False,
        cap_ends: bool = True,
        rebuild_count: int = 32,
    ) -> Dict[str, Any]:
        m_samples = max(4, int(rebuild_count))

        raw_list: List[Any] = []
        if isinstance(sections, (list, tuple)) and sections:
            raw_list.extend(sections)
        else:
            for s in (section_a, section_b, section_c):
                if s is not None:
                    raw_list.append(s)

        curves: List[CurveData] = []
        for item in raw_list:
            if isinstance(item, CurveData) and len(item.points) >= 2:
                curves.append(item.copy())
            elif isinstance(item, MeshData):
                c = item.perimeter_as_curve()
                if len(c.points) >= 2:
                    curves.append(c)
            elif isinstance(item, dict) and "outer" in item:
                outer_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in item.get("outer", [])]
                if len(outer_pts) >= 2:
                    curves.append(CurveData(points=outer_pts, closed=True))
            elif isinstance(item, list) and item:
                pts_list = []
                for p in item:
                    if isinstance(p, Vec3):
                        pts_list.append(p)
                    elif isinstance(p, (list, tuple)) and len(p) >= 3:
                        pts_list.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
                if len(pts_list) >= 2:
                    curves.append(CurveData(points=pts_list, closed=True))

        if len(curves) < 2:
            curves = [
                CurveData(points=[Vec3(3.0 * math.cos(math.pi * 2.0 * i / 16.0), 3.0 * math.sin(math.pi * 2.0 * i / 16.0), 0.0) for i in range(16)], closed=True),
                CurveData(points=[Vec3(4.5 * math.cos(math.pi * 2.0 * i / 16.0), 4.5 * math.sin(math.pi * 2.0 * i / 16.0), 2.5) for i in range(16)], closed=True),
                CurveData(points=[Vec3(2.5 * math.cos(math.pi * 2.0 * i / 16.0), 2.5 * math.sin(math.pi * 2.0 * i / 16.0), 5.0) for i in range(16)], closed=True),
            ]

        k_sections = len(curves)
        is_closed_cross = all(c.closed for c in curves)

        resampled_rings: List[List[Vec3]] = []
        for c in curves:
            ring = self._resample_curve(c.points, m_samples, is_closed_cross)
            resampled_rings.append(ring)

        for j in range(k_sections - 1):
            r_curr = resampled_rings[j]
            r_next = resampled_rings[j + 1]

            best_shift = 0
            best_dist = float("inf")
            best_reversed = False

            for is_rev in (False, True):
                cand = list(reversed(r_next)) if is_rev else r_next
                for shift in range(m_samples if is_closed_cross else 1):
                    d_sum = 0.0
                    for i in range(m_samples):
                        i_shifted = (i + shift) % m_samples
                        d_sum += r_curr[i].distance_to(cand[i_shifted])
                    if d_sum < best_dist:
                        best_dist = d_sum
                        best_shift = shift
                        best_reversed = is_rev

            chosen = list(reversed(r_next)) if best_reversed else r_next
            if is_closed_cross:
                resampled_rings[j + 1] = [chosen[(i + best_shift) % m_samples] for i in range(m_samples)]
            else:
                resampled_rings[j + 1] = chosen

        mesh_verts: List[Tuple[float, float, float]] = []
        mesh_faces: List[List[int]] = []
        mesh_edges: List[Tuple[int, int]] = []

        for ring in resampled_rings:
            for p in ring:
                mesh_verts.append((p.x, p.y, p.z))

        num_layers = k_sections if close_loft else (k_sections - 1)
        for j in range(num_layers):
            j_next = (j + 1) % k_sections
            base_curr = j * m_samples
            base_next = j_next * m_samples

            num_quads = m_samples if is_closed_cross else (m_samples - 1)
            for i in range(num_quads):
                i_next = (i + 1) % m_samples
                v0 = base_curr + i
                v1 = base_curr + i_next
                v2 = base_next + i_next
                v3 = base_next + i

                mesh_faces.append([v0, v1, v2, v3])
                mesh_edges.append((v0, v1))
                mesh_edges.append((v1, v2))
                mesh_edges.append((v2, v3))
                mesh_edges.append((v3, v0))

        if cap_ends and not close_loft and is_closed_cross and k_sections >= 2:
            bottom_face = list(reversed(range(m_samples)))
            mesh_faces.append(bottom_face)
            for i in range(m_samples):
                mesh_edges.append((i, (i + 1) % m_samples))

            top_base = (k_sections - 1) * m_samples
            top_face = [top_base + i for i in range(m_samples)]
            mesh_faces.append(top_face)
            for i in range(m_samples):
                mesh_edges.append((top_base + i, top_base + (i + 1) % m_samples))

        loft_mesh = MeshData(
            vertices=mesh_verts,
            faces=mesh_faces,
            edges=mesh_edges,
            name="LoftSolid",
            material_name="DefaultLoft",
            color=(0.85, 0.70, 0.45),
            face_materials=["DefaultLoft"] * len(mesh_faces),
            face_colors=[(0.85, 0.70, 0.45)] * len(mesh_faces),
            ifc_class="IfcBuildingElementProxy",
        )

        out_curves = [CurveData(points=ring, closed=is_closed_cross) for ring in resampled_rings]

        return {
            "mesh": loft_mesh,
            "curves": out_curves,
        }


# ============================================================================
# 12. Transform Mirror Node
# ============================================================================
@register_node
class TransformMirrorNode(BaseNode):
    type_id = "xform.mirror"
    title = "Mirror"
    category = "Transforms"
    description = (
        "Mirrors 3D geometry or points across a plane (XY, XZ, YZ, or custom plane/origin/normal).\n"
        "Automatically reverses face winding on meshes so surface normals remain outward-pointing.\n"
        "Includes an optional 'Copy' toggle to preserve the original geometry alongside the mirrored copy."
    )
    header_color = (230, 126, 34)
    icon = "transform.mirror.png"

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("plane", "Plane", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("plane_type", "Plane Axis", SocketType.STRING, default="XY", choices=["XY", "XZ", "YZ", "Custom"]),
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("normal", "Normal", SocketType.VEC3, default=Vec3(0, 0, 1), hide_widget=True),
        InputSpec("copy", "Copy", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("result", "Result", SocketType.ANY),
        OutputSpec("mirrored", "Mirrored", SocketType.ANY),
    ]

    def compute(
        self,
        geometry: Any = None,
        plane: Any = None,
        plane_type: str = "XY",
        origin: Any = None,
        normal: Any = None,
        copy: bool = False,
    ) -> Dict[str, Any]:
        # Determine mirror plane origin and unit normal
        if plane is not None:
            p0, _u, _v, n = extract_plane_frame(plane)
        else:
            p0 = origin if isinstance(origin, Vec3) else Vec3(0, 0, 0)
            pt_mode = str(plane_type).strip().upper() if plane_type else "XY"
            if pt_mode == "XY":
                n = Vec3(0, 0, 1)
            elif pt_mode == "XZ":
                n = Vec3(0, 1, 0)
            elif pt_mode == "YZ":
                n = Vec3(1, 0, 0)
            else:  # Custom
                n = normal if isinstance(normal, Vec3) else Vec3(0, 0, 1)

        length = math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z)
        if length < 1e-9:
            n = Vec3(0, 0, 1)
        else:
            n = Vec3(n.x / length, n.y / length, n.z / length)

        def _mirror_point(p: Vec3) -> Vec3:
            diff = p - p0
            dot = diff.x * n.x + diff.y * n.y + diff.z * n.z
            return p - n * (2.0 * dot)

        def _mirror_mesh(mesh: MeshData) -> MeshData:
            new_verts = []
            for v in mesh.vertices:
                pt = Vec3(v[0], v[1], v[2])
                m_pt = _mirror_point(pt)
                new_verts.append((m_pt.x, m_pt.y, m_pt.z))

            # Mirror reflection inverts spatial orientation (determinant = -1).
            # To preserve outward surface normals, reverse the vertex winding of each face:
            new_faces = [list(reversed(f)) for f in mesh.faces]

            new_edges = []
            if mesh.edges:
                new_edges = [(e[1], e[0]) for e in mesh.edges]

            new_mesh = MeshData(
                vertices=new_verts,
                faces=new_faces,
                edges=new_edges,
                name=f"{mesh.name}_mirrored" if mesh.name else "MirroredMesh",
                material_name=mesh.material_name,
                color=mesh.color,
                face_materials=list(mesh.face_materials) if mesh.face_materials else [],
                face_colors=list(mesh.face_colors) if mesh.face_colors else [],
                ifc_class=mesh.ifc_class,
            )
            return new_mesh

        def _mirror_curve(c: CurveData) -> CurveData:
            new_pts = [_mirror_point(p) for p in c.points]
            res_c = CurveData(points=new_pts, closed=c.closed)
            c_norm = getattr(c, "normal", None)
            if c_norm is not None:
                dot = c_norm.x * n.x + c_norm.y * n.y + c_norm.z * n.z
                res_c.normal = c_norm - n * (2.0 * dot)
            return res_c

        def _mirror_item(item: Any) -> Any:
            if isinstance(item, MeshData):
                return _mirror_mesh(item)
            if isinstance(item, CurveData):
                return _mirror_curve(item)
            if isinstance(item, Vec3):
                return _mirror_point(item)
            if isinstance(item, tuple) and len(item) == 3:
                pt = Vec3(float(item[0]), float(item[1]), float(item[2]))
                m_pt = _mirror_point(pt)
                return (m_pt.x, m_pt.y, m_pt.z)
            if isinstance(item, list):
                return [_mirror_item(x) for x in item]
            return item

        if geometry is None:
            geometry = CurveData(points=[Vec3(1, 1, 0), Vec3(3, 1, 0), Vec3(3, 2, 0), Vec3(1, 2, 0)], closed=True)

        mirrored_geom = _mirror_item(geometry)

        if copy:
            if isinstance(geometry, list):
                result_val = list(geometry) + (mirrored_geom if isinstance(mirrored_geom, list) else [mirrored_geom])
            else:
                result_val = [geometry, mirrored_geom]
        else:
            result_val = mirrored_geom

        return {
            "result": result_val,
            "mirrored": mirrored_geom,
        }

NODE_REGISTRY["transform.mirror"] = TransformMirrorNode
