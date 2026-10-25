# SPDX-License-Identifier: GPL-3.0-or-later
"""Wall panel with parametric rectangular openings (windows or doors), built from boxes.

Each opening gets a glass pane, an optional window frame and optional mullions/transoms.
"""

from __future__ import annotations
from typing import Any, Dict, List

try:
    from ..core_types import MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node

# (name, RGB, opacity) of the pane: same colour/opacity as the 'Glass' preset of Assign Material.
GLASS_MATERIAL = ("Vidro", (0.70, 0.85, 0.95), 0.30)
# Window frame: same colour as the 'Aluminum Frame' preset of Assign Material.
FRAME_MATERIAL = ("Aro", (0.82, 0.84, 0.86), 1.0)


def _paint(mesh: "MeshData", mat) -> None:
    """Default material of a generated mesh (the same fields Assign Material fills in)."""
    name, color, opacity = mat
    mesh.material_name = name
    mesh.color = color
    mesh.opacity = opacity
    n_f = len(mesh.faces)
    mesh.face_materials = [name] * n_f
    mesh.face_colors = [color] * n_f
    mesh.face_opacities = [opacity] * n_f


@register_node
class WallPanelOpeningNode(BaseNode):
    type_id = "arch.wall_opening"
    title = "Wall Panel with Opening"
    category = "Architecture"
    description = (
        "Straight wall panel with one or more rectangular openings, as one IfcWall mesh, plus a thin glass pane "
        "per opening (output 'Glass Pane', IfcWindow, already glass material) and a window frame around it "
        "(output 'Frame', IfcMember, aluminium colour; Frame Width 0 = no frame and the pane fills the opening). "
        "Vertical / horizontal bars (mullions / transoms, part of the 'Frame' output) divide each glass into equal panes. "
        "Several windows are spread evenly along the panel (or with a fixed Window Gap in metres; 0 = even). "
        "Window Position (-1 to +1) slides the frame and "
        "glass through the wall thickness: 0 = centred, +1 = flush with the exterior face, -1 = flush with the interior "
        "face; Exterior Side '+' means the exterior is the face with the larger Y (axis X) or larger X (axis Y). "
        "Sill = 0 gives a door. Origin is the panel's base corner; axis X/Y is its direction."
    )
    header_color = (191, 97, 106)

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("axis", "Axis", SocketType.STRING, default="X", choices=["X", "Y"]),
        InputSpec("length", "Length (m)", SocketType.FLOAT, default=4.6, min_val=0.1, step=0.1),
        InputSpec("thickness", "Thickness (m)", SocketType.FLOAT, default=0.25, min_val=0.05, step=0.05),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=2.6, min_val=0.2, step=0.1),
        InputSpec("open_w", "Opening Width (m)", SocketType.FLOAT, default=1.2, min_val=0.0, step=0.1),
        InputSpec("open_h", "Opening Height (m)", SocketType.FLOAT, default=1.2, min_val=0.0, step=0.1),
        InputSpec("sill", "Sill Height (m)", SocketType.FLOAT, default=0.9, min_val=0.0, step=0.1),
        InputSpec("glass_t", "Glass Thickness (m)", SocketType.FLOAT, default=0.03, min_val=0.005, step=0.005),
        InputSpec("frame_w", "Frame Width (m)", SocketType.FLOAT, default=0.05, min_val=0.0, step=0.01),
        InputSpec("frame_d", "Frame Depth (m)", SocketType.FLOAT, default=0.08, min_val=0.02, step=0.01),
        InputSpec("bars_v", "Vertical Bars", SocketType.INT, default=0, min_val=0, max_val=30, step=1),
        InputSpec("bars_h", "Horizontal Bars", SocketType.INT, default=0, min_val=0, max_val=30, step=1),
        InputSpec("bar_w", "Bar Width (m)", SocketType.FLOAT, default=0.04, min_val=0.005, step=0.005),
        InputSpec("bar_d", "Bar Depth (m)", SocketType.FLOAT, default=0.05, min_val=0.01, step=0.005),
        InputSpec("win_count", "Windows per Panel", SocketType.INT, default=1, min_val=1, max_val=20, step=1),
        InputSpec("win_gap", "Window Gap (m, 0=even)", SocketType.FLOAT, default=0.0, min_val=0.0, step=0.05),
        InputSpec("win_pos", "Window Position (-1..+1)", SocketType.FLOAT, default=0.0, min_val=-1.0, max_val=1.0, step=0.1),
        InputSpec("ext_side", "Exterior Side", SocketType.STRING, default="+", choices=["+", "-"]),
    ]
    outputs = [
        OutputSpec("wall_mesh", "Wall Solid", SocketType.MESH),
        OutputSpec("glass_mesh", "Glass Pane", SocketType.MESH),
        OutputSpec("frame_mesh", "Frame", SocketType.MESH),
    ]

    def compute(
        self,
        origin: Vec3,
        axis: str,
        length: float,
        thickness: float,
        height: float,
        open_w: float,
        open_h: float,
        sill: float,
        glass_t: float = 0.03,
        frame_w: float = 0.05,
        frame_d: float = 0.08,
        bars_v: int = 0,
        bars_h: int = 0,
        bar_w: float = 0.04,
        bar_d: float = 0.05,
        win_count: int = 1,
        win_gap: float = 0.0,
        win_pos: float = 0.0,
        ext_side: str = "+",
    ) -> Dict[str, Any]:
        eps = 1e-4
        length = max(0.1, float(length))
        t = max(0.05, float(thickness))
        height = max(0.2, float(height))
        along_y = str(axis).strip().upper() == "Y"

        # Keep at least 10 cm of wall on every side of every opening.
        margin = 0.1
        sill = min(max(0.0, float(sill)), height - 2 * margin)
        h = min(max(0.0, float(open_h)), height - sill - margin)
        n = min(max(1, int(win_count)), max(1, int((length - margin) // (0.05 + margin))))   # each window >= 5 cm wide
        w = min(max(0.0, float(open_w)), (length - (n + 1) * margin) / n)

        def box(u0: float, du: float, z0: float, dz: float) -> MeshData:
            if along_y:
                o = Vec3(origin.x, origin.y + u0, origin.z + z0)
                return MeshData.create_box(o, t, du, dz)
            o = Vec3(origin.x + u0, origin.y, origin.z + z0)
            return MeshData.create_box(o, du, t, dz)

        glass: Any = []                                  # no opening, no glass
        frame: Any = []                                  # no opening, no frame
        if w <= eps or h <= eps:
            pieces: List[MeshData] = [box(0.0, length, 0.0, height)]
        else:
            # --- where the windows go (u = position along the panel)
            gap_req = max(0.0, float(win_gap))
            if n > 1 and gap_req > eps:
                g = min(max(gap_req, margin), (length - 2 * margin - n * w) / (n - 1))
                start = (length - (n * w + (n - 1) * g)) / 2.0
            else:
                g = (length - n * w) / (n + 1)
                start = g
            us = [start + k * (w + g) for k in range(n)]

            # --- wall: full-height piers between windows (and at both ends), then sill / lintel under / over each window
            edges = [0.0] + [x for u in us for x in (u, u + w)] + [length]
            pieces = [box(edges[2 * k], edges[2 * k + 1] - edges[2 * k], 0.0, height) for k in range(n + 1)]
            for u0 in us:
                if sill > eps:
                    pieces.append(box(u0, w, 0.0, sill))                                  # below the opening
                if height - (sill + h) > eps:
                    pieces.append(box(u0, w, sill + h, height - (sill + h)))              # lintel

            # --- window parts: frame ring, bars, glass panes (centred on a plane that can slide through the wall)
            fw = min(max(0.0, float(frame_w)), w / 2.0 - 0.01, h / 2.0 - 0.01)
            fw = fw if fw > eps else 0.0
            fd = min(max(0.02, float(frame_d)), t)
            gt = min(max(0.005, float(glass_t)), t)
            bw = max(0.005, float(bar_w))
            bd = min(max(0.01, float(bar_d)), t)
            sgn = -1.0 if str(ext_side).strip() == "-" else 1.0
            pos = min(max(-1.0, float(win_pos)), 1.0)
            yc = t / 2.0 + sgn * pos * (t - fd) / 2.0     # centre plane (through the thickness) of frame, bars and glass

            def sbox(a0: float, da: float, z0: float, dz: float, depth: float) -> MeshData:
                """Box along the wall (a0, da), height (z0, dz), centred on the window plane."""
                off_s = yc - depth / 2.0
                if along_y:
                    return MeshData.create_box(Vec3(origin.x + off_s, origin.y + a0, origin.z + z0), depth, da, dz)
                return MeshData.create_box(Vec3(origin.x + a0, origin.y + off_s, origin.z + z0), da, depth, dz)

            bars: List[MeshData] = []
            panes: List[MeshData] = []
            for u0 in us:
                if fw > 0.0:
                    bars += [
                        sbox(u0, w, sill, fw, fd),                           # bottom
                        sbox(u0, w, sill + h - fw, fw, fd),                  # top
                        sbox(u0, fw, sill + fw, h - 2 * fw, fd),             # left
                        sbox(u0 + w - fw, fw, sill + fw, h - 2 * fw, fd),    # right
                    ]
                # Glazed area (inside the frame, or the whole opening if there is no frame).
                gu, gz, gw, gh = u0 + fw, sill + fw, w - 2 * fw, h - 2 * fw
                # Mullions (vertical) and transoms (horizontal) divide it into equal panes.
                nv = min(max(0, int(bars_v)), max(0, int((gw - 0.05) // (bw + 0.05))))   # every pane stays >= 5 cm
                nh = min(max(0, int(bars_h)), max(0, int((gh - 0.05) // (bw + 0.05))))
                nc, nr = nv + 1, nh + 1
                pw = (gw - nv * bw) / nc
                ph = (gh - nh * bw) / nr
                for i in range(1, nv + 1):
                    bars.append(sbox(gu + i * pw + (i - 1) * bw, bw, gz, gh, bd))        # vertical bar, full height
                for j in range(1, nh + 1):
                    zj = gz + j * ph + (j - 1) * bw
                    for c in range(nc):
                        bars.append(sbox(gu + c * (pw + bw), pw, zj, bw, bd))            # horizontal bar between verticals
                for r in range(nr):
                    zr = gz + r * (ph + bw)
                    for c in range(nc):
                        panes.append(sbox(gu + c * (pw + bw), pw, zr, ph, gt))           # thin glass pane

            if bars:
                frame = MeshData.merge(bars, name="Parametric_Frame")
                frame.ifc_class = "IfcMember"
                _paint(frame, FRAME_MATERIAL)
            glass = panes[0] if len(panes) == 1 else MeshData.merge(panes, name="Parametric_Glass")
            glass.name = "Parametric_Glass"
            glass.ifc_class = "IfcWindow"
            # Default material: glass (same values as the 'Glass' preset of Assign Material).
            # Wire the pane through an Assign Material node to override it.
            _paint(glass, GLASS_MATERIAL)

        mesh = MeshData.merge(pieces, name="Parametric_Wall")
        mesh.ifc_class = "IfcWall"
        return {"wall_mesh": mesh, "glass_mesh": glass, "frame_mesh": frame}
