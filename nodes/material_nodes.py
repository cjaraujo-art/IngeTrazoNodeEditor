# SPDX-License-Identifier: GPL-3.0-or-later
"""Material assignment and multi-part assembly nodes for IngeTrazo."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


MATERIAL_PRESETS: Dict[str, Dict[str, Any]] = {
    "Glass": {"color": (0.70, 0.85, 0.95), "opacity": 0.30, "finish": "glass"},
    "Frosted Glass": {"color": (0.85, 0.90, 0.95), "opacity": 0.50, "finish": "glass"},
    "Wood Oak": {"color": (0.65, 0.45, 0.28), "opacity": 1.0, "finish": "wood"},
    "Wood Walnut": {"color": (0.38, 0.24, 0.16), "opacity": 1.0, "finish": "wood"},
    "Aluminum Frame": {"color": (0.82, 0.84, 0.86), "opacity": 1.0, "finish": "metal"},
    "Steel Frame": {"color": (0.35, 0.38, 0.42), "opacity": 1.0, "finish": "metal"},
    "Black Metal": {"color": (0.15, 0.15, 0.16), "opacity": 1.0, "finish": "metal"},
    "Concrete": {"color": (0.72, 0.72, 0.72), "opacity": 1.0, "finish": "matte"},
    "White Paint": {"color": (0.95, 0.95, 0.93), "opacity": 1.0, "finish": "matte"},
    "Brick Terracotta": {"color": (0.75, 0.35, 0.25), "opacity": 1.0, "finish": "matte"},
    "Tile Ceramic": {"color": (0.88, 0.88, 0.90), "opacity": 1.0, "finish": "glossy"},
    "Mirror": {"color": (0.95, 0.95, 0.98), "opacity": 1.0, "finish": "metal"},
    "Water": {"color": (0.20, 0.50, 0.70), "opacity": 0.50, "finish": "water"},
    "Grass": {"color": (0.30, 0.60, 0.25), "opacity": 1.0, "finish": "matte"},
    "Custom": {"color": (0.80, 0.80, 0.80), "opacity": 1.0, "finish": "matte"},
}


@register_node
class AssignMaterialNode(BaseNode):
    type_id = "mat.assign"
    title = "Assign Material"
    category = "Material"
    description = (
        "Assigns a material (Glass, Wood, Aluminum, Concrete, etc.), color, and opacity\n"
        "to geometry. When multiple parts are merged into an assembly (window, door),\n"
        "each part preserves its material and transparency when baked to IngeTrazo."
    )
    header_color = (185, 120, 45)

    inputs = [
        InputSpec("geometry", "Geometry", SocketType.ANY, default=None, hide_widget=True),
        InputSpec(
            "material",
            "Preset",
            SocketType.STRING,
            default="Glass",
            choices=list(MATERIAL_PRESETS.keys()),
        ),
        InputSpec("name", "Custom Name", SocketType.STRING, default=""),
        InputSpec("color_r", "Red (0-1)", SocketType.FLOAT, default=0.70, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("color_g", "Green (0-1)", SocketType.FLOAT, default=0.85, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("color_b", "Blue (0-1)", SocketType.FLOAT, default=0.95, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("opacity", "Opacity (0-1)", SocketType.FLOAT, default=0.30, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("override", "Custom Color", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("geometry", "Painted", SocketType.ANY),
        OutputSpec("mat_name", "Material", SocketType.STRING),
    ]

    def get_card_badge_text(self) -> Optional[str]:
        preset = str(self.param_values.get("material", "Glass"))
        custom = str(self.param_values.get("name", "")).strip()
        return f"Material: {custom or preset}"

    def compute(
        self,
        geometry: Any,
        material: str,
        name: str,
        color_r: float,
        color_g: float,
        color_b: float,
        opacity: float,
        override: bool,
    ) -> Dict[str, Any]:
        preset_key = str(material) if material in MATERIAL_PRESETS else "Glass"
        preset_info = MATERIAL_PRESETS.get(preset_key, MATERIAL_PRESETS["Custom"])

        mat_name = str(name).strip() if name and str(name).strip() else preset_key

        if override or preset_key == "Custom":
            r = max(0.0, min(1.0, float(color_r)))
            g = max(0.0, min(1.0, float(color_g)))
            b = max(0.0, min(1.0, float(color_b)))
            col = (r, g, b)
            op = max(0.0, min(1.0, float(opacity)))
        else:
            col = preset_info["color"]
            op = preset_info["opacity"]

        def _apply_material(item: Any) -> Any:
            if isinstance(item, MeshData):
                copied = item.copy()
                copied.material_name = mat_name
                copied.color = col
                copied.opacity = op
                n_faces = len(copied.faces)
                copied.face_materials = [mat_name] * n_faces
                copied.face_colors = [col] * n_faces
                copied.face_opacities = [op] * n_faces
                return copied
            if isinstance(item, CurveData):
                c_copy = item.copy()
                return c_copy
            if isinstance(item, list):
                return [_apply_material(x) for x in item]
            return item

        result_geom = _apply_material(geometry) if geometry is not None else None
        return {"geometry": result_geom, "mat_name": mat_name}


@register_node
class CombinePartsNode(BaseNode):
    type_id = "mat.combine_parts"
    title = "Combine Parts (Assembly)"
    category = "Material"
    description = (
        "Combines separate parts (e.g. glass panes and wood frames) into a single assembly.\n"
        "Preserves each part's assigned material, color, and opacity so the entire assembly\n"
        "bakes cleanly into IngeTrazo as a multi-material window, door, or architectural element."
    )
    header_color = (185, 120, 45)

    inputs = [
        InputSpec("parts", "Parts List", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("name", "Assembly Name", SocketType.STRING, default="Window_Assembly"),
        InputSpec(
            "ifc_class",
            "BIM Tag",
            SocketType.STRING,
            default="IfcWindow",
            choices=["", "IfcWindow", "IfcDoor", "IfcWall", "IfcSlab", "IfcRoof", "IfcColumn", "IfcBeam", "IfcBuildingElementProxy"],
        ),
    ]
    outputs = [
        OutputSpec("assembly", "Assembly", SocketType.MESH),
    ]

    def compute(self, parts: List[Any], name: str, ifc_class: str) -> Dict[str, Any]:
        flat: List[MeshData] = []

        def _collect(item: Any) -> None:
            if isinstance(item, MeshData):
                if item.vertices or item.edges:
                    flat.append(item)
            elif isinstance(item, CurveData):
                if len(item.points) >= 3 and item.closed:
                    flat.append(item.to_mesh_face(name="Profile_Face"))
            elif isinstance(item, (list, tuple)):
                for sub in item:
                    _collect(sub)

        for p in parts:
            _collect(p)

        merged = MeshData.merge(flat, name=name or "CompoundAssembly")
        merged.ifc_class = ifc_class
        return {"assembly": merged}


@register_node
class ColorRGBNode(BaseNode):
    type_id = "mat.color_rgb"
    title = "Color RGB"
    category = "Material"
    description = "Defines an RGB color tuple (0.0 to 1.0) and hex code."
    header_color = (185, 120, 45)

    inputs = [
        InputSpec("r", "Red", SocketType.FLOAT, default=0.8, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("g", "Green", SocketType.FLOAT, default=0.2, min_val=0.0, max_val=1.0, step=0.05),
        InputSpec("b", "Blue", SocketType.FLOAT, default=0.2, min_val=0.0, max_val=1.0, step=0.05),
    ]
    outputs = [
        OutputSpec("color", "Color (RGB)", SocketType.ANY),
        OutputSpec("hex", "Hex String", SocketType.STRING),
    ]

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        r = float(self.param_values.get("r", 0.8))
        g = float(self.param_values.get("g", 0.2))
        b = float(self.param_values.get("b", 0.2))
        cr = max(0, min(255, int(r * 255)))
        cg = max(0, min(255, int(g * 255)))
        cb = max(0, min(255, int(b * 255)))
        hex_code = f"#{cr:02x}{cg:02x}{cb:02x}"
        return [
            {
                "id": "btn_pick_color",
                "label": f"🎨 Pick Color ({hex_code})",
                "tooltip": "Open color picker dialog to choose color visually",
                "color": hex_code,
                "action": "pick_color",
            }
        ]

    def compute(self, r: float, g: float, b: float) -> Dict[str, Any]:
        cr = max(0.0, min(1.0, float(r)))
        cg = max(0.0, min(1.0, float(g)))
        cb = max(0.0, min(1.0, float(b)))
        hex_code = f"#{int(cr * 255):02x}{int(cg * 255):02x}{int(cb * 255):02x}"
        return {"color": (cr, cg, cb), "hex": hex_code}
