# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom Parametric Monolithic Stair Node for IngeTrazo."""

from __future__ import annotations
from typing import Any, Dict

try:
    from ..core_types import MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


@register_node
class ParametricStairNode(BaseNode):
    type_id = "arch.parametric_stair"
    title = "Monolithic Stair"
    category = "Architecture"
    header_color = (150, 95, 50)
    description = "Generates a watertight monolithic concrete stair flight."

    inputs = [
        InputSpec("origin", "Base Pt", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("width", "Width X (m)", SocketType.FLOAT, default=1.20, min_val=0.4, step=0.1),
        InputSpec("riser", "Riser H (m)", SocketType.FLOAT, default=0.175, min_val=0.05, step=0.005),
        InputSpec("tread", "Tread Y (m)", SocketType.FLOAT, default=0.28, min_val=0.10, step=0.02),
        InputSpec("steps", "Step Count", SocketType.INT, default=12, min_val=1, max_val=60, step=1),
    ]
    outputs = [
        OutputSpec("stair_mesh", "Stair Solid", SocketType.MESH),
        OutputSpec("top_landing", "Top Pt", SocketType.VEC3),
    ]

    def compute(
        self,
        origin: Vec3,
        width: float,
        riser: float,
        tread: float,
        steps: int,
    ) -> Dict[str, Any]:
        steps = max(1, int(steps))
        step_boxes = []
        for i in range(steps):
            step_origin = Vec3(origin.x, origin.y + i * tread, origin.z)
            step_height = (i + 1) * riser
            box = MeshData.create_box(step_origin, width, tread, step_height)
            step_boxes.append(box)

        merged = MeshData.merge(step_boxes, name="MonolithicStair")
        merged.ifc_class = "IfcStair"
        top_pt = Vec3(origin.x, origin.y + steps * tread, origin.z + steps * riser)
        return {"stair_mesh": merged, "top_landing": top_pt}
