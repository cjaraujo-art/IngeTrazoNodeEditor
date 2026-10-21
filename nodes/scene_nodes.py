# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene integration nodes for referencing IngeTrazo geometry, faces, and viewports."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core_types import CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


@register_node
class ReferenceFaceNode(BaseNode):
    type_id = "scene.reference_face"
    title = "Reference Face"
    category = "Scene"
    description = (
        "Reference a face or surface from the IngeTrazo 3D viewport into the node graph.\n"
        "Click '📌 Set Selected Face' on the node card to store the currently selected face.\n"
        "Automatically extracts the outer perimeter and all courtyard/interior holes.\n"
        "The referenced face is saved directly in the file (.itgraph) so it is remembered\n"
        "when reopening."
    )
    header_color = (94, 129, 172)

    inputs = [
        InputSpec("name", "Name", SocketType.STRING, default="Referenced_Face"),
    ]
    outputs = [
        OutputSpec("surface", "Surface (Face & Holes)", SocketType.ANY),
        OutputSpec("mesh", "Face Mesh", SocketType.MESH),
        OutputSpec("outer", "Outer Boundary", SocketType.CURVE),
        OutputSpec("holes", "Courtyard Holes", SocketType.ANY),
        OutputSpec("points", "Points", SocketType.VEC3),
    ]

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "btn_set_face",
                "label": "📌 Set Selected Face",
                "tooltip": "Store currently selected face from IngeTrazo 3D viewport",
                "color": "#2b5278",
                "action": "set_face",
            },
            {
                "id": "btn_clear_face",
                "label": "❌ Clear Face",
                "tooltip": "Clear stored face back to default",
                "color": "#4c566a",
                "action": "clear_face",
            },
        ]

    def get_card_badge_text(self) -> Optional[str]:
        stored = self.param_values.get("stored_face")
        if stored and isinstance(stored, dict) and "outer" in stored:
            n_outer = len(stored.get("outer", []))
            n_holes = len(stored.get("holes", []))
            if n_holes > 0:
                return f"📌 Stored: {n_outer} pts ({n_holes} hole{'s' if n_holes > 1 else ''})"
            return f"📌 Stored: {n_outer} pts"
        return "⚪ No face referenced"

    @staticmethod
    def _to_vec3(p: Any) -> Optional[Vec3]:
        """Convert any IngeTrazo Vertex, QVector3D, or coordinate tuple to Vec3."""
        if p is None:
            return None
        if isinstance(p, Vec3):
            return p
        if hasattr(p, "position"):
            pos = p.position
            return Vec3(float(pos.x()), float(pos.y()), float(pos.z()))
        if hasattr(p, "x"):
            x = float(p.x() if callable(p.x) else p.x)
            y = float(p.y() if callable(p.y) else p.y)
            z = float(p.z() if callable(p.z) else p.z)
            return Vec3(x, y, z)
        if isinstance(p, (list, tuple)) and len(p) >= 3:
            return Vec3(float(p[0]), float(p[1]), float(p[2]))
        return None

    @classmethod
    def _extract_face_loops(cls, f: Any) -> Tuple[List[Vec3], List[List[Vec3]]]:
        """Extract outer vertices and holes from an IngeTrazo Face object."""
        outer: List[Vec3] = []
        holes: List[List[Vec3]] = []

        # 1. Outer boundary
        raw_verts = getattr(f, "vertices", None)
        if raw_verts is None:
            raw_loop = getattr(f, "loop", None)
            raw_verts = [getattr(v, "position", v) for v in raw_loop] if raw_loop else []

        if raw_verts:
            for v in raw_verts:
                pt = cls._to_vec3(v)
                if pt:
                    outer.append(pt)

        # 2. Native holes
        raw_holes = getattr(f, "holes", None) or []
        for h_ring in raw_holes:
            h_pts: List[Vec3] = []
            for hv in h_ring:
                pt = cls._to_vec3(hv)
                if pt:
                    h_pts.append(pt)
            if len(h_pts) >= 3:
                holes.append(h_pts)

        return outer, holes

    def reference_from_selection(self, app: Any = None) -> Tuple[str, bool]:
        """Extract the selected face/group from the active IngeTrazo viewport and save into param_values."""
        if app is None:
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                app = getattr(qapp, "_extension_app_handle", None)
            except Exception:
                app = None

        if not app:
            return ("No IngeTrazo app handle available", False)

        viewport = getattr(app, "viewport", None)
        scene = getattr(viewport, "scene", None) or getattr(app, "scene", None)
        if not scene:
            return ("No active scene found", False)

        sel = getattr(scene, "selection", None) or getattr(viewport, "selection", None) or []
        selected_faces = getattr(scene, "selected_faces", None) or getattr(viewport, "selected_faces", None)
        if selected_faces:
            sel = list(sel) + list(selected_faces)

        if not sel:
            return ("Please select a face or group in IngeTrazo first!", False)

        collected_faces: List[Tuple[List[Vec3], List[List[Vec3]]]] = []

        for item in sel:
            if hasattr(item, "vertices") or hasattr(item, "loop"):
                o, h = self._extract_face_loops(item)
                if len(o) >= 3:
                    collected_faces.append((o, h))
            elif hasattr(item, "mesh") and hasattr(item.mesh, "faces"):
                for gf in item.mesh.faces:
                    o, h = self._extract_face_loops(gf)
                    if len(o) >= 3:
                        collected_faces.append((o, h))

        if not collected_faces:
            return ("Selected item has no planar faces", False)

        if len(collected_faces) == 1:
            outer, holes = collected_faces[0]
        else:
            # Sort by planar polygon area (largest is outer boundary)
            def _poly_area(pts: List[Vec3]) -> float:
                if len(pts) < 3:
                    return 0.0
                nx = ny = nz = 0.0
                n = len(pts)
                for i in range(n):
                    a, b = pts[i], pts[(i + 1) % n]
                    nx += (a.y - b.y) * (a.z + b.z)
                    ny += (a.z - b.z) * (a.x + b.x)
                    nz += (a.x - b.x) * (a.y + b.y)
                return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)

            collected_faces.sort(key=lambda item: _poly_area(item[0]), reverse=True)
            outer, holes = collected_faces[0]
            for extra_o, extra_h in collected_faces[1:]:
                holes.append(extra_o)
                holes.extend(extra_h)

        summary_txt = f"{len(outer)} pts" + (f", {len(holes)} hole(s)" if holes else "")
        self.param_values["stored_face"] = {
            "outer": [(p.x, p.y, p.z) for p in outer],
            "holes": [[(p.x, p.y, p.z) for p in h] for h in holes],
            "summary": summary_txt,
        }
        self.is_dirty = True
        return (f"Saved: {summary_txt}", True)

    def clear_reference(self) -> None:
        """Clear stored referenced face."""
        if "stored_face" in self.param_values:
            del self.param_values["stored_face"]
        self.is_dirty = True

    def compute(self, name: str = "Referenced_Face") -> Dict[str, Any]:
        stored = self.param_values.get("stored_face")
        outer_pts: List[Vec3] = []
        holes_pts: List[List[Vec3]] = []

        if stored and isinstance(stored, dict) and "outer" in stored:
            outer_pts = [Vec3(float(p[0]), float(p[1]), float(p[2])) for p in stored.get("outer", [])]
            for h_ring in stored.get("holes", []):
                holes_pts.append([Vec3(float(p[0]), float(p[1]), float(p[2])) for p in h_ring])

        # Sensible default if nothing referenced yet: 24x16m building with 8x6m courtyard hole
        if len(outer_pts) < 3:
            outer_pts = [
                Vec3(0.0, 0.0, 3.0),
                Vec3(24.0, 0.0, 3.0),
                Vec3(24.0, 16.0, 3.0),
                Vec3(0.0, 16.0, 3.0),
            ]
            holes_pts = [[
                Vec3(8.0, 5.0, 3.0),
                Vec3(16.0, 5.0, 3.0),
                Vec3(16.0, 11.0, 3.0),
                Vec3(8.0, 11.0, 3.0),
            ]]

        outer_curve = CurveData(points=outer_pts, closed=True)
        holes_curves = [CurveData(points=h, closed=True) for h in holes_pts]

        surface_dict = {
            "outer": [(p.x, p.y, p.z) for p in outer_pts],
            "holes": [[(p.x, p.y, p.z) for p in h] for h in holes_pts],
            "base_z": outer_pts[0].z if outer_pts else 0.0,
        }

        # Build preview face mesh
        face_mesh = outer_curve.to_mesh_face(name=name or "ReferencedFace")

        return {
            "surface": surface_dict,
            "mesh": face_mesh,
            "outer": outer_curve,
            "holes": holes_curves,
            "points": outer_pts,
        }
