# SPDX-License-Identifier: GPL-3.0-or-later
"""Built-in parametric nodes for IngeTrazo."""

from __future__ import annotations
import ast
import math
import operator
from typing import Any, Dict, List

try:
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


# ============================================================================
# 1. INPUTS & GENERATORS
# ============================================================================
@register_node
class NumberSliderNode(BaseNode):
    type_id = "input.number"
    title = "Number Slider"
    category = "Inputs"
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("val", "Value", SocketType.FLOAT, default=2.0, min_val=-100.0, max_val=100.0, step=0.1),
    ]
    outputs = [
        OutputSpec("out", "Number", SocketType.FLOAT),
    ]

    def compute(self, val: float) -> Dict[str, Any]:
        return {"out": float(val)}


@register_node
class IntegerSliderNode(BaseNode):
    type_id = "input.integer"
    title = "Integer Slider"
    category = "Inputs"
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("val", "Value", SocketType.INT, default=5, min_val=-1000, max_val=1000, step=1),
    ]
    outputs = [
        OutputSpec("out", "Integer", SocketType.INT),
    ]

    def compute(self, val: int) -> Dict[str, Any]:
        return {"out": int(round(val))}


@register_node
class BooleanToggleNode(BaseNode):
    type_id = "input.toggle"
    title = "Boolean Toggle"
    category = "Inputs"
    description = "Sleek Grasshopper-style boolean switch. Click the button to toggle between True and False."
    header_color = (44, 110, 130)
    inputs = []
    outputs = [
        OutputSpec("out", "Value", SocketType.BOOL),
    ]

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        val = bool(self.param_values.get("val", True))
        return [
            {
                "id": "btn_toggle",
                "label": "🟢 TRUE" if val else "🔴 FALSE",
                "tooltip": "Click to toggle True / False",
                "color": "#2e7d32" if val else "#c62828",
                "action": "toggle_value",
            }
        ]

    def get_card_badge_text(self) -> Optional[str]:
        return None

    def toggle_value(self) -> None:
        val = bool(self.param_values.get("val", True))
        self.set_param("val", not val)
        self.is_dirty = True

    def compute(self, val: Optional[bool] = None) -> Dict[str, Any]:
        if val is not None:
            return {"out": bool(val)}
        current = bool(self.param_values.get("val", True))
        return {"out": current}


@register_node
class StringInputNode(BaseNode):
    type_id = "input.string"
    title = "String / Text"
    category = "Inputs"
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("text", "Text", SocketType.STRING, default="Hello IngeTrazo"),
    ]
    outputs = [
        OutputSpec("out", "String", SocketType.STRING),
    ]

    def compute(self, text: str) -> Dict[str, Any]:
        return {"out": str(text)}


