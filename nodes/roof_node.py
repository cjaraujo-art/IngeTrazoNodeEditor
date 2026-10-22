# SPDX-License-Identifier: GPL-3.0-or-later
"""Parametric 3D Roof Node powered by Straight-Skeleton, 3D Plane Projections, and Geometric Offsets."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node

# Import local straight-skeleton package
try:
    from py_straight_skeleton import compute_skeleton
except ImportError:
    try:
        from ..py_straight_skeleton import compute_skeleton
    except ImportError:
        compute_skeleton = None


def _extract_rings(
    boundary_in: Any,
    holes_in: Any = None,
) -> Tuple[List[Tuple[float, float]], List[List[Tuple[float, float]]], Vec3, Vec3, Vec3, Vec3, float]:
    """
    Extracts 2D contour loops, courtyard holes, and 3D orthonormal basis (origin, U, V, W, base_z).
    Supports horizontal roofs and tilted 3D planar faces.
    """
    outer_3d: List[Vec3] = []
    holes_3d: List[List[Vec3]] = []

    # 1. Unpack boundary_in
    if isinstance(boundary_in, dict):
        # Dictionary from ReferenceFaceNode or similar surface descriptor
        raw_outer = boundary_in.get("outer", [])
        raw_holes = boundary_in.get("holes", [])
        for p in raw_outer:
            if isinstance(p, Vec3):
                outer_3d.append(p)
            elif isinstance(p, (tuple, list)) and len(p) >= 3:
                outer_3d.append(Vec3(float(p[0]), float(p[1]), float(p[2])))
        for h_ring in raw_holes:
            h_pts: List[Vec3] = []
            for hp in h_ring:
                if isinstance(hp, Vec3):
                    h_pts.append(hp)
                elif isinstance(hp, (tuple, list)) and len(hp) >= 3:
                    h_pts.append(Vec3(float(hp[0]), float(hp[1]), float(hp[2])))
            if len(h_pts) >= 3:
                holes_3d.append(h_pts)
    elif isinstance(boundary_in, CurveData):
        outer_3d = list(boundary_in.points)
    elif isinstance(boundary_in, MeshData):
        if boundary_in.vertices:
            if boundary_in.faces:
                f0 = boundary_in.faces[0]
                outer_3d = [Vec3(*boundary_in.vertices[idx]) for idx in f0 if 0 <= idx < len(boundary_in.vertices)]
            else:
                outer_3d = [Vec3(*v) for v in boundary_in.vertices]
    elif isinstance(boundary_in, list) and boundary_in:
        first = boundary_in[0]
        if isinstance(first, Vec3):
            outer_3d = list(boundary_in)
        elif isinstance(first, (tuple, list)):
            outer_3d = [Vec3(float(p[0]), float(p[1]), float(p[2]) if len(p) >= 3 else 0.0) for p in boundary_in]

    # 2. Unpack optional explicit holes_in
    if holes_in is not None:
        if isinstance(holes_in, CurveData):
            if len(holes_in.points) >= 3:
                holes_3d.append(list(holes_in.points))
        elif isinstance(holes_in, list):
            for h_item in holes_in:
                if isinstance(h_item, CurveData):
                    if len(h_item.points) >= 3:
                        holes_3d.append(list(h_item.points))
                elif isinstance(h_item, list):
                    h_pts2 = [p if isinstance(p, Vec3) else Vec3(float(p[0]), float(p[1]), float(p[2]) if len(p) >= 3 else 0.0) for p in h_item]
                    if len(h_pts2) >= 3:
                        holes_3d.append(h_pts2)

    # 3. Default fallback: 20x12m building with courtyard hole (6x4m) at Z=3m
    if len(outer_3d) < 3:
        outer_3d = [Vec3(0.0, 0.0, 3.0), Vec3(20.0, 0.0, 3.0), Vec3(20.0, 12.0, 3.0), Vec3(0.0, 12.0, 3.0)]
        holes_3d = [[Vec3(7.0, 4.0, 3.0), Vec3(13.0, 4.0, 3.0), Vec3(13.0, 8.0, 3.0), Vec3(7.0, 8.0, 3.0)]]

    # 4. Check whether planar points are horizontal in XY
    z_vals = [p.z for p in outer_3d]
    avg_z = sum(z_vals) / len(z_vals)
    is_xy = all(abs(p.z - avg_z) < 1e-3 for p in outer_3d)

    if is_xy:
        base_z = avg_z
        origin_3d = Vec3(0.0, 0.0, base_z)
        u_axis = Vec3(1.0, 0.0, 0.0)
        v_axis = Vec3(0.0, 1.0, 0.0)
        w_axis = Vec3(0.0, 0.0, 1.0)
        outer_2d = [(p.x, p.y) for p in outer_3d]
        holes_2d = [[(p.x, p.y) for p in h] for h in holes_3d]
    else:
        # Compute 3D polygon normal
        n_pts = len(outer_3d)
        nx = ny = nz = 0.0
        for i in range(n_pts):
            p1, p2 = outer_3d[i], outer_3d[(i + 1) % n_pts]
            nx += (p1.y - p2.y) * (p1.z + p2.z)
            ny += (p1.z - p2.z) * (p1.x + p2.x)
            nz += (p1.x - p2.x) * (p1.y + p2.y)
        normal = Vec3(nx, ny, nz).normalized()
        if normal.z < 0:
            normal = normal * -1.0
        w_axis = normal
        ref = Vec3(0.0, 0.0, 1.0) if abs(normal.z) < 0.9 else Vec3(1.0, 0.0, 0.0)
        u_axis = w_axis.cross(ref).normalized()
        v_axis = w_axis.cross(u_axis).normalized()
        origin_3d = outer_3d[0]
        base_z = 0.0

        def _to_2d(p: Vec3) -> Tuple[float, float]:
            d = p - origin_3d
            return (d.dot(u_axis), d.dot(v_axis))

        outer_2d = [_to_2d(p) for p in outer_3d]
        holes_2d = [[_to_2d(p) for p in h] for h in holes_3d]

    # Ensure CCW orientation for outer boundary
    def _area2(ring: List[Tuple[float, float]]) -> float:
        n = len(ring)
        return sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n))

    if _area2(outer_2d) < 0:
        outer_2d.reverse()

    # Ensure CW orientation for holes
    norm_holes: List[List[Tuple[float, float]]] = []
    for h in holes_2d:
        if len(h) >= 3:
            h_copy = list(h)
            if _area2(h_copy) > 0:
                h_copy.reverse()
            norm_holes.append(h_copy)

    return outer_2d, norm_holes, origin_3d, u_axis, v_axis, w_axis, base_z


def _offset_contour(pts: List[Tuple[float, float]], dist: float) -> List[Tuple[float, float]]:
    """Offsets a 2D closed polygon outward by `dist` using parallel segment intersections."""
    if abs(dist) < 1e-4 or len(pts) < 3:
        return list(pts)
    n = len(pts)
    lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        # Right-hand normal for outward offset of CCW loop
        nx = dy / length * dist
        ny = -dx / length * dist
        lines.append(((p1[0] + nx, p1[1] + ny), (p2[0] + nx, p2[1] + ny)))

    m = len(lines)
    if m < 3:
        return list(pts)

    out: List[Tuple[float, float]] = []
    for i in range(m):
        (x1, y1), (x2, y2) = lines[i]
        (x3, y3), (x4, y4) = lines[(i + 1) % m]
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-6:
            out.append((x2, y2))
        else:
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
            out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    return out


@register_node
class ParametricRoofNode(BaseNode):
    type_id = "arch.roof"
    title = "Parametric Roof"
    category = "Architecture"
    description = (
        "Generates 3D watertight parametric hip roofs via Straight Skeleton "
        "from any boundary contour or referenced face, with optional courtyard/interior holes.\n"
        "Supports both horizontal roofs and sloped/tilted 3D surfaces."
    )
    header_color = (191, 97, 106)

    inputs = [
        InputSpec("boundary", "Boundary / Face", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("holes", "Courtyard Holes", SocketType.ANY, default=None, hide_widget=True),
        InputSpec("pitch", "Pitch / Slope (°)", SocketType.FLOAT, default=35.0, min_val=5.0, max_val=75.0, step=1.0),
        InputSpec("overhang", "Overhang (m)", SocketType.FLOAT, default=0.4, min_val=0.0, max_val=2.0, step=0.05),
        InputSpec("thickness", "Thickness (m)", SocketType.FLOAT, default=0.25, min_val=0.05, max_val=1.0, step=0.05),
        InputSpec("elevation", "Elevation (m)", SocketType.FLOAT, default=0.0, step=0.5),
    ]
    outputs = [
        OutputSpec("solid", "Roof Solid", SocketType.MESH),
        OutputSpec("eaves", "Eave Lines", SocketType.CURVE),
        OutputSpec("peaks", "Peak Points", SocketType.VEC3),
    ]

    def compute(
        self,
        boundary: Any,
        holes: Any = None,
        pitch: float = 35.0,
        overhang: float = 0.4,
        thickness: float = 0.25,
        elevation: float = 0.0,
        style: int = 0,
    ) -> Dict[str, Any]:
        c_outer, c_holes, origin_3d, u_axis, v_axis, w_axis, base_z = _extract_rings(boundary, holes)
        slope_deg = max(5.0, min(80.0, float(pitch)))
        tan_slope = math.tan(math.radians(slope_deg))
        d_overhang = max(0.0, float(overhang))
        th = max(0.05, float(thickness))
        elev = float(elevation)
        roof_style = int(style) if isinstance(style, (int, float)) else 0

        # Apply eave overhang buffer to outer perimeter
        if d_overhang > 1e-4:
            eave_outer = _offset_contour(c_outer, d_overhang)
        else:
            eave_outer = list(c_outer)

        eave_holes = list(c_holes)

        mesh_verts: List[Tuple[float, float, float]] = []
        mesh_faces: List[List[int]] = []
        mesh_edges: List[Tuple[int, int]] = []

        ridge_lines: List[Vec3] = []
        peak_points: List[Vec3] = []

        def to_3d(u: float, v: float, h: float) -> Vec3:
            """Unprojects 2D (u, v) and skeleton height h into 3D space."""
            return origin_3d + (u_axis * u) + (v_axis * v) + (w_axis * (elev + h))

        # ---------------------------------------------------------------------
        # Style 0: Hip Roof (Straight Skeleton)
        # ---------------------------------------------------------------------
        if roof_style == 0 and compute_skeleton is not None:
            try:
                skel = compute_skeleton(eave_outer, eave_holes)
                skel_faces = skel.get_faces()

                # Map skeleton nodes to 3D vertex indices
                skel_vert_map: Dict[int, int] = {}
                for idx, node in enumerate(skel.nodes):
                    dist_to_eave = max(0.0, float(node.time))
                    h = dist_to_eave * tan_slope
                    pt = to_3d(float(node.position.x), float(node.position.y), h)
                    v_idx = len(mesh_verts)
                    mesh_verts.append((pt.x, pt.y, pt.z))
                    skel_vert_map[idx] = v_idx
                    if dist_to_eave > 1e-3:
                        peak_points.append(pt)

                # Top sloped roof facets
                for f_indices in skel_faces:
                    if len(f_indices) >= 3:
                        face_v = [skel_vert_map[i] for i in f_indices]
                        mesh_faces.append(face_v)

                # Collect ridges and hips
                for a_node, b_node in skel.arc_iterator():
                    if a_node.time > 1e-3 and b_node.time > 1e-3:
                        p_a = to_3d(float(a_node.position.x), float(a_node.position.y), a_node.time * tan_slope)
                        p_b = to_3d(float(b_node.position.x), float(b_node.position.y), b_node.time * tan_slope)
                        ridge_lines.append(p_a)
                        ridge_lines.append(p_b)

            except Exception:
                roof_style = 1  # Fallback to Gable on geometry exception

        # ---------------------------------------------------------------------
        # Style 1: Gable Roof
        # ---------------------------------------------------------------------
        if roof_style == 1 or not mesh_faces:
            xs = [p[0] for p in eave_outer]
            ys = [p[1] for p in eave_outer]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            dx, dy = max_x - min_x, max_y - min_y
            along_x = dx >= dy

            half_span = (dy if along_x else dx) * 0.5
            ridge_h = half_span * tan_slope

            if along_x:
                mid_y = (min_y + max_y) * 0.5
                r1 = to_3d(min_x, mid_y, ridge_h)
                r2 = to_3d(max_x, mid_y, ridge_h)
                p_sw = to_3d(min_x, min_y, 0.0)
                p_se = to_3d(max_x, min_y, 0.0)
                p_ne = to_3d(max_x, max_y, 0.0)
                p_nw = to_3d(min_x, max_y, 0.0)

                mesh_verts.extend([p_sw.to_tuple(), p_se.to_tuple(), r2.to_tuple(), r1.to_tuple(), p_ne.to_tuple(), p_nw.to_tuple()])
                # South slope
                mesh_faces.append([0, 1, 2, 3])
                # North slope
                mesh_faces.append([3, 2, 4, 5])
                # West gable triangle
                mesh_faces.append([0, 3, 5])
                # East gable triangle
                mesh_faces.append([1, 4, 2])

                ridge_lines.extend([r1, r2])
                peak_points.extend([r1, r2])
            else:
                mid_x = (min_x + max_x) * 0.5
                r1 = to_3d(mid_x, min_y, ridge_h)
                r2 = to_3d(mid_x, max_y, ridge_h)
                p_sw = to_3d(min_x, min_y, 0.0)
                p_se = to_3d(max_x, min_y, 0.0)
                p_ne = to_3d(max_x, max_y, 0.0)
                p_nw = to_3d(min_x, max_y, 0.0)

                mesh_verts.extend([p_sw.to_tuple(), p_se.to_tuple(), p_ne.to_tuple(), p_nw.to_tuple(), r1.to_tuple(), r2.to_tuple()])
                mesh_faces.append([0, 4, 5, 3])
                mesh_faces.append([4, 1, 2, 5])
                mesh_faces.append([0, 1, 4])
                mesh_faces.append([3, 5, 2])
                ridge_lines.extend([r1, r2])
                peak_points.extend([r1, r2])

        # ---------------------------------------------------------------------
        # Style 2: Shed / Mono-Pitch
        # ---------------------------------------------------------------------
        elif roof_style == 2:
            xs = [p[0] for p in eave_outer]
            ys = [p[1] for p in eave_outer]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            total_h = (max_y - min_y) * tan_slope

            p0 = to_3d(min_x, min_y, 0.0)
            p1 = to_3d(max_x, min_y, 0.0)
            p2 = to_3d(max_x, max_y, total_h)
            p3 = to_3d(min_x, max_y, total_h)

            mesh_verts.extend([p0.to_tuple(), p1.to_tuple(), p2.to_tuple(), p3.to_tuple()])
            mesh_faces.append([0, 1, 2, 3])
            ridge_lines.extend([p3, p2])
            peak_points.extend([p3, p2])

        # ---------------------------------------------------------------------
        # Style 3: Flat / Parapet Roof
        # ---------------------------------------------------------------------
        elif roof_style == 3:
            parapet_h = 0.6
            for x, y in eave_outer:
                mesh_verts.append(to_3d(x, y, parapet_h).to_tuple())
            n = len(eave_outer)
            mesh_faces.append(list(range(n)))

        # ---------------------------------------------------------------------
        # Style 4: Mansard Roof
        # ---------------------------------------------------------------------
        elif roof_style == 4:
            curb_offset = d_overhang + 1.2
            curb_outer = _offset_contour(c_outer, -curb_offset)
            if len(curb_outer) >= 3:
                curb_h = 1.2 * math.tan(math.radians(65.0))
                deck_h = curb_h + 0.8 * tan_slope

                base_v = [to_3d(x, y, 0.0).to_tuple() for x, y in eave_outer]
                curb_v = [to_3d(x, y, curb_h).to_tuple() for x, y in curb_outer]

                mesh_verts.extend(base_v)
                mesh_verts.extend(curb_v)
                n = len(eave_outer)
                m = len(curb_outer)
                for i in range(min(n, m)):
                    nxt = (i + 1) % min(n, m)
                    mesh_faces.append([i, nxt, n + nxt, n + i])
                deck_face = [n + j for j in range(m)]
                mesh_faces.append(deck_face)

        # ---------------------------------------------------------------------
        # Create Watertight Solid (Bottom Soffit + Fascia Walls)
        # ---------------------------------------------------------------------
        num_top_verts = len(mesh_verts)
        num_top_faces = len(mesh_faces)

        # Duplicate vertices downward along -w_axis by `th` for bottom soffit
        for i in range(num_top_verts):
            vx, vy, vz = mesh_verts[i]
            mesh_verts.append((vx - w_axis.x * th, vy - w_axis.y * th, vz - w_axis.z * th))

        # Bottom faces (reversed order for downward outward normal)
        for i in range(num_top_faces):
            top_f = mesh_faces[i]
            bot_f = [idx + num_top_verts for idx in reversed(top_f)]
            mesh_faces.append(bot_f)

        # Build fascia quads around eave perimeter
        eave_pts_3d: List[Vec3] = []
        n_eave = len(eave_outer)
        eave_top_indices: List[int] = []
        for ex, ey in eave_outer:
            best_idx = 0
            best_dist = 1e9
            for v_idx in range(num_top_verts):
                vx, vy, vz = mesh_verts[v_idx]
                target_pt = to_3d(ex, ey, 0.0)
                d = (vx - target_pt.x) ** 2 + (vy - target_pt.y) ** 2 + (vz - target_pt.z) ** 2
                if d < best_dist:
                    best_dist = d
                    best_idx = v_idx
            eave_top_indices.append(best_idx)
            eave_pts_3d.append(Vec3(mesh_verts[best_idx][0], mesh_verts[best_idx][1], mesh_verts[best_idx][2]))

        for i in range(n_eave):
            nxt = (i + 1) % n_eave
            t0 = eave_top_indices[i]
            t1 = eave_top_indices[nxt]
            b0 = t0 + num_top_verts
            b1 = t1 + num_top_verts
            mesh_faces.append([t0, t1, b1, b0])
            mesh_edges.append((t0, t1))
            mesh_edges.append((b0, b1))
            mesh_edges.append((t0, b0))

        solid_mesh = MeshData(
            vertices=mesh_verts,
            faces=mesh_faces,
            edges=mesh_edges,
            name="Parametric_Roof",
            ifc_class="IfcRoof",
        )

        eaves_curve = CurveData(points=eave_pts_3d, closed=True)

        return {
            "solid": solid_mesh,
            "eaves": eaves_curve,
            "peaks": peak_points,
        }
