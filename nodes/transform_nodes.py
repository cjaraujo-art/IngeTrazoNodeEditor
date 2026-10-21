# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric Geometry Transformation, Extrusion, Revolve, and Array Nodes."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


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
        InputSpec("curve", "Profile Curve", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("height", "Height (Z)", SocketType.FLOAT, default=3.0, step=0.5),
        InputSpec("capped", "Cap Ends", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("solid", "Solid Mesh", SocketType.MESH),
    ]

    def compute(self, curve: Any, height: float, capped: bool) -> Dict[str, Any]:
        if not isinstance(curve, CurveData) or not curve.points:
            curve = CurveData(
                points=[Vec3(0, 0, 0), Vec3(4, 0, 0), Vec3(4, 3, 0), Vec3(0, 3, 0)],
                closed=True,
            )
        mesh = MeshData.extrude_curve(curve, float(height), cap=bool(capped))
        return {"solid": mesh}


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
        "Supports open or closed profiles and paths, with automatic start and end capping."
    )
    header_color = (155, 89, 182)

    inputs = [
        InputSpec("profile", "Profile Curve", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("rail", "Rail Path", SocketType.CURVE, default=None, hide_widget=True),
        InputSpec("capped", "Cap Ends", SocketType.BOOL, default=True),
        InputSpec("scale_end", "Scale End", SocketType.FLOAT, default=1.0, min_val=0.01, max_val=10.0, step=0.1),
    ]
    outputs = [
        OutputSpec("solid", "Sweep Solid", SocketType.MESH),
    ]

    def compute(self, profile: Any = None, rail: Any = None, capped: bool = True, scale_end: float = 1.0) -> Dict[str, Any]:
        # Fallback profile: 0.3m radius 12-segment circle
        if not isinstance(profile, CurveData) or len(profile.points) < 3:
            prof_pts: List[Vec3] = []
            for seg in range(12):
                ang = seg * 2.0 * math.pi / 12.0
                prof_pts.append(Vec3(0.3 * math.cos(ang), 0.3 * math.sin(ang), 0.0))
            profile = CurveData(points=prof_pts, closed=True)

        # Fallback rail: curved trajectory
        if not isinstance(rail, CurveData) or len(rail.points) < 2:
            rail_pts: List[Vec3] = [
                Vec3(0.0, 0.0, 0.0),
                Vec3(1.5, 0.5, 1.0),
                Vec3(3.0, 1.8, 2.5),
                Vec3(4.5, 1.2, 4.0),
                Vec3(6.0, 0.0, 5.0),
            ]
            rail = CurveData(points=rail_pts, closed=False)

        pts_rail = rail.points
        k_count = len(pts_rail)
        if k_count < 2:
            return {"solid": MeshData(name="Sweep_Solid")}

        # 1. Compute tangents along rail
        tangents: List[Vec3] = []
        for i in range(k_count):
            if i == 0:
                t = (pts_rail[1] - pts_rail[0]).normalized()
            elif i == k_count - 1:
                t = (pts_rail[k_count - 1] - pts_rail[k_count - 2]).normalized()
            else:
                t = (pts_rail[i + 1] - pts_rail[i - 1]).normalized()
            tangents.append(t if t.length() > 1e-6 else Vec3(0, 0, 1))

        # 2. Parallel Transport Frame (Double Reflection Method / Wang et al.)
        normals: List[Vec3] = []
        binormals: List[Vec3] = []

        # Initial frame at k=0
        t0 = tangents[0]
        guide = Vec3(0, 0, 1) if abs(t0.z) < 0.9 else Vec3(1, 0, 0)
        n0 = t0.cross(guide).normalized()
        b0 = t0.cross(n0).normalized()
        normals.append(n0)
        binormals.append(b0)

        for i in range(1, k_count):
            p_prev = pts_rail[i - 1]
            p_curr = pts_rail[i]
            v1 = p_curr - p_prev
            c1 = v1.dot(v1)

            t_prev = tangents[i - 1]
            t_curr = tangents[i]
            n_prev = normals[i - 1]

            if c1 > 1e-12:
                # First reflection across bisecting plane of p_curr - p_prev
                r_l_t = t_prev - v1 * ((2.0 / c1) * v1.dot(t_prev))
                r_l_n = n_prev - v1 * ((2.0 / c1) * v1.dot(n_prev))

                # Second reflection across bisecting plane of t_curr - r_l_t
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

        # 3. Loft profile along stations
        prof_pts = profile.points
        m_count = len(prof_pts)
        mesh_verts: List[Tuple[float, float, float]] = []
        mesh_faces: List[List[int]] = []
        mesh_edges_set = set()

        def _add_edge(a: int, b: int) -> None:
            mesh_edges_set.add((min(a, b), max(a, b)))

        s_end = float(scale_end)
        for i in range(k_count):
            t_ratio = i / float(k_count - 1) if k_count > 1 else 0.0
            scale = 1.0 + (s_end - 1.0) * t_ratio
            origin = pts_rail[i]
            n_vec = normals[i]
            b_vec = binormals[i]
            t_vec = tangents[i]

            for p in prof_pts:
                # Map 2D profile coordinates (x, y) to normal and binormal
                pos = origin + (n_vec * (p.x * scale)) + (b_vec * (p.y * scale)) + (t_vec * (p.z * scale))
                mesh_verts.append((pos.x, pos.y, pos.z))

        # Quad faces connecting consecutive stations
        seg_count = m_count if profile.closed else m_count - 1
        for i in range(k_count - 1):
            base_a = i * m_count
            base_b = (i + 1) * m_count
            for j in range(seg_count):
                j_next = (j + 1) % m_count
                i00 = base_a + j
                i10 = base_b + j
                i11 = base_b + j_next
                i01 = base_a + j_next
                mesh_faces.append([i00, i10, i11, i01])
                _add_edge(i00, i10)
                _add_edge(i10, i11)
                _add_edge(i11, i01)
                _add_edge(i01, i00)

        # 4. Caps
        if capped and profile.closed and not rail.closed and m_count >= 3:
            # Start cap (facing backward: reversed)
            start_cap = list(reversed(range(0, m_count)))
            # End cap (facing forward)
            end_base = (k_count - 1) * m_count
            end_cap = list(range(end_base, end_base + m_count))
            mesh_faces.insert(0, start_cap)
            mesh_faces.append(end_cap)

        return {
            "solid": MeshData(
                vertices=mesh_verts,
                faces=mesh_faces,
                edges=list(mesh_edges_set),
                name="Sweep_Solid",
            )
        }


# ============================================================================
# 9. Flip Normals / Faces Node
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