@register_node
class PanelNode(BaseNode):
    type_id = "input.panel"
    title = "Panel"
    category = "Inputs"
    description = (
        "Grasshopper-style multi-line data inspector and input panel.\n"
        "• When wired: acts as a data viewer, formatting items with indices [0], [1]...\n"
        "• When unwired: type multi-line numbers, text, or coordinates (x, y, z) to output as lists."
    )
    header_color = (44, 110, 130)
    inputs = [
        InputSpec("data", "Data", SocketType.ANY, default=None, access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("out", "Output", SocketType.ANY),
    ]

    def compute(self, data: Any = None, text: Optional[str] = None) -> Dict[str, Any]:
        if data is not None and (not isinstance(data, list) or len(data) > 0):
            display_str = self._format_data(data)
            return {"out": data, "text": display_str}
        else:
            raw_text = text if text is not None else str(self.param_values.get("text", ""))
            parsed = self._parse_text(raw_text)
            return {"out": parsed, "text": raw_text}

    def _format_data(self, val: Any, max_items: int = 100) -> str:
        if isinstance(val, (list, tuple)):
            if not val:
                return "[Empty List]"
            lines = []
            for i, item in enumerate(val[:max_items]):
                lines.append(f"[{i}] {self._format_item(item)}")
            if len(val) > max_items:
                lines.append(f"... ({len(val) - max_items} more items, total {len(val)})")
            return "\n".join(lines)
        return self._format_item(val)

    def _format_item(self, item: Any) -> str:
        if item is None:
            return "None"
        if isinstance(item, Vec3):
            return f"Point({item.x:.2f}, {item.y:.2f}, {item.z:.2f})"
        if isinstance(item, MeshData):
            closed_str = "closed" if getattr(item, "is_closed", False) else "open"
            return f"MeshData ({len(item.vertices)} verts, {len(item.faces)} faces, {closed_str})"
        if isinstance(item, CurveData):
            return f"CurveData ({len(item.points)} pts, closed={item.closed})"
        if isinstance(item, float):
            return f"{item:.4f}".rstrip("0").rstrip(".") or "0"
        return str(item)

    def _parse_text(self, text: str) -> Any:
        if not text or not text.strip():
            return ""
        raw_lines = text.splitlines()
        lines = [ln.strip() for ln in raw_lines if ln.strip()]
        if not lines:
            return ""
        parsed = []
        for line in lines:
            if line.lower() == "true":
                parsed.append(True)
                continue
            if line.lower() == "false":
                parsed.append(False)
                continue
            # Try parsing Vec3 / Point coordinate: e.g. "1, 2, 3" or "(1, 2, 3)"
            clean_coord = line.strip("()[]{}")
            if "," in clean_coord:
                parts = [p.strip() for p in clean_coord.split(",")]
                if len(parts) in (2, 3):
                    try:
                        x = float(parts[0])
                        y = float(parts[1])
                        z = float(parts[2]) if len(parts) == 3 else 0.0
                        parsed.append(Vec3(x, y, z))
                        continue
                    except ValueError:
                        pass
            try:
                parsed.append(int(line))
                continue
            except ValueError:
                pass
            try:
                parsed.append(float(line))
                continue
            except ValueError:
                pass
            parsed.append(line)

        if len(lines) == 1 and "\n" not in text:
            return parsed[0]
        return parsed


@register_node
class SeriesNode(BaseNode):
    type_id = "math.series"
    title = "Series (Range)"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("start", "Start", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("step", "Step", SocketType.FLOAT, default=3.0, step=0.5),
        InputSpec("count", "Count", SocketType.INT, default=4, min_val=1, max_val=500, step=1),
    ]
    outputs = [
        OutputSpec("seq", "List", SocketType.FLOAT),
    ]

    def compute(self, start: float, step: float, count: int) -> Dict[str, Any]:
        n = max(0, min(2000, int(count)))
        return {"seq": [start + i * step for i in range(n)]}


# Safe AST math environment for ExpressionNode
_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg,
}
_SAFE_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
    "pi": math.pi, "rad": math.radians, "deg": math.degrees,
}


