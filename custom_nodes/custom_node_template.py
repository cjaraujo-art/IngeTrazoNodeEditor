# SPDX-License-Identifier: GPL-3.0-or-later
"""
================================================================================
🧩 INGETRAZO PARAMETRIC NODE EDITOR — CUSTOM NODE DEVELOPER TEMPLATE
================================================================================
How to create and use custom nodes:
1. Place this file (or any .py file containing @register_node classes) into:
   - Plugin custom nodes folder: `custom_nodes/`
   - OR User AppData folder: `%APPDATA%/IngeTrazo/custom_nodes/` (persists across updates!)
2. Decorate your node class with `@register_node` and inherit from `BaseNode`.
3. In the Node Editor toolbar or right-click canvas menu:
   - Click "🔄 Reload Nodes Catalog" (or press the 🔄 button)
   - Your custom node will immediately appear in the Add Menu (Space / Tab)!
   - No restart of IngeTrazo required!

Architecture Best Practices:
- Coordinate System: Z-UP (X = East/Red, Y = North/Green, Z = Up/Blue). Units = Meters.
- Watertight Topology: 3D solids (`MeshData`) must have closed surfaces where every
  edge is shared by 2 faces and all polygon normals point outward (CCW when viewed from outside).
- Automatic Broadcasting: `compute()` handles single items (e.g. `origin: Vec3`),
  and `BaseNode` automatically broadcasts across list inputs unless `access=AccessMode.LIST` is set.
================================================================================
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node


# ============================================================================
# ADDON / PLUGIN PACK CONFIGURATION
# ============================================================================
# Setting ADDON_NAME gives your addon its own dedicated TAB in the top ribbon
# and its own category in the search popup!
#
# If ADDON_NAME is omitted:
#   - A folder (e.g. custom_nodes/seg_nodes/) becomes the tab: "Seg Nodes"
#   - A python file (e.g. custom_nodes/seg nodes.py) becomes the tab: "Seg Nodes"
ADDON_NAME = "Custom Pack"
ADDON_AUTHOR = "Community Developer"
ADDON_VERSION = "1.0.0"


# ============================================================================
# EXAMPLE 1: PARAMETRIC 3D ARCHITECTURAL SOLID (WALL PANEL WITH OPENING)
# ============================================================================
@register_node
class CustomWallPanelNode(BaseNode):
    """
    Parametric architectural wall panel solid with a centered opening for doors or windows.
    Outputs a watertight 3D solid mesh accepted by IngeTrazo and BIM export.
    """
    type_id = "custom.wall_panel"
    title = "Custom Wall Panel"
    category = "Custom Pack"
    description = "Generates a watertight 3D architectural wall panel with a customizable window/door opening."
    header_color = (70, 130, 180)  # Steel Blue
    icon_tag = "WP"  # Text badge (e.g. "WP") or emoji (e.g. "🧱")
    # icon = "wall_panel.png"  # Optional: image file in your addon's 'icons/' folder!

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=4.0, min_val=1.0, step=0.25),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=3.0, min_val=1.0, step=0.25),
        InputSpec("thickness", "Thickness (m)", SocketType.FLOAT, default=0.25, min_val=0.05, step=0.05),
        InputSpec("opening_w", "Opening W (m)", SocketType.FLOAT, default=1.6, min_val=0.2, step=0.1),
        InputSpec("opening_h", "Opening H (m)", SocketType.FLOAT, default=1.8, min_val=0.2, step=0.1),
        InputSpec("sill_h", "Sill Height (m)", SocketType.FLOAT, default=0.8, min_val=0.0, step=0.1),
    ]
    outputs = [
        OutputSpec("panel_mesh", "Panel Solid", SocketType.MESH),
    ]

    def compute(
        self,
        origin: Vec3,
        width: float,
        height: float,
        thickness: float,
        opening_w: float,
        opening_h: float,
        sill_h: float,
    ) -> Dict[str, Any]:
        x0, y0, z0 = (origin or Vec3()).x, (origin or Vec3()).y, (origin or Vec3()).z
        W = max(1.0, float(width))
        H = max(1.0, float(height))
        T = max(0.05, float(thickness))

        ow = max(0.2, min(float(opening_w), W - 0.4))
        oh = max(0.2, min(float(opening_h), H - 0.4))
        sh = max(0.0, min(float(sill_h), H - oh - 0.2))

        ox_min = x0 + (W - ow) * 0.5
        ox_max = ox_min + ow
        oz_min = z0 + sh
        oz_max = oz_min + oh

        # Build solid sub-boxes: jambs, sill, lintel
        parts: List[MeshData] = []

        # 1. Left jamb
        left_w = ox_min - x0
        if left_w > 1e-4:
            parts.append(MeshData.create_box(Vec3(x0, y0, z0), left_w, T, H))

        # 2. Right jamb
        right_w = (x0 + W) - ox_max
        if right_w > 1e-4:
            parts.append(MeshData.create_box(Vec3(ox_max, y0, z0), right_w, T, H))

        # 3. Bottom sill (between jambs)
        if sh > 1e-4:
            parts.append(MeshData.create_box(Vec3(ox_min, y0, z0), ow, T, sh))

        # 4. Top lintel (between jambs)
        lintel_h = (z0 + H) - oz_max
        if lintel_h > 1e-4:
            parts.append(MeshData.create_box(Vec3(ox_min, y0, oz_max), ow, T, lintel_h))

        # Merge components into a single watertight panel solid
        all_verts: List[Tuple[float, float, float]] = []
        all_faces: List[List[int]] = []
        all_edges: List[Tuple[int, int]] = []
        offset = 0

        for p in parts:
            all_verts.extend(p.vertices)
            for f in p.faces:
                all_faces.append([idx + offset for idx in f])
            for e in p.edges:
                all_edges.append((e[0] + offset, e[1] + offset))
            offset += len(p.vertices)

        panel = MeshData(
            vertices=all_verts,
            faces=all_faces,
            edges=all_edges,
            name="Custom_Wall_Panel",
            ifc_class="IfcWall",
        )
        return {"panel_mesh": panel}


# ============================================================================
# EXAMPLE 2: 2D/3D PARAMETRIC CURVE PROFILE
# ============================================================================
@register_node
class CustomWaveCurveNode(BaseNode):
    """
    Generates a smooth mathematical sinusoidal wave curve profile and planar ribbon.
    """
    type_id = "custom.wave_profile"
    title = "Custom Wave Profile"
    category = "Custom Pack"
    description = "Generates a smooth parametric sinusoidal wave curve and planar ribbon face."
    header_color = (130, 90, 160)  # Purple
    icon_tag = "🌊"  # Emoji badge

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("length", "Length X (m)", SocketType.FLOAT, default=8.0, min_val=0.5, step=0.5),
        InputSpec("amplitude", "Amplitude (m)", SocketType.FLOAT, default=1.0, min_val=0.05, step=0.1),
        InputSpec("wavelength", "Wavelength (m)", SocketType.FLOAT, default=2.0, min_val=0.2, step=0.2),
        InputSpec("samples", "Samples", SocketType.INT, default=48, min_val=8, max_val=256, step=4),
        InputSpec("closed", "Close to Axis", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("curve", "Wave Curve", SocketType.CURVE),
        OutputSpec("face", "Ribbon Face", SocketType.MESH),
    ]

    def compute(
        self,
        origin: Vec3,
        length: float,
        amplitude: float,
        wavelength: float,
        samples: int,
        closed: bool,
    ) -> Dict[str, Any]:
        x0, y0, z0 = (origin or Vec3()).x, (origin or Vec3()).y, (origin or Vec3()).z
        L = max(0.5, float(length))
        A = float(amplitude)
        wl = max(0.2, float(wavelength))
        N = max(8, int(samples))
        is_closed = bool(closed)

        pts: List[Vec3] = []
        for i in range(N + 1):
            t = i / N
            x = x0 + t * L
            z = z0 + A * math.sin(2.0 * math.pi * (t * L) / wl)
            pts.append(Vec3(x, y0, z))

        if is_closed:
            # Add base return points to close the curve into a planar region
            pts.append(Vec3(x0 + L, y0, z0))
            pts.append(Vec3(x0, y0, z0))
            curve = CurveData(points=pts, closed=True)
            face = curve.to_mesh_face("WaveFace")
        else:
            curve = CurveData(points=pts, closed=False)
            face = curve.to_wire_mesh("WaveWire")

        return {"curve": curve, "face": face}


# ============================================================================
# EXAMPLE 3: MATHEMATICAL / UTILITY EVALUATOR
# ============================================================================
@register_node
class CustomFormulaNode(BaseNode):
    """
    Evaluates a customizable mathematical expression: f(x, y) = scale * (a * x^2 + b * y + c).
    """
    type_id = "custom.formula_eval"
    title = "Custom Formula (Quadratic)"
    category = "Custom Pack"
    description = "Evaluates a parametric quadratic formula f(x, y) = scale * (a * x^2 + b * y + c)."
    header_color = (190, 120, 50)  # Amber
    icon_tag = "fx"  # Math abbreviation badge

    inputs = [
        InputSpec("x", "Input X", SocketType.FLOAT, default=2.0),
        InputSpec("y", "Input Y", SocketType.FLOAT, default=3.0),
        InputSpec("a", "Coeff A", SocketType.FLOAT, default=1.0, step=0.1),
        InputSpec("b", "Coeff B", SocketType.FLOAT, default=2.0, step=0.1),
        InputSpec("c", "Constant C", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("scale", "Scale", SocketType.FLOAT, default=1.0, step=0.1),
    ]
    outputs = [
        OutputSpec("result", "Result", SocketType.FLOAT),
    ]

    def compute(self, x: float, y: float, a: float, b: float, c: float, scale: float) -> Dict[str, Any]:
        val = float(scale) * (float(a) * (float(x) ** 2) + float(b) * float(y) + float(c))
        return {"result": val}
