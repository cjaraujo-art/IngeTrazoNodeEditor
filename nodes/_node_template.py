# SPDX-License-Identifier: GPL-3.0-or-later
"""
================================================================================
🤖 AI & DEVELOPER NODE CREATION TEMPLATE FOR INGETRAZO NODE EDITOR
================================================================================
HOW TO CREATE A NEW NODE:
1. Copy this file into `nodes/my_custom_nodes.py` (do NOT start filename with `_`).
2. Decorate your class with `@register_node` and inherit from `BaseNode`.
3. Define `type_id`, `title`, `category`, `inputs`, and `outputs`.
4. Implement `compute(self, **inputs) -> dict[str, Any]`.
5. Click "🔄 Reload Nodes" in the Node Editor toolbar—no restart required!

ARCHITECTURAL RULES FOR AI AGENTS:
- Coordinate System: Z-UP (X = East/Red, Y = North/Green, Z = Up/Blue). Units = Meters.
- Watertightness: Every 3D solid (`MeshData`) MUST have closed topology (every edge
  shared by 2 faces) and Counter-Clockwise (CCW) outward face winding so IngeTrazo's
  `solid_report()` / `is_closed` BIM guard accepts the volume.
- List Broadcasting: By default (`AccessMode.ITEM`), you write `compute()` for a SINGLE
  item (e.g., `origin: Vec3`), and `BaseNode` automatically broadcasts over lists!
  Use `access=AccessMode.LIST` only when your node needs the whole list at once (e.g. Loft).
- Zero External Dependencies: Use Python's `math` module and `Vec3`, `CurveData`, `MeshData`.
================================================================================
"""

from __future__ import annotations
import math
from typing import Any, Dict, List

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


@register_node
class ParametricGableHouseNode(BaseNode):
    """Example template node: generates a watertight gable-roof building massing."""
    type_id = "template.gable_house"
    title = "Gable Roof Massing"
    category = "Architecture"
    header_color = (140, 85, 60)

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("width", "Width X (m)", SocketType.FLOAT, default=6.0, min_val=0.5, step=0.5),
        InputSpec("length", "Length Y (m)", SocketType.FLOAT, default=10.0, min_val=0.5, step=0.5),
        InputSpec("wall_h", "Wall H (m)", SocketType.FLOAT, default=3.0, min_val=0.5, step=0.25),
        InputSpec("roof_h", "Ridge H (m)", SocketType.FLOAT, default=1.8, min_val=0.1, step=0.25),
    ]
    outputs = [
        OutputSpec("solid", "Building Solid", SocketType.MESH),
        OutputSpec("ridge_top", "Ridge Midpoint", SocketType.VEC3),
    ]

    def compute(
        self,
        origin: Vec3,
        width: float,
        length: float,
        wall_h: float,
        roof_h: float,
    ) -> Dict[str, Any]:
        x0, y0, z0 = origin.x, origin.y, origin.z
        x1 = x0 + width
        xm = x0 + 0.5 * width
        y1 = y0 + length
        zw = z0 + wall_h
        zr = zw + roof_h

        # 10 shared vertices (5 front at y0, 5 back at y1)
        verts = [
            # Front pentagon (y = y0): 0..4
            (x0, y0, z0), (x1, y0, z0), (x1, y0, zw), (xm, y0, zr), (x0, y0, zw),
            # Back pentagon (y = y1): 5..9
            (x0, y1, z0), (x1, y1, z0), (x1, y1, zw), (xm, y1, zr), (x0, y1, zw),
        ]

        # Outward CCW faces (watertight 7-face prism)
        faces = [
            [0, 1, 2, 3, 4],  # Front gable (-Y)
            [9, 8, 7, 6, 5],  # Back gable (+Y)
            [0, 5, 6, 1],     # Floor (-Z)
            [1, 6, 7, 2],     # Right wall (+X)
            [2, 7, 8, 3],     # Right roof slope
            [3, 8, 9, 4],     # Left roof slope
            [4, 9, 5, 0],     # Left wall (-X)
        ]

        edges = [
            (0, 1), (1, 2), (2, 3), (3, 4), (4, 0),
            (5, 6), (6, 7), (7, 8), (8, 9), (9, 5),
            (0, 5), (1, 6), (2, 7), (3, 8), (4, 9)
        ]

        mesh = MeshData(vertices=verts, faces=faces, edges=edges, name="GableHouse")
        ridge_mid = Vec3(xm, y0 + 0.5 * length, zr)
        return {"solid": mesh, "ridge_top": ridge_mid}