def _eval_ast(node: ast.AST, env: Dict[str, Any]) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name) and node.id in env:
        return float(env[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return float(_SAFE_OPS[type(node.op)](_eval_ast(node.left, env), _eval_ast(node.right, env)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return float(_SAFE_OPS[type(node.op)](_eval_ast(node.operand, env)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
        fn = _SAFE_FUNCS[node.func.id]
        args = [_eval_ast(a, env) for a in node.args]
        return float(fn(*args))
    raise ValueError(f"Unsupported expression syntax: {ast.dump(node)}")


@register_node
class MathExpressionNode(BaseNode):
    type_id = "math.expression"
    title = "Math Expression"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("expr", "f(x,y)", SocketType.STRING, default="sin(x) * cos(y) + 2.0"),
        InputSpec("x", "x", SocketType.FLOAT, default=1.0, step=0.25),
        InputSpec("y", "y", SocketType.FLOAT, default=1.0, step=0.25),
    ]
    outputs = [
        OutputSpec("result", "Result", SocketType.FLOAT),
    ]

    def compute(self, expr: str, x: float, y: float) -> Dict[str, Any]:
        tree = ast.parse(expr.strip(), mode="eval")
        env = {**_SAFE_FUNCS, "x": x, "y": y}
        return {"result": _eval_ast(tree.body, env)}


@register_node
class DivideDomainNode(BaseNode):
    type_id = "math.divide_domain"
    title = "Divide Domain"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("start", "Start", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("end", "End", SocketType.FLOAT, default=10.0, step=0.5),
        InputSpec("count", "Segments", SocketType.INT, default=10, min_val=1, max_val=1000, step=1),
    ]
    outputs = [
        OutputSpec("seq", "List", SocketType.FLOAT),
        OutputSpec("step", "Step Size", SocketType.FLOAT),
    ]

    def compute(self, start: float, end: float, count: int) -> Dict[str, Any]:
        n = max(1, min(2000, int(count)))
        step = (end - start) / float(n)
        return {
            "seq": [start + i * step for i in range(n + 1)],
            "step": step,
        }


@register_node
class CrossReferenceNode(BaseNode):
    type_id = "math.cross_reference"
    title = "Cross Reference"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("list_a", "List A", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("list_b", "List B", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("a_out", "A x B", SocketType.ANY),
        OutputSpec("b_out", "B x A", SocketType.ANY),
    ]

    def compute(self, list_a: List[Any], list_b: List[Any]) -> Dict[str, Any]:
        la = list(list_a) if isinstance(list_a, (list, tuple)) else ([list_a] if list_a is not None else [])
        lb = list(list_b) if isinstance(list_b, (list, tuple)) else ([list_b] if list_b is not None else [])
        if not la or not lb:
            return {"a_out": [], "b_out": []}
        out_a: List[Any] = []
        out_b: List[Any] = []
        for a in la:
            for b in lb:
                out_a.append(a)
                out_b.append(b)
        return {"a_out": out_a, "b_out": out_b}


@register_node
class MathAddNode(BaseNode):
    type_id = "math.add"
    title = "Add"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=0.0),
        InputSpec("b", "B", SocketType.ANY, default=0.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        if isinstance(a, Vec3) and isinstance(b, Vec3):
            return {"res": a + b}
        if isinstance(a, Vec3):
            return {"res": Vec3(a.x + float(b), a.y + float(b), a.z + float(b))}
        if isinstance(b, Vec3):
            return {"res": Vec3(float(a) + b.x, float(a) + b.y, float(a) + b.z)}
        try:
            return {"res": float(a) + float(b)}
        except Exception:
            return {"res": 0.0}


@register_node
class MathSubtractNode(BaseNode):
    type_id = "math.subtract"
    title = "Subtract"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=0.0),
        InputSpec("b", "B", SocketType.ANY, default=0.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        if isinstance(a, Vec3) and isinstance(b, Vec3):
            return {"res": a - b}
        if isinstance(a, Vec3):
            return {"res": Vec3(a.x - float(b), a.y - float(b), a.z - float(b))}
        if isinstance(b, Vec3):
            return {"res": Vec3(float(a) - b.x, float(a) - b.y, float(a) - b.z)}
        try:
            return {"res": float(a) - float(b)}
        except Exception:
            return {"res": 0.0}


@register_node
class MathMultiplyNode(BaseNode):
    type_id = "math.multiply"
    title = "Multiply"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=1.0),
        InputSpec("b", "B", SocketType.ANY, default=1.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        if isinstance(a, Vec3):
            return {"res": a * float(b)}
        if isinstance(b, Vec3):
            return {"res": b * float(a)}
        try:
            return {"res": float(a) * float(b)}
        except Exception:
            return {"res": 0.0}


@register_node
class MathDivideNode(BaseNode):
    type_id = "math.divide"
    title = "Divide"
    category = "Math & Lists"
    header_color = (60, 100, 140)
    inputs = [
        InputSpec("a", "A", SocketType.ANY, default=1.0),
        InputSpec("b", "B", SocketType.ANY, default=1.0),
    ]
    outputs = [
        OutputSpec("res", "Result", SocketType.ANY),
    ]

    def compute(self, a: Any, b: Any) -> Dict[str, Any]:
        try:
            fb = float(b)
            if abs(fb) < 1e-12:
                return {"res": 0.0}
            if isinstance(a, Vec3):
                return {"res": Vec3(a.x / fb, a.y / fb, a.z / fb)}
            return {"res": float(a) / fb}
        except Exception:
            return {"res": 0.0}


# ============================================================================
# 2. POINTS, VECTORS & GRIDS
# ============================================================================
@register_node
class ConstructPointNode(BaseNode):
    type_id = "vec.point_xyz"
    title = "Point XYZ"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("x", "X (m)", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("y", "Y (m)", SocketType.FLOAT, default=0.0, step=0.5),
        InputSpec("z", "Z (m)", SocketType.FLOAT, default=0.0, step=0.5),
    ]
    outputs = [
        OutputSpec("pt", "Point", SocketType.VEC3),
    ]

    def compute(self, x: float, y: float, z: float) -> Dict[str, Any]:
        return {"pt": Vec3(x, y, z)}


@register_node
class PointGrid2DNode(BaseNode):
    type_id = "vec.grid_2d"
    title = "Point Grid (2D)"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("nx", "Count X", SocketType.INT, default=3, min_val=1, max_val=100, step=1),
        InputSpec("ny", "Count Y", SocketType.INT, default=3, min_val=1, max_val=100, step=1),
        InputSpec("sx", "Spacing X", SocketType.FLOAT, default=4.0, min_val=0.05, step=0.5),
        InputSpec("sy", "Spacing Y", SocketType.FLOAT, default=4.0, min_val=0.05, step=0.5),
    ]
    outputs = [
        OutputSpec("points", "Points", SocketType.VEC3),
    ]

    def compute(self, origin: Vec3, nx: int, ny: int, sx: float, sy: float) -> Dict[str, Any]:
        pts: List[Vec3] = []
        for ix in range(max(1, nx)):
            for iy in range(max(1, ny)):
                pts.append(Vec3(origin.x + ix * sx, origin.y + iy * sy, origin.z))
        return {"points": pts}


@register_node
class DeconstructPointNode(BaseNode):
    type_id = "vec.deconstruct"
    title = "Deconstruct Point"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("pt", "Point", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("x", "X", SocketType.FLOAT),
        OutputSpec("y", "Y", SocketType.FLOAT),
        OutputSpec("z", "Z", SocketType.FLOAT),
    ]

    def compute(self, pt: Vec3) -> Dict[str, Any]:
        p = pt if isinstance(pt, Vec3) else Vec3()
        return {"x": float(p.x), "y": float(p.y), "z": float(p.z)}


@register_node
class DistanceNode(BaseNode):
    type_id = "vec.distance"
    title = "Distance"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("a", "Point A", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("b", "Point B", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
    ]
    outputs = [
        OutputSpec("dist", "Distance", SocketType.FLOAT),
    ]

    def compute(self, a: Vec3, b: Vec3) -> Dict[str, Any]:
        pa = a if isinstance(a, Vec3) else Vec3()
        pb = b if isinstance(b, Vec3) else Vec3()
        return {"dist": pa.distance_to(pb)}


@register_node
class VectorMathNode(BaseNode):
    type_id = "vec.math"
    title = "Vector Math"
    category = "Points & Vectors"
    header_color = (58, 125, 68)
    inputs = [
        InputSpec("a", "Vector A", SocketType.VEC3, default=Vec3(0, 0, 1), hide_widget=True),
        InputSpec("b", "Vector B", SocketType.VEC3, default=Vec3(0, 1, 0), hide_widget=True),
        InputSpec("op", "Operation", SocketType.STRING, default="Add", choices=["Add", "Subtract", "Cross Product", "Dot Product", "Normalize A"]),
    ]
    outputs = [
        OutputSpec("vec", "Vector", SocketType.VEC3),
        OutputSpec("val", "Scalar", SocketType.FLOAT),
    ]

    def compute(self, a: Vec3, b: Vec3, op: str) -> Dict[str, Any]:
        va = a if isinstance(a, Vec3) else Vec3()
        vb = b if isinstance(b, Vec3) else Vec3()
        if op == "Add":
            return {"vec": va + vb, "val": (va + vb).length()}
        elif op == "Subtract":
            return {"vec": va - vb, "val": (va - vb).length()}
        elif op == "Cross Product":
            cp = va.cross(vb)
            return {"vec": cp, "val": cp.length()}
        elif op == "Dot Product":
            dp = va.dot(vb)
            return {"vec": Vec3(), "val": dp}
        elif op == "Normalize A":
            norm = va.normalized()
            return {"vec": norm, "val": 1.0}
        return {"vec": va, "val": 0.0}


@register_node
class PlaneFromNormalNode(BaseNode):
    type_id = "vec.plane_normal"
    title = "Plane from Normal"
    category = "Points & Vectors"
    description = (
        "Constructs an orthonormal 3D plane coordinate system from an origin point and normal vector.\n"
        "Emits origin, unit normal, unit U (X-axis in plane), unit V (Y-axis in plane), a visual preview rectangle, and a plane dictionary."
    )
    header_color = (58, 125, 68)

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("normal", "Normal", SocketType.VEC3, default=Vec3(0, 0, 1), hide_widget=True),
        InputSpec("size", "Preview Size (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.5),
    ]
    outputs = [
        OutputSpec("origin", "Origin", SocketType.VEC3),
        OutputSpec("normal", "Normal", SocketType.VEC3),
        OutputSpec("u_axis", "U Axis (X)", SocketType.VEC3),
        OutputSpec("v_axis", "V Axis (Y)", SocketType.VEC3),
        OutputSpec("preview", "Plane Preview", SocketType.CURVE),
        OutputSpec("plane", "Plane", SocketType.ANY),
    ]

    def compute(self, origin: Any = None, normal: Any = None, size: float = 2.0) -> Dict[str, Any]:
        p0 = origin if isinstance(origin, Vec3) else Vec3(0, 0, 0)
        n = normal if isinstance(normal, Vec3) else Vec3(0, 0, 1)

        length = math.sqrt(n.x * n.x + n.y * n.y + n.z * n.z)
        if length < 1e-6:
            n = Vec3(0, 0, 1)
        else:
            n = Vec3(n.x / length, n.y / length, n.z / length)

        if abs(n.z) < 0.9:
            guide = Vec3(0, 0, 1)
        else:
            guide = Vec3(1, 0, 0)

        # U = normalize(guide x n)
        u_raw = Vec3(
            guide.y * n.z - guide.z * n.y,
            guide.z * n.x - guide.x * n.z,
            guide.x * n.y - guide.y * n.x,
        )
        u_len = math.sqrt(u_raw.x * u_raw.x + u_raw.y * u_raw.y + u_raw.z * u_raw.z)
        u = Vec3(u_raw.x / u_len, u_raw.y / u_len, u_raw.z / u_len)

        # V = normalize(n x u)
        v = Vec3(
            n.y * u.z - n.z * u.y,
            n.z * u.x - n.x * u.z,
            n.x * u.y - n.y * u.x,
        )

        s = float(size) * 0.5
        c0 = p0 - u * s - v * s
        c1 = p0 + u * s - v * s
        c2 = p0 + u * s + v * s
        c3 = p0 - u * s + v * s
        preview_curve = CurveData(points=[c0, c1, c2, c3], closed=True)

        plane_dict = {
            "origin": (p0.x, p0.y, p0.z),
            "normal": (n.x, n.y, n.z),
            "u": (u.x, u.y, u.z),
            "v": (v.x, v.y, v.z),
        }

        return {
            "origin": p0,
            "normal": n,
            "u_axis": u,
            "v_axis": v,
            "preview": preview_curve,
            "plane": plane_dict,
        }


# ============================================================================
# 3. 2D PROFILES & 3D WATERTIGHT SOLIDS
# ============================================================================
@register_node
class RectangleProfileNode(BaseNode):
    type_id = "curve.rectangle"
    title = "Rectangle Profile"
    category = "Curves"
    header_color = (165, 105, 45)
    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("width", "Width (X)", SocketType.FLOAT, default=4.0, min_val=0.01, step=0.25),
        InputSpec("length", "Length (Y)", SocketType.FLOAT, default=3.0, min_val=0.01, step=0.25),
    ]
    outputs = [
        OutputSpec("curve", "Profile", SocketType.CURVE),
    ]

    def compute(self, origin: Vec3, width: float, length: float) -> Dict[str, Any]:
        x0, y0, z0 = origin.x, origin.y, origin.z
        pts = [
            Vec3(x0, y0, z0),
            Vec3(x0 + width, y0, z0),
            Vec3(x0 + width, y0 + length, z0),
            Vec3(x0, y0 + length, z0),
        ]
        return {"curve": CurveData(points=pts, closed=True)}


@register_node
class BoxSolidNode(BaseNode):
    type_id = "solid.box"
    title = "Box (Cuboid)"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("dx", "Size X (m)", SocketType.FLOAT, default=2.0, min_val=0.01, step=0.2),
        InputSpec("dy", "Size Y (m)", SocketType.FLOAT, default=2.0, min_val=0.01, step=0.2),
        InputSpec("dz", "Height Z (m)", SocketType.FLOAT, default=3.0, min_val=0.01, step=0.2),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, origin: Vec3, dx: float, dy: float, dz: float) -> Dict[str, Any]:
        return {"mesh": MeshData.create_box(origin, dx, dy, dz)}


@register_node
class CylinderSolidNode(BaseNode):
    type_id = "solid.cylinder"
    title = "Cylinder / Column"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("center", "Base Pt", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=0.3, min_val=0.01, step=0.05),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=3.2, min_val=0.01, step=0.2),
        InputSpec("segments", "Segments", SocketType.INT, default=24, min_val=3, max_val=128, step=1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, center: Vec3, radius: float, height: float, segments: int) -> Dict[str, Any]:
        return {"mesh": MeshData.create_cylinder(center, radius, height, segments)}


@register_node
class SphereSolidNode(BaseNode):
    type_id = "solid.sphere"
    title = "Sphere"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("center", "Center Pt", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("radius", "Radius (m)", SocketType.FLOAT, default=1.0, min_val=0.01, step=0.1),
        InputSpec("rings", "Rings (Lat)", SocketType.INT, default=16, min_val=3, max_val=64, step=1),
        InputSpec("segments", "Segments (Lon)", SocketType.INT, default=24, min_val=3, max_val=128, step=1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, center: Vec3, radius: float, rings: int, segments: int) -> Dict[str, Any]:
        return {"mesh": MeshData.create_sphere(center, radius, rings, segments)}


@register_node
class MeshFromPointsNode(BaseNode):
    type_id = "solid.mesh_from_points"
    title = "Mesh From Points"
    category = "3D Solids"
    header_color = (125, 70, 150)
    inputs = [
        InputSpec("points", "Grid Points", SocketType.ANY, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("u", "U Count", SocketType.INT, default=10, min_val=2, max_val=200, step=1),
        InputSpec("v", "V Count", SocketType.INT, default=0, min_val=0, max_val=200, step=1),
        InputSpec("closed_u", "Closed U", SocketType.BOOL, default=False),
        InputSpec("closed_v", "Closed V", SocketType.BOOL, default=False),
        InputSpec("swap_uv", "Swap UV", SocketType.BOOL, default=False),
        InputSpec("triangulate", "Triangulate", SocketType.BOOL, default=False),
        InputSpec("flip_normals", "Flip Normals", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("mesh", "Mesh", SocketType.MESH),
    ]

    def compute(
        self,
        points: List[Any],
        u: int,
        v: int,
        closed_u: bool,
        closed_v: bool,
        swap_uv: bool,
        triangulate: bool,
        flip_normals: bool = False,
    ) -> Dict[str, Any]:
        return {
            "mesh": MeshData.create_from_points(
                pts=points,
                u_count=u,
                v_count=v,
                closed_u=closed_u,
                closed_v=closed_v,
                swap_uv=swap_uv,
                triangulate=triangulate,
                flip_normals=flip_normals,
                name="TerrainMesh",
            )
        }


# ============================================================================
# 4. TRANSFORMS & SCENE OUTPUT
# ============================================================================
@register_node
class TransformMeshNode(BaseNode):
    type_id = "transform.move_rot_scale"
    title = "Transform Solid"
    category = "Transforms"
    header_color = (90, 95, 135)
    inputs = [
        InputSpec("mesh", "Solid", SocketType.MESH, default=None, hide_widget=True),
        InputSpec("offset", "Move XYZ", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("rot_z", "Rotate Z (°)", SocketType.FLOAT, default=0.0, step=5.0),
        InputSpec("scale", "Uniform Scale", SocketType.FLOAT, default=1.0, min_val=0.01, step=0.1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid", SocketType.MESH),
    ]

    def compute(self, mesh: MeshData, offset: Vec3, rot_z: float, scale: float) -> Dict[str, Any]:
        if not isinstance(mesh, MeshData):
            return {"mesh": MeshData()}
        s_vec = Vec3(scale, scale, scale)
        return {"mesh": mesh.transformed(offset=offset, rot_z_deg=rot_z, scale=s_vec)}


@register_node
class MergeMeshesNode(BaseNode):
    type_id = "transform.merge"
    title = "Merge Solids"
    category = "Transforms"
    header_color = (90, 95, 135)
    inputs = [
        InputSpec("meshes", "Solids List", SocketType.MESH, default=[], access=AccessMode.LIST, hide_widget=True),
    ]
    outputs = [
        OutputSpec("merged", "Merged Solid", SocketType.MESH),
    ]

    def compute(self, meshes: List[MeshData]) -> Dict[str, Any]:
        flat: List[MeshData] = []
        for item in meshes:
            if isinstance(item, list):
                flat.extend(x for x in item if isinstance(x, MeshData))
            elif isinstance(item, MeshData):
                flat.append(item)
        return {"merged": MeshData.merge(flat)}


@register_node
class IngeTrazoOutputNode(BaseNode):
    type_id = "scene.output"
    title = "IngeTrazo BIM Output"
    category = "Scene Output"
    header_color = (180, 65, 65)
    is_output_node = True

    inputs = [
        InputSpec("mesh", "Geometry", SocketType.MESH, default=[], access=AccessMode.LIST, hide_widget=True),
        InputSpec("group_name", "Group Name", SocketType.STRING, default="Parametric_Group"),
        InputSpec(
            "ifc_class",
            "BIM Tag",
            SocketType.STRING,
            default="",
            choices=["", "IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcRoof", "IfcStair", "IfcBuildingElementProxy"],
        ),
        InputSpec("enabled", "Live Preview", SocketType.BOOL, default=True),
    ]
    outputs = [
        OutputSpec("mesh_out", "Baked", SocketType.MESH),
    ]

    def compute(self, mesh: List[MeshData], group_name: str, ifc_class: str, enabled: bool) -> Dict[str, Any]:
        out_list: List[MeshData] = []
        flat: List[MeshData] = []

        def _collect(x: Any) -> None:
            if x is None:
                return
            if isinstance(x, MeshData):
                if x.vertices or x.edges:
                    flat.append(x)
            elif isinstance(x, CurveData):
                if len(x.points) >= 3 and x.closed:
                    flat.append(x.to_mesh_face(name="Profile_Solid"))
                elif x.points:
                    flat.append(x.to_wire_mesh(name="Curve_Wire"))
            elif isinstance(x, (list, tuple)):
                for sub in x:
                    _collect(sub)

        _collect(mesh)

        for idx, item in enumerate(flat):
            copied = item.copy()
            copied.name = group_name if len(flat) == 1 else f"{group_name}_{idx + 1}"
            if ifc_class:
                copied.ifc_class = ifc_class
            out_list.append(copied)
        return {"mesh_out": out_list}
