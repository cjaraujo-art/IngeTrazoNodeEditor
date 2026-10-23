# SPDX-License-Identifier: GPL-3.0-or-later
"""PySide6 Interactive Node Graph Canvas with Blender-Style Value Sliders."""

from __future__ import annotations
import ast
import math
import operator
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QContextMenuEvent, QCursor, QDrag, QFont, QIcon, QKeyEvent, QMouseEvent,
    QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QFrame, QGraphicsItem, QGraphicsPathItem, QGraphicsProxyWidget,
    QGraphicsScene, QGraphicsView, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter, QSplitterHandle, QTabBar,
    QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

try:
    from .core_types import SOCKET_COLORS, SocketType
    from .engine import GraphEngine, Wire
    from .node_base import BaseNode, InputSpec, NODE_REGISTRY
    from .nodes import discover_nodes
    from .i18n import (
        tr, get_available_languages, get_current_language,
        get_current_language_meta, set_language, register_language_listener,
    )
except (ImportError, ValueError):
    from core_types import SOCKET_COLORS, SocketType
    from engine import GraphEngine, Wire
    from node_base import BaseNode, InputSpec, NODE_REGISTRY
    from nodes import discover_nodes
    from i18n import (
        tr, get_available_languages, get_current_language,
        get_current_language_meta, set_language, register_language_listener,
    )


# ============================================================================
# COMPONENT ICON CACHE & RESOLUTION (DARK & LIGHT THEME SUPPORT)
# ============================================================================
_ICON_CACHE: Dict[Tuple[str, bool], QIcon] = {}


def get_node_icon(type_id: str, is_dark: bool = True) -> QIcon:
    """Returns a QIcon for `type_id` matching dark or light theme, with clean fallback."""
    key = (type_id, is_dark)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    sub_dir = "dark" if is_dark else "light"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "icons", sub_dir, f"{type_id}.png")

    if os.path.isfile(icon_path):
        icon = QIcon(icon_path)
    else:
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(44, 49, 58) if is_dark else QColor(220, 224, 230)
        fg = QColor(220, 224, 230) if is_dark else QColor(33, 37, 43)
        p.setBrush(QBrush(bg))
        p.setPen(QPen(fg, 1.0))
        p.drawRoundedRect(1, 1, 30, 30, 6, 6)
        p.setPen(QPen(fg))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font)
        abbr = (type_id.split(".")[-1][:2]).upper()
        p.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, abbr)
        p.end()
        icon = QIcon(pm)

    _ICON_CACHE[key] = icon
    return icon


# ============================================================================
# BLENDER-STYLE VALUE SLIDER WIDGET
# ============================================================================
_MATH_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg,
}
_MATH_ENV = {
    "pi": math.pi, "e": math.e, "sqrt": math.sqrt,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
}


def _parse_number_or_formula(text: str) -> float:
    cleaned = text.strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        pass

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in _MATH_ENV:
            return float(_MATH_ENV[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _MATH_OPS:
            return float(_MATH_OPS[type(node.op)](_eval(node.left), _eval(node.right)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _MATH_OPS:
            return float(_MATH_OPS[type(node.op)](_eval(node.operand)))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _MATH_ENV:
            fn = _MATH_ENV[node.func.id]
            return float(fn(*[_eval(a) for a in node.args]))
        raise ValueError("Invalid math expression")

    tree = ast.parse(cleaned, mode="eval")
    return _eval(tree.body)


class BlenderValueSlider(QWidget):
    valueChanged = Signal(object)
    ARROW_ZONE_W = 16

    def __init__(
        self,
        label: str,
        value: float,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        step: float = 0.1,
        decimals: Optional[int] = None,
        is_int: bool = False,
        width: int = 196,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.label_text = label
        self.is_int = is_int
        self.min_val = min_val
        self.max_val = max_val
        self.step = max(1.0, float(step)) if is_int else max(1e-4, float(step))
        self.decimals: Optional[int] = 0 if is_int else decimals
        self._value = int(round(value)) if is_int else float(value)

        self._soft_min = float(min_val) if min_val is not None else 0.0
        self._soft_max = (
            float(max_val)
            if max_val is not None
            else max(10.0, abs(float(value)) * 2.5 if value != 0 else 10.0)
        )

        self._hovered = False
        self._pressed = False
        self._dragging = False
        self._press_x = 0.0
        self._start_val = 0.0

        self.setFixedSize(width, 22)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SplitHCursor)

        self._editor = QLineEdit(self)
        self._editor.setGeometry(1, 1, width - 2, 20)
        self._editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor.setStyleSheet(
            "background: #181a1f; color: #ffffff; border: 1px solid #61afef;"
            "border-radius: 3px; font-size: 11px; selection-background-color: #3e6896;"
        )
        self._editor.hide()
        self._editor.editingFinished.connect(self._commit_edit)

    def value(self) -> float | int:
        return int(round(self._value)) if self.is_int else float(self._value)

    def setValue(self, val: float) -> None:
        if self.min_val is not None:
            val = max(float(self.min_val), val)
        if self.max_val is not None:
            val = min(float(self.max_val), val)
        new_val = int(round(val)) if self.is_int else float(val)
        if new_val != self._value:
            self._value = new_val
            self.valueChanged.emit(self._value)
            self.update()

    def set_config(
        self,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        decimals: Optional[int] = None,
        step: Optional[float] = None,
    ) -> None:
        self.min_val = min_val
        self.max_val = max_val
        if decimals is not None:
            self.decimals = int(decimals)
        if step is not None:
            self.step = max(1.0, float(step)) if self.is_int else max(1e-4, float(step))
        self._soft_min = float(min_val) if min_val is not None else 0.0
        self._soft_max = (
            float(max_val)
            if max_val is not None
            else max(10.0, abs(float(self._value)) * 2.5 if self._value != 0 else 10.0)
        )
        if self.min_val is not None and self._value < self.min_val:
            self.setValue(self.min_val)
        elif self.max_val is not None and self._value > self.max_val:
            self.setValue(self.max_val)
        else:
            self.update()

    def _format_val(self) -> str:
        if self.is_int:
            return f"{int(round(self._value))}"
        if self.decimals is not None:
            return f"{self._value:.{self.decimals}f}"
        if abs(self._value) >= 1000.0 or (0.0 < abs(self._value) < 0.01):
            return f"{self._value:.3f}"
        return f"{self._value:.2f}"

    def _enter_edit_mode(self) -> None:
        self._editor.setText(self._format_val())
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()
        self.update()

    def _commit_edit(self) -> None:
        if not self._editor.isVisible():
            return
        text = self._editor.text()
        self._editor.hide()
        try:
            parsed = _parse_number_or_formula(text)
            self.setValue(parsed)
        except Exception:
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._editor.isVisible() and event.key() == Qt.Key.Key_Escape:
            self._editor.hide()
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._dragging = False
            self._press_x = event.position().x()
            self._start_val = float(self._value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pressed:
            dx = event.position().x() - self._press_x
            if not self._dragging and abs(dx) >= 3.0:
                self._dragging = True

            if self._dragging:
                mods = event.modifiers()
                mult = 1.0
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    mult = 0.1
                elif mods & Qt.KeyboardModifier.ControlModifier:
                    mult = 5.0

                pixels_per_step = 8.0 if self.is_int else 4.0
                delta = (dx / pixels_per_step) * self.step * mult
                candidate = self._start_val + delta
                if mods & Qt.KeyboardModifier.ControlModifier:
                    snap_unit = self.step * (5.0 if not self.is_int else 1.0)
                    candidate = round(candidate / snap_unit) * snap_unit
                self.setValue(candidate)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            was_dragging = self._dragging
            self._pressed = False
            self._dragging = False
            x = event.position().x()

            if not was_dragging:
                if x <= self.ARROW_ZONE_W:
                    self.setValue(float(self._value) - self.step)
                elif x >= self.width() - self.ARROW_ZONE_W:
                    self.setValue(float(self._value) + self.step)
                else:
                    self._enter_edit_mode()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._enter_edit_mode()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:
        if self._editor.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        rect = QRectF(0.5, 0.5, w - 1.0, h - 1.0)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, 4.0, 4.0)
        painter.setClipPath(clip_path)

        bg_col = QColor(56, 62, 74) if self._hovered else QColor(43, 48, 59)
        painter.fillRect(rect, bg_col)

        span = self._soft_max - self._soft_min
        if span > 1e-9:
            ratio = (float(self._value) - self._soft_min) / span
            ratio = max(0.0, min(1.0, ratio))
            if ratio > 0.0:
                fill_col = QColor(74, 114, 168, 195) if not self._dragging else QColor(92, 138, 198, 220)
                painter.fillRect(QRectF(0.5, 0.5, (w - 1.0) * ratio, h - 1.0), fill_col)

        painter.setClipping(False)
        border_col = QColor(110, 150, 205) if (self._hovered or self._dragging) else QColor(62, 68, 82)
        painter.setPen(QPen(border_col, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 4.0, 4.0)

        font = QFont("Sans Serif", 8)
        painter.setFont(font)
        if self._hovered and not self._dragging:
            painter.setPen(QColor(190, 200, 215))
            painter.drawText(QRectF(3.0, 0.0, 12.0, h), Qt.AlignmentFlag.AlignCenter, "◂")
            painter.drawText(QRectF(w - 15.0, 0.0, 12.0, h), Qt.AlignmentFlag.AlignCenter, "▸")

        pad_x = 16.0 if (self._hovered and not self._dragging) else 8.0
        text_rect = QRectF(pad_x, 0.0, w - 2.0 * pad_x, h)

        painter.setPen(QColor(225, 230, 238))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, tr(self.label_text))

        val_font = QFont("Sans Serif", 8, QFont.Weight.DemiBold)
        painter.setFont(val_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self._format_val())


# ============================================================================
# NODE COMBO BOX
# ============================================================================
class NodeComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._prev_proxy_z = 20.0
        self._prev_node_z = 0.0

    def showPopup(self) -> None:
        proxy = self.graphicsProxyWidget()
        if proxy is not None:
            self._prev_proxy_z = proxy.zValue()
            proxy.setZValue(2000.0)
            parent_item = proxy.parentItem()
            if parent_item is not None:
                self._prev_node_z = parent_item.zValue()
                parent_item.setZValue(9999.0)
        super().showPopup()

    def hidePopup(self) -> None:
        super().hidePopup()
        proxy = self.graphicsProxyWidget()
        if proxy is not None:
            proxy.setZValue(self._prev_proxy_z)
            parent_item = proxy.parentItem()
            if parent_item is not None:
                parent_item.setZValue(self._prev_node_z)


# ============================================================================
# SOCKET PIN & BEZIER WIRE GRAPHICS ITEMS
# ============================================================================
class SocketItem(QGraphicsItem):
    RADIUS = 6.2

    def __init__(self, parent_node_item: NodeItem, socket_id: str, label: str, stype: SocketType, is_output: bool) -> None:
        super().__init__(parent_node_item)
        self.node_item = parent_node_item
        self.socket_id = socket_id
        self.label = label
        self.stype = stype
        self.is_output = is_output
        r, g, b = SOCKET_COLORS.get(stype, (180, 180, 180))
        self.color = QColor(r, g, b)
        self.setAcceptHoverEvents(True)
        self.hovered = False
        self.setToolTip(f"{tr(self.label)} ({self.stype.name})")

    def retranslate_ui(self) -> None:
        self.setToolTip(f"{tr(self.label)} ({self.stype.name})")
        self.update()

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 3.0
        return QRectF(-r, -r, 2.0 * r, 2.0 * r)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.RADIUS + (1.5 if self.hovered else 0.0)
        painter.setPen(QPen(QColor(20, 23, 28), 1.8))
        painter.setBrush(QBrush(self.color.lighter(125) if self.hovered else self.color))
        painter.drawEllipse(QPointF(0, 0), r, r)

    def hoverEnterEvent(self, event) -> None:
        self.hovered = True
        self.update()

    def hoverLeaveEvent(self, event) -> None:
        self.hovered = False
        self.update()


class WireItem(QGraphicsPathItem):
    def __init__(self, src_sock: SocketItem, dst_sock: Optional[SocketItem] = None, wire_model: Optional[Wire] = None) -> None:
        super().__init__()
        self.src_sock = src_sock
        self.dst_sock = dst_sock
        self.wire_model = wire_model
        self.drag_pos: QPointF = src_sock.scenePos()
        self.setZValue(-1)
        self.update_path()

    def update_path(self) -> None:
        p1 = self.src_sock.scenePos()
        p2 = self.dst_sock.scenePos() if self.dst_sock else self.drag_pos
        dx = max(40.0, abs(p2.x() - p1.x()) * 0.55)
        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())
        path = QPainterPath(p1)
        path.cubicTo(c1, c2, p2)
        self.setPath(path)

        color = self.src_sock.color
        pen = QPen(color, 2.5)
        if self.dst_sock is None:
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)


# ============================================================================
# BLENDER-STYLE STACKED NODE ITEM
# ============================================================================
class NodeItem(QGraphicsItem):
    WIDTH = 228.0
    HEADER_H = 28.0
    ROW_H = 28.0

    def __init__(self, node: BaseNode, on_param_changed: Callable[[str, str, object], None]) -> None:
        super().__init__()
        self.node = node
        self.on_param_changed = on_param_changed
        self.input_sockets: Dict[str, SocketItem] = {}
        self.output_sockets: Dict[str, SocketItem] = {}
        self.proxies: Dict[str, QGraphicsProxyWidget] = {}
        self._input_row_y: Dict[str, float] = {}
        self._output_row_y: Dict[str, float] = {}

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setPos(node.pos[0], node.pos[1])

        action_buttons = self.node.get_action_buttons() if hasattr(self.node, "get_action_buttons") else []
        badge_text = self.node.get_card_badge_text() if hasattr(self.node, "get_card_badge_text") else None
        extra_rows = len(action_buttons) + (1 if badge_text is not None else 0)

        if self.node.type_id == "input.panel":
            self.WIDTH = 230.0
            self.height = 195.0
        else:
            self.WIDTH = 228.0
            total_rows = max(1, len(node.outputs) + len(node.inputs)) + extra_rows
            self.height = self.HEADER_H + total_rows * self.ROW_H + 10.0
        self._build_sockets_and_widgets()

    @property
    def has_preview_eye(self) -> bool:
        if hasattr(self.node, "has_preview_eye"):
            return bool(self.node.has_preview_eye)
        if any(out.type in (SocketType.MESH, SocketType.CURVE, SocketType.VEC3) for out in self.node.outputs):
            return True
        if getattr(self.node, "is_output_node", False):
            return True
        non_geo_types = {
            "math.add", "math.subtract", "math.multiply", "math.divide", "math.sin", "math.cos",
            "math.expression", "input.number", "input.slider", "input.toggle", "input.string",
            "input.panel", "color.rgb", "mat.color_rgb", "vec.decompose_xyz", "vec.distance", "mesh.volume",
            "mesh.solid_report", "input.valuelist"
        }
        if self.node.type_id in non_geo_types:
            return False
        for out in self.node.outputs:
            if out.type == SocketType.ANY:
                return True
        return False

    def update_panel_display(self) -> None:
        if self.node.type_id != "input.panel" or not hasattr(self, "_panel_editor"):
            return
        engine = getattr(self.scene(), "engine", None)
        is_conn = False
        if engine is not None:
            is_conn = any(
                wire.dst_node == self.node.id and wire.dst_socket == "data"
                for wire in engine.wires
            )

        self._panel_is_connected = is_conn
        if is_conn:
            self._panel_editor.setReadOnly(True)
            self._panel_editor.setStyleSheet("""
                QPlainTextEdit {
                    background: #14171d;
                    color: #98c379;
                    border: 1px solid #2e3440;
                    border-radius: 4px;
                    padding: 4px;
                    font-family: Consolas, monospace;
                    font-size: 11px;
                }
            """)
            txt = str(self.node.cached_outputs.get("text", ""))
            if self._panel_editor.toPlainText() != txt:
                self._panel_editor.blockSignals(True)
                self._panel_editor.setPlainText(txt)
                self._panel_editor.blockSignals(False)
        else:
            self._panel_editor.setReadOnly(False)
            self._panel_editor.setStyleSheet("""
                QPlainTextEdit {
                    background: #181a20;
                    color: #e5e9f0;
                    border: 1px solid #3b4252;
                    border-radius: 4px;
                    padding: 4px;
                    font-family: Consolas, monospace;
                    font-size: 11px;
                }
                QPlainTextEdit:focus {
                    border-color: #5e81ac;
                }
            """)

    def _build_sockets_and_widgets(self) -> None:
        if self.node.type_id == "input.panel":
            for out_idx, out_spec in enumerate(self.node.outputs):
                y = self.HEADER_H + 14.0 + out_idx * 20.0
                self._output_row_y[out_spec.id] = y
                sock = SocketItem(self, out_spec.id, out_spec.label, out_spec.type, is_output=True)
                sock.setPos(self.WIDTH, y)
                self.output_sockets[out_spec.id] = sock

            for in_idx, in_spec in enumerate(self.node.inputs):
                y = self.HEADER_H + 14.0 + in_idx * 20.0
                self._input_row_y[in_spec.id] = y
                sock = SocketItem(self, in_spec.id, in_spec.label, in_spec.type, is_output=False)
                sock.setPos(0.0, y)
                self.input_sockets[in_spec.id] = sock

            te = QPlainTextEdit()
            te.setFixedSize(int(self.WIDTH - 20.0), 136)
            te.setFont(QFont("Consolas", 9))
            te.setStyleSheet("""
                QPlainTextEdit {
                    background: #181a20;
                    color: #e5e9f0;
                    border: 1px solid #3b4252;
                    border-radius: 4px;
                    padding: 4px;
                    font-family: Consolas, monospace;
                    font-size: 11px;
                }
                QPlainTextEdit:focus {
                    border-color: #5e81ac;
                }
            """)
            initial_text = str(self.node.param_values.get("text", ""))
            te.setPlainText(initial_text)

            def _on_te_changed():
                if not getattr(self, "_panel_is_connected", False):
                    txt = te.toPlainText()
                    self.node.set_param("text", txt)
                    self.node.is_dirty = True
                    sc = self.scene()
                    if hasattr(sc, "trigger_eval"):
                        sc.trigger_eval()

            te.textChanged.connect(_on_te_changed)
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(te)
            proxy.setPos(10.0, self.HEADER_H + 26.0)
            self.proxies["_panel_te"] = proxy
            self._panel_editor = te
            return

        row_idx = 0

        for out_spec in self.node.outputs:
            y = self.HEADER_H + 15.0 + row_idx * self.ROW_H
            self._output_row_y[out_spec.id] = y
            sock = SocketItem(self, out_spec.id, out_spec.label, out_spec.type, is_output=True)
            sock.setPos(self.WIDTH, y)
            self.output_sockets[out_spec.id] = sock
            row_idx += 1

        for in_spec in self.node.inputs:
            y = self.HEADER_H + 15.0 + row_idx * self.ROW_H
            self._input_row_y[in_spec.id] = y
            sock = SocketItem(self, in_spec.id, in_spec.label, in_spec.type, is_output=False)
            sock.setPos(0.0, y)
            self.input_sockets[in_spec.id] = sock

            if not in_spec.hide_widget:
                widget, x_offset = self._create_inline_widget(in_spec)
                if widget is not None:
                    proxy = QGraphicsProxyWidget(self)
                    proxy.setWidget(widget)
                    proxy.setPos(x_offset, y - 11.0)
                    proxy.setZValue(20.0 if isinstance(widget, NodeComboBox) else 10.0)
                    self.proxies[in_spec.id] = proxy
            row_idx += 1

        badge_text = self.node.get_card_badge_text() if hasattr(self.node, "get_card_badge_text") else None
        if badge_text is not None:
            y = self.HEADER_H + 15.0 + row_idx * self.ROW_H
            lbl_badge = QLabel(badge_text)
            lbl_badge.setFixedSize(int(self.WIDTH - 24.0), 20)
            lbl_badge.setStyleSheet("color: #98c379; font-size: 11px; font-weight: bold; background: transparent; padding-left: 2px;")
            proxy_lbl = QGraphicsProxyWidget(self)
            proxy_lbl.setWidget(lbl_badge)
            proxy_lbl.setPos(12.0, y - 10.0)
            proxy_lbl.setZValue(5.0)
            self.proxies["_card_badge"] = proxy_lbl
            self._badge_label = lbl_badge
            row_idx += 1

        action_buttons = self.node.get_action_buttons() if hasattr(self.node, "get_action_buttons") else []
        for btn_spec in action_buttons:
            y = self.HEADER_H + 15.0 + row_idx * self.ROW_H
            btn_id = btn_spec.get("id", f"btn_{row_idx}")
            btn = QPushButton(tr(btn_spec.get("label", "Action")))
            btn.setFixedSize(int(self.WIDTH - 24.0), 24)
            btn.setToolTip(btn_spec.get("tooltip", ""))
            color = btn_spec.get("color", "#2e7d32")
            text_color = btn_spec.get("text_color", "#ffffff")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: {text_color};
                    font-weight: bold;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border: 1px solid rgba(255, 255, 255, 0.5);
                }}
            """)
            btn.clicked.connect(lambda checked=False, spec=btn_spec: self._handle_card_button_click(spec))
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(btn)
            proxy.setPos(12.0, y - 11.0)
            proxy.setZValue(5.0)
            self.proxies[btn_id] = proxy
            if btn_spec.get("action") == "bake":
                self.proxies["_btn_bake"] = proxy
            row_idx += 1

    def _handle_card_button_click(self, btn_spec: Dict[str, Any]) -> None:
        act = btn_spec.get("action", "")
        sc = self.scene()
        if act == "bake":
            if hasattr(sc, "request_bake"):
                sc.request_bake(self.node)
        elif act == "pick_color":
            r = float(self.node.param_values.get("r", 0.8))
            g = float(self.node.param_values.get("g", 0.8))
            b = float(self.node.param_values.get("b", 0.8))
            curr_qcol = QColor.fromRgbF(min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, b)))
            color = QColorDialog.getColor(curr_qcol, None, "Select Node Color")
            if color.isValid():
                new_r = round(color.redF(), 3)
                new_g = round(color.greenF(), 3)
                new_b = round(color.blueF(), 3)
                self.node.param_values["r"] = new_r
                self.node.param_values["g"] = new_g
                self.node.param_values["b"] = new_b
                for p_id, val in (("r", new_r), ("g", new_g), ("b", new_b)):
                    proxy = self.proxies.get(p_id)
                    if proxy is not None:
                        w = proxy.widget()
                        if isinstance(w, BlenderValueSlider):
                            w.blockSignals(True)
                            w.setValue(val)
                            w.blockSignals(False)
                self._update_action_buttons()
                if sc and hasattr(sc, "engine"):
                    sc.engine.mark_dirty(self.node.id)
                    sc.trigger_eval()
        elif act == "set_face":
            app = self._get_app_handle()
            if hasattr(self.node, "reference_from_selection"):
                msg, ok = self.node.reference_from_selection(app)
                if sc and hasattr(sc, "engine"):
                    sc.engine.mark_dirty(self.node.id)
                    sc.trigger_eval()
                self._update_badge()
        elif act == "clear_face":
            if hasattr(self.node, "clear_reference"):
                self.node.clear_reference()
                if sc and hasattr(sc, "engine"):
                    sc.engine.mark_dirty(self.node.id)
                    sc.trigger_eval()
                self._update_badge()
        elif hasattr(self.node, act):
            fn = getattr(self.node, act)
            if callable(fn):
                fn()
                if sc and hasattr(sc, "engine"):
                    sc.engine.mark_dirty(self.node.id)
                    sc.trigger_eval()
                self._update_badge()
                self._update_action_buttons()

    def _update_badge(self) -> None:
        if hasattr(self, "_badge_label") and self._badge_label is not None:
            if hasattr(self.node, "get_card_badge_text"):
                txt = self.node.get_card_badge_text() or ""
                self._badge_label.setText(txt)

    def _update_action_buttons(self) -> None:
        action_buttons = self.node.get_action_buttons() if hasattr(self.node, "get_action_buttons") else []
        for btn_spec in action_buttons:
            btn_id = btn_spec.get("id")
            proxy = self.proxies.get(btn_id)
            if proxy is not None:
                btn = proxy.widget()
                if isinstance(btn, QPushButton):
                    btn.setText(btn_spec.get("label", "Action"))
                    color = btn_spec.get("color", "#2e7d32")
                    text_color = btn_spec.get("text_color", "#ffffff")
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background: {color};
                            color: {text_color};
                            font-weight: bold;
                            border: 1px solid rgba(255, 255, 255, 0.2);
                            border-radius: 4px;
                            font-size: 11px;
                        }}
                        QPushButton:hover {{
                            border: 1px solid rgba(255, 255, 255, 0.5);
                        }}
                    """)

    def _get_app_handle(self) -> Any:
        sc = self.scene()
        if sc and hasattr(sc, "get_app") and callable(sc.get_app):
            app = sc.get_app()
            if app:
                return app
        try:
            from PySide6.QtWidgets import QApplication
            qapp = QApplication.instance()
            win = getattr(qapp, "_extension_app_handle", None)
            if win:
                return win
            for w in qapp.topLevelWidgets():
                if hasattr(w, "viewport") or hasattr(w, "scene"):
                    return w
                if hasattr(w, "_extension_app_handle"):
                    return w._extension_app_handle
        except Exception:
            pass
        return None

    def mousePressEvent(self, event) -> None:
        pos = event.pos()
        if pos.y() <= self.HEADER_H:
            if self.has_preview_eye and QRectF(self.WIDTH - 46.0, 4.0, 18.0, 20.0).contains(pos):
                self.toggle_preview()
                event.accept()
                return
            if QRectF(self.WIDTH - 24.0, 4.0, 18.0, 20.0).contains(pos):
                self.toggle_enable()
                event.accept()
                return
        super().mousePressEvent(event)

    def toggle_preview(self) -> None:
        self.node.is_preview_visible = not getattr(self.node, "is_preview_visible", True)
        self.update()
        sc = self.scene()
        if hasattr(sc, "trigger_eval"):
            sc.trigger_eval()

    def toggle_enable(self) -> None:
        self.node.is_enabled = not getattr(self.node, "is_enabled", True)
        self.node.is_dirty = True
        self.update()
        sc = self.scene()
        if sc and hasattr(sc, "engine"):
            sc.engine.mark_dirty(self.node.id)
            sc.trigger_eval()

    def _on_slider_changed(self, sid: str, v: Any) -> None:
        self.node.param_values[sid] = v
        self.node.is_dirty = True
        self.on_param_changed(self.node.id, sid, v)
        self._update_action_buttons()

    def update_slider_config(
        self,
        param_id: str,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        decimals: Optional[int] = None,
        step: Optional[float] = None,
    ) -> None:
        for in_spec in self.node.inputs:
            if in_spec.id == param_id:
                in_spec.min_val = min_val
                in_spec.max_val = max_val
                if decimals is not None:
                    in_spec.decimals = decimals
                if step is not None:
                    in_spec.step = step
                break
        proxy = self.proxies.get(param_id)
        if proxy is not None:
            w = proxy.widget()
            if isinstance(w, BlenderValueSlider):
                w.set_config(min_val=min_val, max_val=max_val, decimals=decimals, step=step)

    def set_param_value_from_inspector(self, param_id: str, value: Any) -> None:
        self.node.param_values[param_id] = value
        self.node.is_dirty = True
        proxy = self.proxies.get(param_id)
        if proxy is not None:
            w = proxy.widget()
            if isinstance(w, BlenderValueSlider):
                w.blockSignals(True)
                w.setValue(float(value))
                w.blockSignals(False)
            elif isinstance(w, QCheckBox):
                w.blockSignals(True)
                w.setChecked(bool(value))
                w.blockSignals(False)
            elif isinstance(w, QLineEdit):
                w.blockSignals(True)
                w.setText(str(value))
                w.blockSignals(False)
            elif isinstance(w, QComboBox):
                w.blockSignals(True)
                for i in range(w.count()):
                    t = w.itemText(i)
                    if t == str(value) or (isinstance(value, int) and t.startswith(f"{value}:")):
                        w.setCurrentIndex(i)
                        break
                w.blockSignals(False)
        self.on_param_changed(self.node.id, param_id, value)
        self._update_action_buttons()

    def set_custom_title(self, title: str) -> None:
        clean = title.strip()
        self.node.custom_title = clean if clean else None
        self.update()

    def retranslate_ui(self) -> None:
        self.setToolTip(tr(self.node.description or self.node.title))
        for in_spec in self.node.inputs:
            proxy = self.proxies.get(in_spec.id)
            if proxy is not None:
                w = proxy.widget()
                if isinstance(w, QCheckBox):
                    w.setText(tr(in_spec.label))
                elif isinstance(w, BlenderValueSlider):
                    w.update()
                elif isinstance(w, QComboBox) and in_spec.choices:
                    cur_idx = w.currentIndex()
                    w.blockSignals(True)
                    w.clear()
                    w.addItems([tr(str(c)) for c in in_spec.choices])
                    if 0 <= cur_idx < len(in_spec.choices):
                        w.setCurrentIndex(cur_idx)
                    w.blockSignals(False)
        action_buttons = self.node.get_action_buttons() if hasattr(self.node, "get_action_buttons") else []
        for btn_spec in action_buttons:
            btn_id = btn_spec.get("id")
            proxy = self.proxies.get(btn_id)
            if proxy is not None:
                btn = proxy.widget()
                if isinstance(btn, QPushButton):
                    btn.setText(tr(btn_spec.get("label", "Action")))
        if hasattr(self, "_badge_label") and self._badge_label is not None:
            if hasattr(self.node, "get_card_badge_text"):
                txt = self.node.get_card_badge_text() or ""
                self._badge_label.setText(tr(txt))
        for sock in self.input_sockets.values():
            sock.retranslate_ui()
        for sock in self.output_sockets.values():
            sock.retranslate_ui()
        self.update()

    def _create_inline_widget(self, spec: InputSpec) -> Tuple[Optional[QWidget], float]:
        val = self.node.param_values.get(spec.id, spec.default)
        full_w = int(self.WIDTH - 24.0)

        if spec.choices is not None and len(spec.choices) > 0:
            combo = NodeComboBox()
            combo.addItems([tr(str(c)) for c in spec.choices])

            current_str = str(val)
            match_idx = -1
            for idx, c in enumerate(spec.choices):
                cstr = str(c)
                if cstr == current_str or (spec.type == SocketType.INT and cstr.startswith(f"{val}:")):
                    match_idx = idx
                    break
            if match_idx >= 0:
                combo.setCurrentIndex(match_idx)
            elif isinstance(val, int) and 0 <= val < len(spec.choices):
                combo.setCurrentIndex(val)

            combo_w = 125
            combo.setFixedSize(combo_w, 22)
            combo.setStyleSheet("""
                QComboBox {
                    background: #2b303c;
                    color: #eceff4;
                    border: 1px solid #434c5e;
                    border-radius: 4px;
                    font-size: 11px;
                    padding: 1px 18px 1px 6px;
                }
                QComboBox:hover {
                    border-color: #5e81ac;
                    background: #353b49;
                }
                QComboBox::drop-down {
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 16px;
                    border-left: 1px solid #434c5e;
                }
                QComboBox::down-arrow {
                    width: 0;
                    height: 0;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 5px solid #d8dee9;
                }
                QComboBox QAbstractItemView {
                    background-color: #1e222b;
                    color: #eceff4;
                    border: 1px solid #5e81ac;
                    border-radius: 4px;
                    selection-background-color: #3875d7;
                    selection-color: #ffffff;
                    outline: none;
                    padding: 3px;
                }
                QComboBox QAbstractItemView::item {
                    min-height: 22px;
                    padding: 2px 6px;
                }
                QComboBox QAbstractItemView::item:selected {
                    background-color: #3875d7;
                    color: #ffffff;
                }
            """)
            if combo.view() is not None:
                combo.view().setMinimumWidth(combo_w + 30)

            def _on_combo_changed(idx_val):
                chosen_idx = combo.currentIndex()
                if spec.type == SocketType.INT:
                    self.on_param_changed(self.node.id, spec.id, chosen_idx)
                else:
                    self.on_param_changed(self.node.id, spec.id, str(spec.choices[chosen_idx]))

            combo.currentIndexChanged.connect(_on_combo_changed)
            x_offset = self.WIDTH - combo_w - 8.0
            return combo, x_offset

        if spec.type in (SocketType.FLOAT, SocketType.INT):
            slider = BlenderValueSlider(
                label=spec.label,
                value=float(val) if val is not None else 0.0,
                min_val=spec.min_val,
                max_val=spec.max_val,
                step=spec.step,
                decimals=getattr(spec, "decimals", None),
                is_int=(spec.type == SocketType.INT),
                width=full_w,
            )
            slider.valueChanged.connect(lambda v, sid=spec.id: self._on_slider_changed(sid, v))
            return slider, 12.0

        if spec.type == SocketType.BOOL:
            cb = QCheckBox(tr(spec.label))
            cb.setChecked(bool(val))
            base_dir = os.path.dirname(os.path.abspath(__file__))
            chk_icon = os.path.join(base_dir, "icons", "checkmark.png").replace("\\", "/")
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: #d8dee9;
                    font-size: 11px;
                    background: transparent;
                    spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: 14px;
                    height: 14px;
                    border: 1px solid #7e8798;
                    border-radius: 3px;
                    background: #252932;
                }}
                QCheckBox::indicator:hover {{
                    border-color: #88c0d0;
                    background: #2e3440;
                }}
                QCheckBox::indicator:checked {{
                    background: #3875d7;
                    border-color: #81a1c1;
                    image: url("{chk_icon}");
                }}
            """)
            cb.toggled.connect(lambda v, sid=spec.id: self.on_param_changed(self.node.id, sid, bool(v)))
            return cb, 14.0

        if spec.type == SocketType.STRING or (spec.type == SocketType.ANY and isinstance(val, str) and not spec.hide_widget):
            half_w = int(self.WIDTH - 100.0)
            le = QLineEdit(str(val) if val is not None else "")
            le.setFixedSize(half_w, 22)
            le.setStyleSheet(
                "background: #2b303b; color: #e5e9f0; border: 1px solid #3e4452;"
                "border-radius: 4px; font-size: 11px; padding: 1px 5px;"
            )
            le.textChanged.connect(lambda v, sid=spec.id: self.on_param_changed(self.node.id, sid, v))
            return le, self.WIDTH - half_w - 8.0

        return None, 12.0

    def set_socket_connected(self, input_id: str, connected: bool) -> None:
        proxy = self.proxies.get(input_id)
        if proxy is not None:
            proxy.setVisible(not connected)
            self.update()
        if self.node.type_id == "input.panel" and input_id == "data":
            self.update_panel_display()

    def boundingRect(self) -> QRectF:
        return QRectF(-8.0, -4.0, self.WIDTH + 16.0, self.height + 8.0)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            p = self.pos()
            self.node.pos = (p.x(), p.y())
            sc = self.scene()
            if hasattr(sc, "update_wires_for_node"):
                sc.update_wires_for_node(self.node.id)
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body_rect = QRectF(0.0, 0.0, self.WIDTH, self.height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(33, 37, 45, 245)))
        painter.drawRoundedRect(body_rect, 7.0, 7.0)

        hr, hg, hb = self.node.header_color
        header_path = QPainterPath()
        header_path.addRoundedRect(QRectF(0.0, 0.0, self.WIDTH, self.HEADER_H), 7.0, 7.0)
        painter.setBrush(QBrush(QColor(hr, hg, hb)))
        painter.drawPath(header_path)

        if self.node.error_message:
            border_pen = QPen(QColor(235, 77, 75), 2.2)
            self.setToolTip(self.node.error_message)
        elif self.isSelected():
            border_pen = QPen(QColor(246, 185, 59), 2.0)
            self.setToolTip(tr(self.node.description or self.node.title))
        else:
            border_pen = QPen(QColor(58, 64, 76), 1.2)
            self.setToolTip(tr(self.node.description or self.node.title))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(border_pen)
        painter.drawRoundedRect(body_rect, 7.0, 7.0)

        title_w = self.WIDTH - 52.0 if self.has_preview_eye else self.WIDTH - 30.0
        painter.setPen(QColor(242, 245, 250))
        painter.setFont(QFont("Sans Serif", 9, QFont.Weight.Bold))
        display_title = getattr(self.node, "custom_title", None) or tr(self.node.title)
        painter.drawText(
            QRectF(12.0, 0.0, title_w, self.HEADER_H),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            display_title,
        )

        power_rect = QRectF(self.WIDTH - 24.0, 4.0, 18.0, 20.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 95)))
        painter.drawRoundedRect(power_rect, 3.0, 3.0)

        if self.has_preview_eye:
            eye_rect = QRectF(self.WIDTH - 46.0, 4.0, 18.0, 20.0)
            painter.drawRoundedRect(eye_rect, 3.0, 3.0)
            is_prev = getattr(self.node, "is_preview_visible", True)
            painter.setFont(QFont("Segoe UI Symbol", 8))
            if is_prev:
                painter.setPen(QColor(168, 216, 234))
                painter.drawText(eye_rect, Qt.AlignmentFlag.AlignCenter, "👁")
            else:
                painter.setPen(QColor(115, 125, 140))
                painter.drawText(eye_rect, Qt.AlignmentFlag.AlignCenter, "⊘")

        is_en = getattr(self.node, "is_enabled", True)
        painter.setFont(QFont("Segoe UI Symbol", 8))
        if is_en:
            painter.setPen(QColor(85, 239, 196))
            painter.drawText(power_rect, Qt.AlignmentFlag.AlignCenter, "⏻")
        else:
            painter.setPen(QColor(231, 76, 60))
            painter.drawText(power_rect, Qt.AlignmentFlag.AlignCenter, "⏻")

        if not is_en:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(18, 20, 24, 185)))
            painter.drawRoundedRect(body_rect, 7.0, 7.0)

            painter.setPen(QPen(QColor(150, 150, 150, 90), 1.0, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(body_rect, 7.0, 7.0)

            painter.setFont(QFont("Sans Serif", 7, QFont.Weight.Bold))
            painter.setPen(QColor(231, 76, 60, 220))
            painter.drawText(
                QRectF(12.0, self.height - 18.0, self.WIDTH - 24.0, 14.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                tr("MUTED"),
            )

        painter.setFont(QFont("Sans Serif", 8))
        painter.setPen(QColor(205, 212, 222))

        for out_spec in self.node.outputs:
            y = self._output_row_y[out_spec.id]
            painter.drawText(
                QRectF(12.0, y - 10.0, self.WIDTH - 24.0, 20.0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                tr(out_spec.label),
            )

        for in_spec in self.node.inputs:
            y = self._input_row_y[in_spec.id]
            proxy = self.proxies.get(in_spec.id)
            if proxy is not None and proxy.isVisible():
                if in_spec.type in (SocketType.FLOAT, SocketType.INT, SocketType.BOOL):
                    continue
                painter.drawText(
                    QRectF(12.0, y - 10.0, 78.0, 20.0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    tr(in_spec.label),
                )
            else:
                painter.drawText(
                    QRectF(12.0, y - 10.0, self.WIDTH - 24.0, 20.0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    tr(in_spec.label),
                )


# ============================================================================
# QUICK SEARCH PALETTE DIALOG
# ============================================================================
class NodeSearchPopup(QDialog):
    def __init__(self, parent: QWidget, on_pick: Callable[[str], None]) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.on_pick = on_pick
        self.setFixedSize(290, 330)
        self.setStyleSheet("background: #21252b; color: #eceff4; border: 1px solid #4c566a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("🔍 Search nodes (type & press Enter)..."))
        self.search_box.setStyleSheet("background: #282c34; padding: 5px; border: 1px solid #3b4252;")
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("background: #1e222a; border: none;")

        layout.addWidget(self.search_box)
        layout.addWidget(self.list_widget)

        self.search_box.textChanged.connect(self._populate)
        self.search_box.returnPressed.connect(self._accept_current)
        self.list_widget.itemActivated.connect(lambda item: self._choose(item))
        self._populate("")

    def _populate(self, query: str) -> None:
        self.list_widget.clear()
        q = query.strip().lower()
        for type_id, cls in sorted(NODE_REGISTRY.items(), key=lambda kv: (kv[1].category, kv[1].title)):
            tr_cat = tr(cls.category)
            tr_title = tr(cls.title)
            label = f"[{tr_cat}]  {tr_title}"
            if not q or q in label.lower() or q in type_id.lower() or q in cls.title.lower() or q in cls.category.lower():
                item = QListWidgetItem(label)
                item.setIcon(get_node_icon(type_id, is_dark=True))
                item.setData(Qt.ItemDataRole.UserRole, type_id)
                self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _accept_current(self) -> None:
        item = self.list_widget.currentItem()
        if item:
            self._choose(item)

    def _choose(self, item: QListWidgetItem) -> None:
        type_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if type_id:
            self.on_pick(type_id)


# ============================================================================
# GRAPH SCENE & VIEWPORT CANVAS
# ============================================================================
class NodeCanvasScene(QGraphicsScene):
    def __init__(
        self,
        engine: GraphEngine,
        trigger_eval: Callable[[], None],
        on_bake: Optional[Callable[[], None]] = None,
        get_app: Optional[Callable[[], Any]] = None,
    ) -> None:
        super().__init__(-5000, -5000, 10000, 10000)
        self.engine = engine
        self.trigger_eval = trigger_eval
        self.on_bake = on_bake
        self.get_app = get_app
        self.node_items: Dict[str, NodeItem] = {}
        self.wire_items: List[WireItem] = []
        self._temp_wire: Optional[WireItem] = None

    def request_bake(self, node: Optional[BaseNode] = None) -> None:
        if self.on_bake:
            try:
                self.on_bake(node.id if node else None)
            except TypeError:
                self.on_bake()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(24, 26, 31))
        step = 24
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        pen = QPen(QColor(52, 58, 70), 1.6)
        painter.setPen(pen)
        for x in range(left, int(rect.right()), step):
            for y in range(top, int(rect.bottom()), step):
                painter.drawPoint(x, y)

    def retranslate_ui(self) -> None:
        for it in self.node_items.values():
            it.retranslate_ui()

    def spawn_node(self, type_id: str, pos: Tuple[float, float]) -> NodeItem:
        node = self.engine.add_node(type_id, pos=pos)
        item = NodeItem(node, self._on_node_param_edited)
        self.addItem(item)
        self.node_items[node.id] = item
        self.trigger_eval()
        return item

    def rebuild_from_engine(self) -> None:
        self.clear()
        self.node_items.clear()
        self.wire_items.clear()
        for node in self.engine.nodes.values():
            item = NodeItem(node, self._on_node_param_edited)
            self.addItem(item)
            self.node_items[node.id] = item
        for w in self.engine.wires:
            self._add_wire_item(w)
        self.trigger_eval()

    def _on_node_param_edited(self, node_id: str, input_id: str, value: object) -> None:
        self.engine.update_node_param(node_id, input_id, value)
        node_item = self.node_items.get(node_id)
        if node_item:
            node_item._update_badge()
            node_item._update_action_buttons()
        self.trigger_eval()

    def _add_wire_item(self, w: Wire) -> None:
        s_item = self.node_items.get(w.src_node)
        d_item = self.node_items.get(w.dst_node)
        if not s_item or not d_item:
            return
        s_sock = s_item.output_sockets.get(w.src_socket)
        d_sock = d_item.input_sockets.get(w.dst_socket)
        if not s_sock or not d_sock:
            return
        wi = WireItem(s_sock, d_sock, wire_model=w)
        self.addItem(wi)
        self.wire_items.append(wi)
        d_item.set_socket_connected(w.dst_socket, True)

    def update_wires_for_node(self, node_id: str) -> None:
        for wi in self.wire_items:
            if wi.wire_model and (wi.wire_model.src_node == node_id or wi.wire_model.dst_node == node_id):
                wi.update_path()

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        if isinstance(item, SocketItem) and event.button() == Qt.MouseButton.LeftButton:
            if item.is_output:
                self._temp_wire = WireItem(item)
                self.addItem(self._temp_wire)
                event.accept()
                return
            else:
                for wi in list(self.wire_items):
                    if wi.dst_sock == item and wi.wire_model:
                        src_sock = wi.src_sock
                        self.engine.disconnect(wi.wire_model)
                        self.removeItem(wi)
                        self.wire_items.remove(wi)
                        has_other_wires = any(
                            w.dst_node == item.node_item.node.id and w.dst_socket == item.socket_id
                            for w in self.engine.wires
                        )
                        item.node_item.set_socket_connected(item.socket_id, has_other_wires)
                        self._temp_wire = WireItem(src_sock)
                        self._temp_wire.drag_pos = event.scenePos()
                        self._temp_wire.update_path()
                        self.addItem(self._temp_wire)
                        self.trigger_eval()
                        event.accept()
                        return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._temp_wire is not None:
            self._temp_wire.drag_pos = event.scenePos()
            self._temp_wire.update_path()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._temp_wire is not None:
            src_sock = self._temp_wire.src_sock
            self.removeItem(self._temp_wire)
            self._temp_wire = None

            best_sock: Optional[SocketItem] = None
            best_dist = 18.0
            for n_item in self.node_items.values():
                for in_sock in n_item.input_sockets.values():
                    d = (in_sock.scenePos() - event.scenePos()).manhattanLength()
                    if d < best_dist:
                        best_dist = d
                        best_sock = in_sock

            if best_sock is not None:
                mods = event.modifiers()
                try:
                    mods = mods | QApplication.keyboardModifiers()
                except Exception:
                    pass
                shift_held = bool(mods & Qt.KeyboardModifier.ShiftModifier)

                if not shift_held:
                    for wi in list(self.wire_items):
                        if wi.dst_sock == best_sock and wi.wire_model:
                            self.engine.disconnect(wi.wire_model)
                            self.removeItem(wi)
                            self.wire_items.remove(wi)

                    w = self.engine.connect(
                        src_sock.node_item.node.id,
                        src_sock.socket_id,
                        best_sock.node_item.node.id,
                        best_sock.socket_id,
                        replace_existing=True,
                    )
                    if w is not None:
                        self._add_wire_item(w)
                        self.trigger_eval()
                else:
                    w = self.engine.connect(
                        src_sock.node_item.node.id,
                        src_sock.socket_id,
                        best_sock.node_item.node.id,
                        best_sock.socket_id,
                        replace_existing=False,
                    )
                    if w is not None:
                        if not any(wi.wire_model == w for wi in self.wire_items):
                            self._add_wire_item(w)
                        self.trigger_eval()

            event.accept()
            return
        super().mouseReleaseEvent(event)

    def delete_selected_nodes(self) -> None:
        selected = [it for it in self.selectedItems() if isinstance(it, NodeItem)]
        if not selected:
            return
        for n_item in selected:
            nid = n_item.node.id
            for wi in list(self.wire_items):
                if wi.wire_model and (wi.wire_model.src_node == nid or wi.wire_model.dst_node == nid):
                    dst_sock = wi.dst_sock
                    self.removeItem(wi)
                    self.wire_items.remove(wi)
                    if dst_sock and dst_sock.node_item != n_item:
                        has_remaining = any(
                            w.dst_node == dst_sock.node_item.node.id and w.dst_socket == dst_sock.socket_id
                            for w in self.engine.wires
                            if w != wi.wire_model
                        )
                        dst_sock.node_item.set_socket_connected(dst_sock.socket_id, has_remaining)
            self.engine.remove_node(nid)
            self.removeItem(n_item)
            self.node_items.pop(nid, None)
        self.trigger_eval()


class NodeCanvasView(QGraphicsView):
    def __init__(self, scene: NodeCanvasScene) -> None:
        super().__init__(scene)
        self.canvas_scene = scene
        self.parent_editor: Optional[Any] = None
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAcceptDrops(True)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._panning = False
        self._pan_start = QPointF()
        self._cutting: bool = False
        self._cut_points: List[QPointF] = []
        self._cut_item: Optional[QGraphicsPathItem] = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        curr_scale = self.transform().m11()
        if (0.2 <= curr_scale <= 3.0) or (curr_scale < 0.2 and factor > 1) or (curr_scale > 3.0 and factor < 1):
            self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if event.button() == Qt.MouseButton.LeftButton and ctrl:
            item = self.itemAt(event.pos())
            if item is None or isinstance(item, (WireItem, QGraphicsPathItem)):
                self._cutting = True
                sp = self.mapToScene(event.pos())
                self._cut_points = [sp, sp]
                self._update_cut_path()
                self.setCursor(Qt.CursorShape.CrossCursor)
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._cutting:
            sp = self.mapToScene(event.pos())
            self._cut_points.append(sp)
            self._update_cut_path()
            event.accept()
            return

        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._cutting and event.button() == Qt.MouseButton.LeftButton:
            self._cutting = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._apply_cutting_cut()
            if self._cut_item and self._cut_item.scene():
                self.canvas_scene.removeItem(self._cut_item)
            self._cut_item = None
            self._cut_points = []
            event.accept()
            return

        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_cut_path(self) -> None:
        if len(self._cut_points) < 2:
            return
        path = QPainterPath(self._cut_points[0])
        for pt in self._cut_points[1:]:
            path.lineTo(pt)
        if self._cut_item is None:
            self._cut_item = QGraphicsPathItem()
            pen = QPen(QColor("#e06c75"), 2.0, Qt.PenStyle.DashLine)
            self._cut_item.setPen(pen)
            self._cut_item.setZValue(100)
            self.canvas_scene.addItem(self._cut_item)
        self._cut_item.setPath(path)

    def _apply_cutting_cut(self) -> None:
        if len(self._cut_points) < 2:
            return
        cut_path = QPainterPath(self._cut_points[0])
        for pt in self._cut_points[1:]:
            cut_path.lineTo(pt)
        stroker = QPainterPathStroker()
        stroker.setWidth(8.0)
        stroke_poly = stroker.createStroke(cut_path)

        wires_to_remove = []
        for wi in list(self.canvas_scene.wire_items):
            if stroke_poly.intersects(wi.path()):
                wires_to_remove.append(wi)

        if not wires_to_remove:
            return

        for wi in wires_to_remove:
            dst_sock = wi.dst_sock
            if wi.wire_model:
                self.canvas_scene.engine.disconnect(wi.wire_model)
            self.canvas_scene.removeItem(wi)
            if wi in self.canvas_scene.wire_items:
                self.canvas_scene.wire_items.remove(wi)
            if dst_sock and hasattr(dst_sock, 'node_item'):
                has_remaining = any(
                    w.dst_node == dst_sock.node_item.node.id and w.dst_socket == dst_sock.socket_id
                    for w in self.canvas_scene.engine.wires
                )
                dst_sock.node_item.set_socket_connected(dst_sock.socket_id, has_remaining)

        self.canvas_scene.trigger_eval()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        item = self.itemAt(event.pos())
        if item is None:
            self.open_search_popup(event.pos())
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat("application/x-ingetrazo-node"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat("application/x-ingetrazo-node"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat("application/x-ingetrazo-node"):
            raw_tid = event.mimeData().data("application/x-ingetrazo-node")
            type_id = bytes(raw_tid).decode("utf-8")
            pt = event.position().toPoint() if hasattr(event, "position") else event.pos()
            scene_pt = self.mapToScene(pt)
            item = self.canvas_scene.spawn_node(type_id, (scene_pt.x(), scene_pt.y()))
            self.canvas_scene.clearSelection()
            item.setSelected(True)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        item = self.itemAt(event.pos())
        node_item = None
        curr = item
        while curr is not None:
            if isinstance(curr, NodeItem):
                node_item = curr
                break
            curr = curr.parentItem()

        if node_item is not None:
            self._open_node_context_menu(node_item, event.globalPos())
        else:
            self._open_canvas_context_menu(event.pos(), event.globalPos())
        event.accept()

    def _open_node_context_menu(self, node_item: NodeItem, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #21252b;
                color: #abb2bf;
                border: 1px solid #3e4451;
                border-radius: 6px;
                padding: 4px;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c313a;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #3e4451;
                margin: 4px 6px;
            }
        """)

        if not node_item.isSelected():
            self.canvas_scene.clearSelection()
            node_item.setSelected(True)

        node = node_item.node
        is_en = getattr(node, "is_enabled", True)
        is_prev = getattr(node, "is_preview_visible", True)

        toggle_label = tr("Disable Node (Mute)") if is_en else tr("Enable Node")
        act_toggle = menu.addAction(f"⏻ {toggle_label} (D)")
        act_toggle.triggered.connect(self.toggle_selected_enable)

        prev_label = tr("Hide Viewport Preview") if is_prev else tr("Show Viewport Preview")
        act_prev = menu.addAction(f"👁 {prev_label} (V)")
        act_prev.triggered.connect(self.toggle_selected_preview)

        if node.is_output_node or any(out.type == SocketType.MESH for out in node.outputs):
            act_bake = menu.addAction(tr("🥐 Bake This Node to Scene"))
            act_bake.triggered.connect(lambda: self.canvas_scene.request_bake(node))

        menu.addSeparator()

        act_copy = menu.addAction(tr("📄 Copy Node(s) (Ctrl+C)"))
        act_copy.triggered.connect(self.copy_selected)

        act_cut = menu.addAction(tr("✂ Cut Node(s) (Ctrl+X)"))
        act_cut.triggered.connect(self.cut_selected)

        act_dup = menu.addAction(tr("📑 Duplicate Node(s) (Ctrl+D)"))
        act_dup.triggered.connect(self.duplicate_selected)

        act_del = menu.addAction(tr("🗑 Delete Node(s) (Del)"))
        act_del.triggered.connect(self.delete_selected)

        menu.addSeparator()

        act_up = menu.addAction(tr("🎯 Select Connected Upstream"))
        act_up.triggered.connect(lambda: self._select_connected(node.id, upstream=True))

        act_down = menu.addAction(tr("🎯 Select Connected Downstream"))
        act_down.triggered.connect(lambda: self._select_connected(node.id, upstream=False))

        menu.exec(global_pos)

    def _open_canvas_context_menu(self, view_pt: QPoint, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #21252b;
                color: #abb2bf;
                border: 1px solid #3e4451;
                border-radius: 6px;
                padding: 4px;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c313a;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #3e4451;
                margin: 4px 6px;
            }
        """)

        scene_pt = self.mapToScene(view_pt)

        act_add = menu.addAction(tr("➕ Add Node... (Space / Tab)"))
        act_add.triggered.connect(lambda: self.open_search_popup(view_pt))

        cb_text = QApplication.clipboard().text()
        has_nodes = bool(cb_text and cb_text.startswith("{") and "nodes" in cb_text)

        act_paste = menu.addAction(tr("📋 Paste Nodes (Ctrl+V)"))
        act_paste.setEnabled(has_nodes)
        act_paste.triggered.connect(lambda: self.paste_at_pos(scene_pt))

        menu.addSeparator()

        act_sel_all = menu.addAction(tr("Select All (Ctrl+A)"))
        act_sel_all.triggered.connect(self.select_all)

        if self.parent_editor is not None:
            act_reload = menu.addAction(tr("🔄 Reload Nodes Catalog"))
            act_reload.triggered.connect(self.parent_editor._hot_reload_nodes)

        act_fit = menu.addAction(tr("🔎 Fit All in View (F)"))
        act_fit.triggered.connect(self.fit_view)

        menu.exec(global_pos)

    def copy_selected(self) -> None:
        selected_nodes = [it.node.id for it in self.canvas_scene.selectedItems() if isinstance(it, NodeItem)]
        if not selected_nodes:
            return
        json_str = self.canvas_scene.engine.copy_nodes(selected_nodes)
        QApplication.clipboard().setText(json_str)

    def cut_selected(self) -> None:
        self.copy_selected()
        self.delete_selected()

    def paste_at_pos(self, scene_pt: QPointF) -> None:
        import json
        text = QApplication.clipboard().text()
        if not text or not text.startswith("{"):
            return
        try:
            data = json.loads(text)
            nodes = data.get("nodes", [])
            if not nodes:
                return
            min_x = min(float(n.get("pos", [0, 0])[0]) for n in nodes)
            min_y = min(float(n.get("pos", [0, 0])[1]) for n in nodes)
            offset = (scene_pt.x() - min_x, scene_pt.y() - min_y)
        except Exception:
            offset = (40.0, 40.0)

        new_nodes = self.canvas_scene.engine.paste_nodes(text, offset=offset)
        if not new_nodes:
            return

        self.canvas_scene.clearSelection()
        new_ids = {n.id for n in new_nodes}

        for node in new_nodes:
            item = NodeItem(node, self.canvas_scene._on_node_param_edited)
            self.canvas_scene.addItem(item)
            self.canvas_scene.node_items[node.id] = item
            item.setSelected(True)

        for w in self.canvas_scene.engine.wires:
            if w.src_node in new_ids or w.dst_node in new_ids:
                if not any(wi.wire_model == w for wi in self.canvas_scene.wire_items):
                    self.canvas_scene._add_wire_item(w)

        self.canvas_scene.trigger_eval()

    def paste_at_cursor(self) -> None:
        cursor_pos = self.mapFromGlobal(QCursor.pos())
        scene_pos = self.mapToScene(cursor_pos)
        self.paste_at_pos(scene_pos)

    def duplicate_selected(self) -> None:
        selected_items = [it for it in self.canvas_scene.selectedItems() if isinstance(it, NodeItem)]
        if not selected_items:
            return
        selected_ids = [it.node.id for it in selected_items]
        new_nodes = self.canvas_scene.engine.duplicate_nodes(selected_ids, offset=(40.0, 40.0))
        if not new_nodes:
            return

        self.canvas_scene.clearSelection()
        new_ids = {n.id for n in new_nodes}

        for node in new_nodes:
            item = NodeItem(node, self.canvas_scene._on_node_param_edited)
            self.canvas_scene.addItem(item)
            self.canvas_scene.node_items[node.id] = item
            item.setSelected(True)

        for w in self.canvas_scene.engine.wires:
            if w.src_node in new_ids or w.dst_node in new_ids:
                if not any(wi.wire_model == w for wi in self.canvas_scene.wire_items):
                    self.canvas_scene._add_wire_item(w)

        self.canvas_scene.trigger_eval()

    def delete_selected(self) -> None:
        self.canvas_scene.delete_selected_nodes()

    def select_all(self) -> None:
        for it in self.canvas_scene.node_items.values():
            it.setSelected(True)

    def toggle_selected_enable(self) -> None:
        selected_items = [it for it in self.canvas_scene.selectedItems() if isinstance(it, NodeItem)]
        if not selected_items:
            return
        target_state = not getattr(selected_items[0].node, "is_enabled", True)
        for it in selected_items:
            it.node.is_enabled = target_state
            it.node.is_dirty = True
            it.update()
            if hasattr(self.canvas_scene, "engine"):
                self.canvas_scene.engine.mark_dirty(it.node.id)
        self.canvas_scene.trigger_eval()

    def toggle_selected_preview(self) -> None:
        selected_items = [it for it in self.canvas_scene.selectedItems() if isinstance(it, NodeItem)]
        if not selected_items:
            return
        target_state = not getattr(selected_items[0].node, "is_preview_visible", True)
        for it in selected_items:
            it.node.is_preview_visible = target_state
            it.update()
        self.canvas_scene.trigger_eval()

    def fit_view(self) -> None:
        rect = self.canvas_scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def _select_connected(self, start_node_id: str, upstream: bool = True) -> None:
        queue = [start_node_id]
        visited = set()
        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            for w in self.canvas_scene.engine.wires:
                if upstream and w.dst_node == curr:
                    queue.append(w.src_node)
                elif not upstream and w.src_node == curr:
                    queue.append(w.dst_node)

        for nid in visited:
            it = self.canvas_scene.node_items.get(nid)
            if it:
                it.setSelected(True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if isinstance(self.scene().focusItem(), QGraphicsProxyWidget):
            super().keyPressEvent(event)
            return

        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if ctrl and event.key() == Qt.Key.Key_C:
            self.copy_selected()
            event.accept()
            return
        if ctrl and event.key() == Qt.Key.Key_V:
            self.paste_at_cursor()
            event.accept()
            return
        if ctrl and event.key() == Qt.Key.Key_D:
            self.duplicate_selected()
            event.accept()
            return
        if ctrl and event.key() == Qt.Key.Key_X:
            self.cut_selected()
            event.accept()
            return
        if ctrl and event.key() == Qt.Key.Key_A:
            self.select_all()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_D, Qt.Key.Key_M) and not ctrl:
            self.toggle_selected_enable()
            event.accept()
            return

        if event.key() == Qt.Key.Key_V and not ctrl:
            self.toggle_selected_preview()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_F, Qt.Key.Key_Home) and not ctrl:
            self.fit_view()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return

        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Tab):
            center = self.viewport().rect().center()
            self.open_search_popup(center)
            event.accept()
            return

        super().keyPressEvent(event)

    def open_search_popup(self, view_pt) -> None:
        scene_pt = self.mapToScene(view_pt)
        global_pt = self.viewport().mapToGlobal(view_pt)
        popup = NodeSearchPopup(
            self,
            on_pick=lambda tid: self.canvas_scene.spawn_node(tid, (scene_pt.x(), scene_pt.y())),
        )
        popup.move(global_pt)
        popup.show()
        popup.search_box.setFocus()


# ============================================================================
# COLLAPSIBLE INSPECTOR SPLITTER & CENTER PILL HANDLE
# ============================================================================
class InspectorSplitterHandle(QSplitterHandle):
    """Splitter handle featuring a persistent center pill button to collapse/expand properties."""

    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self.btn = QToolButton(self)
        self.btn.setFixedSize(16, 56)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setText("◀")
        self.btn.setToolTip("Expand Node Properties Panel")
        self.btn.setStyleSheet("""
            QToolButton {
                background: #282c34;
                color: #88c0d0;
                border: 1px solid #3b4252;
                border-radius: 4px;
                font-size: 9px;
                font-weight: bold;
                padding: 0px;
            }
            QToolButton:hover {
                background: #3e4451;
                color: #ffffff;
                border: 1px solid #61afef;
            }
            QToolButton:pressed {
                background: #61afef;
                color: #1e2227;
            }
        """)
        self.btn.clicked.connect(self._on_btn_clicked)

    def _on_btn_clicked(self) -> None:
        sp = self.splitter()
        if sp is None:
            return
        if sp.is_collapsed:
            sp.user_expand()
            p = sp.parent()
            while p is not None:
                if hasattr(p, "inspector") and hasattr(p, "scene"):
                    selected = [it for it in p.scene.selectedItems() if isinstance(it, NodeItem)]
                    if len(selected) == 1:
                        p.inspector.populate(selected[0].node, selected[0], p.scene)
                    elif len(selected) > 1:
                        p.inspector.show_multiple(len(selected))
                    else:
                        p.inspector.clear_and_show_placeholder()
                    break
                p = p.parent()
        else:
            sp.user_collapse()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.btn.move(0, max(0, (self.height() - self.btn.height()) // 2))

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1e2227"))
        painter.setPen(QColor("#282c34"))
        painter.drawLine(0, 0, 0, self.height())
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.end()


class InspectorSplitter(QSplitter):
    """Collapsible splitter managing canvas view and node properties panel."""

    def __init__(self, orientation: Qt.Orientation, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(16)
        self.is_collapsed: bool = True
        self.user_collapsed: bool = False  # Track explicit user collapse
        self._saved_size: int = 310
        self._handle: Optional[InspectorSplitterHandle] = None
        self.setChildrenCollapsible(True)
        self.splitterMoved.connect(self._on_splitter_moved)

    def createHandle(self) -> QSplitterHandle:
        h = InspectorSplitterHandle(self.orientation(), self)
        self._handle = h
        return h

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        cur_sizes = self.sizes()
        if len(cur_sizes) > 1:
            w = cur_sizes[1]
            if w <= 10:
                self.is_collapsed = True
                self.user_collapsed = True
                if self._handle:
                    self._handle.btn.setText("◀")
                    self._handle.btn.setToolTip("Expand Node Properties Panel")
            else:
                self.is_collapsed = False
                self.user_collapsed = False
                self._saved_size = w
                if self._handle:
                    self._handle.btn.setText("▶")
                    self._handle.btn.setToolTip("Collapse Node Properties Panel")

    def user_collapse(self) -> None:
        self.user_collapsed = True
        self.collapse_panel()

    def user_expand(self) -> None:
        self.user_collapsed = False
        self.expand_panel()

    def collapse_panel(self) -> None:
        cur_sizes = self.sizes()
        if len(cur_sizes) > 1 and cur_sizes[1] > 50:
            self._saved_size = cur_sizes[1]
        self.setSizes([max(100, self.width()), 0])
        self.is_collapsed = True
        if self._handle:
            self._handle.btn.setText("◀")
            self._handle.btn.setToolTip("Expand Node Properties Panel")

    def expand_panel(self) -> None:
        w = max(280, self._saved_size)
        self.is_collapsed = False
        self.setSizes([max(100, self.width() - w), w])
        if self._handle:
            self._handle.btn.setText("▶")
            self._handle.btn.setToolTip("Collapse Node Properties Panel")


# ============================================================================
# COMPACT ZERO-OVERFLOW INSPECTOR CONTENT CONTAINER
# ============================================================================
class _InspectorContentWidget(QWidget):
    """Content widget that never enforces a minimum width on QScrollArea."""
    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        return QSize(0, super().sizeHint().height())


# ============================================================================
# NODE PROPERTY INSPECTOR PANEL (RIGHT SIDEBAR)
# ============================================================================
class NodeInspectorPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_node: Optional[BaseNode] = None
        self.current_node_item: Optional[NodeItem] = None
        self.current_scene: Optional[NodeCanvasScene] = None
        self._syncing: bool = False

        self.setMinimumWidth(0)
        self.setMaximumWidth(420)

        self._setup_ui()
        self._setup_styling()
        self.clear_and_show_placeholder()

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header_bar = QWidget()
        header_bar.setObjectName("inspector_header")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(10, 6, 6, 6)
        header_layout.setSpacing(6)

        lbl_title = QLabel(tr("📋 Node Properties"))
        lbl_title.setObjectName("inspector_title")
        lbl_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header_layout.addWidget(lbl_title, 1)
        self.lbl_title = lbl_title

        btn_close = QPushButton("✕")
        btn_close.setObjectName("inspector_close")
        btn_close.setToolTip(tr("Collapse properties panel"))
        btn_close.setFixedSize(22, 22)
        btn_close.clicked.connect(self.close_panel)
        header_layout.addWidget(btn_close, 0)
        self.btn_close = btn_close

        outer_layout.addWidget(header_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setMinimumWidth(0)

        self.content_widget = _InspectorContentWidget()
        self.content_widget.setMinimumWidth(0)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(6, 8, 6, 8)
        self.content_layout.setSpacing(8)

        self.scroll.setWidget(self.content_widget)
        outer_layout.addWidget(self.scroll, 1)

    def _setup_styling(self) -> None:
        self.setStyleSheet("""
            QWidget {
                background: #1e222b;
                color: #eceff4;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 11px;
            }
            #inspector_header {
                background: #21252b;
                border-bottom: 1px solid #282c34;
            }
            #inspector_title {
                color: #88c0d0;
                font-size: 12px;
                font-weight: bold;
            }
            #inspector_close {
                background: transparent;
                color: #d8dee9;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            #inspector_close:hover {
                background: #bf616a;
                color: #ffffff;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background: #181a20;
                color: #eceff4;
                border: 1px solid #3b4252;
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 11px;
                min-width: 0px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #88c0d0;
                background: #1e222b;
            }
            QGroupBox {
                border: 1px solid #2e3440;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 8px;
                font-weight: bold;
                color: #81a1c1;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #282c34;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #5e81ac;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #eceff4;
                border: 1px solid #3b4252;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
                border: 1px solid #88c0d0;
            }
            QScrollBar:vertical {
                background: #181a20;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3b4252;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4c566a;
            }
        """)

    def retranslate_ui(self) -> None:
        if hasattr(self, "lbl_title"):
            self.lbl_title.setText(tr("📋 Node Properties"))
        if hasattr(self, "btn_close"):
            self.btn_close.setToolTip(tr("Collapse properties panel"))
        if self.current_node and self.current_node_item and self.current_scene:
            self.populate(self.current_node, self.current_node_item, self.current_scene)
        else:
            self.clear_and_show_placeholder()

    def close_panel(self) -> None:
        p = getattr(self, "parent_editor", None) or self.parent()
        while p is not None:
            if hasattr(p, "splitter") and hasattr(p.splitter, "user_collapse"):
                p.splitter.user_collapse()
                return
            p = p.parent()

    def clear_and_show_placeholder(self) -> None:
        self.current_node = None
        self.current_node_item = None
        self.current_scene = None
        self._clear_layout()

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 30, 12, 20)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("🔍")
        icon_lbl.setStyleSheet("font-size: 28px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(tr("No Node Selected"))
        title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #d8dee9; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title_lbl)

        desc_lbl = QLabel(tr("Select a node on canvas to inspect parameters and sliders."))
        desc_lbl.setStyleSheet("font-size: 10px; color: #7f8c98; background: transparent;")
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc_lbl)

        self.content_layout.addWidget(box)
        self.content_layout.addStretch(1)

    def show_multiple(self, count: int) -> None:
        self.current_node = None
        self.current_node_item = None
        self.current_scene = None
        self._clear_layout()

        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 30, 12, 20)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel("📦")
        icon_lbl.setStyleSheet("font-size: 28px; background: transparent;")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_lbl)

        title_lbl = QLabel(f"{count} {tr('Nodes Selected')}")
        title_lbl.setStyleSheet("font-size: 12px; font-weight: bold; color: #d8dee9; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title_lbl)

        desc_lbl = QLabel(tr("Select a single node to configure its parameters."))
        desc_lbl.setStyleSheet("font-size: 10px; color: #7f8c98; background: transparent;")
        desc_lbl.setWordWrap(True)
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(desc_lbl)

        self.content_layout.addWidget(box)
        self.content_layout.addStretch(1)

    def _clear_layout(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def populate(self, node: BaseNode, node_item: NodeItem, scene: NodeCanvasScene) -> None:
        self.current_node = node
        self.current_node_item = node_item
        self.current_scene = scene

        self._clear_layout()
        if not node:
            self.clear_and_show_placeholder()
            return

        self._syncing = True
        self._build_identity_card(node, node_item)

        if node.type_id in ("mat.color_rgb", "color.rgb") or ("r" in node.param_values and "g" in node.param_values and "b" in node.param_values):
            self._build_color_picker_card(node, node_item)

        self._build_parameters_section(node, node_item)
        self._build_actions_section(node, node_item)

        self.content_layout.addStretch(1)
        self._syncing = False

    def _build_identity_card(self, node: BaseNode, node_item: NodeItem) -> None:
        card = QFrame()
        card.setStyleSheet("background: #232731; border: 1px solid #2e3440; border-radius: 5px; padding: 2px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        display_t = getattr(node, "custom_title", None) or tr(node.title)
        lbl_type = QLabel(f"<b>{tr('Type:')}</b> {display_t} <span style='color: #88c0d0;'>({tr(node.category)})</span>")
        lbl_type.setTextFormat(Qt.TextFormat.RichText)
        lbl_type.setWordWrap(True)
        lbl_type.setStyleSheet("background: transparent; color: #eceff4; font-size: 11px;")
        lay.addWidget(lbl_type)

        nick_lay = QHBoxLayout()
        nick_lay.setSpacing(4)
        lbl_nick = QLabel(tr("Nick:"))
        lbl_nick.setStyleSheet("background: transparent; color: #abb2bf; font-weight: 500;")
        lbl_nick.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        le_nick = QLineEdit(getattr(node, "custom_title", None) or "")
        le_nick.setPlaceholderText(display_t)
        le_nick.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        le_nick.setMinimumWidth(30)

        def _on_nick_committed():
            if not self._syncing:
                node_item.set_custom_title(le_nick.text())
                node.is_dirty = True

        le_nick.editingFinished.connect(_on_nick_committed)
        nick_lay.addWidget(lbl_nick)
        nick_lay.addWidget(le_nick, 1)
        lay.addLayout(nick_lay)

        if node.description:
            lbl_desc = QLabel(tr(node.description))
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet("color: #7f8c98; font-size: 10px; background: transparent;")
            lay.addWidget(lbl_desc)

        self.content_layout.addWidget(card)

    def _build_color_picker_card(self, node: BaseNode, node_item: NodeItem) -> None:
        group = QGroupBox(tr("🎨 Color Picker & Palette"))
        lay = QVBoxLayout(group)
        lay.setContentsMargins(6, 8, 6, 6)
        lay.setSpacing(4)

        r = float(node.param_values.get("r", 0.8))
        g = float(node.param_values.get("g", 0.8))
        b = float(node.param_values.get("b", 0.8))
        hex_col = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        text_col = "#111111" if lum > 0.55 else "#ffffff"

        btn_color = QPushButton(f"{tr('Select Color')} ({hex_col})")
        btn_color.setFixedHeight(26)
        btn_color.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_color.setStyleSheet(f"""
            QPushButton {{
                background: {hex_col};
                color: {text_col};
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(255, 255, 255, 0.7);
            }}
        """)

        def _on_pick():
            curr_qcol = QColor.fromRgbF(min(1.0, max(0.0, r)), min(1.0, max(0.0, g)), min(1.0, max(0.0, b)))
            color = QColorDialog.getColor(curr_qcol, self, tr("Select Node Color"))
            if color.isValid():
                new_r = round(color.redF(), 3)
                new_g = round(color.greenF(), 3)
                new_b = round(color.blueF(), 3)
                node_item.set_param_value_from_inspector("r", new_r)
                node_item.set_param_value_from_inspector("g", new_g)
                node_item.set_param_value_from_inspector("b", new_b)
                self.populate(node, node_item, self.current_scene)

        btn_color.clicked.connect(_on_pick)
        lay.addWidget(btn_color)
        self.content_layout.addWidget(group)

    def _create_numeric_param_card(self, in_spec: InputSpec, node: BaseNode, node_item: NodeItem) -> QFrame:
        is_int = (in_spec.type == SocketType.INT)
        cur_val = float(node.param_values.get(in_spec.id, in_spec.default or 0.0))
        min_v = float(in_spec.min_val) if in_spec.min_val is not None else (0.0 if cur_val >= 0 else cur_val * 2.0)
        max_v = float(in_spec.max_val) if in_spec.max_val is not None else max(10.0, cur_val * 2.5 if cur_val != 0 else 10.0)
        if max_v <= min_v:
            max_v = min_v + 10.0
        dec = int(getattr(in_spec, "decimals", 0 if is_int else 2) or (0 if is_int else 2))
        step_v = float(in_spec.step if in_spec.step is not None else (1.0 if is_int else 0.1))

        card = QFrame()
        card.setStyleSheet("background: #232731; border: 1px solid #2e3440; border-radius: 5px; padding: 2px;")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(6, 6, 6, 6)
        card_lay.setSpacing(4)

        header_row = QHBoxLayout()
        lbl_name = QLabel(tr(in_spec.label))
        lbl_name.setStyleSheet("font-weight: bold; color: #88c0d0; background: transparent;")
        lbl_name.setWordWrap(True)
        tag_name = QLabel("Int" if is_int else "Float")
        tag_name.setStyleSheet("color: #7f8c98; font-size: 10px; background: transparent;")
        header_row.addWidget(lbl_name, 1)
        header_row.addWidget(tag_name, 0)
        card_lay.addLayout(header_row)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        # Min
        grid.addWidget(QLabel(tr("Min:")), 0, 0)
        spin_min = QSpinBox() if is_int else QDoubleSpinBox()
        spin_min.setRange(-1000000, 1000000)
        spin_min.setMinimumWidth(30)
        spin_min.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        spin_min.setKeyboardTracking(False)
        if not is_int:
            spin_min.setDecimals(max(4, dec))
        spin_min.setValue(int(round(min_v)) if is_int else min_v)
        grid.addWidget(spin_min, 0, 1)

        # Max
        grid.addWidget(QLabel(tr("Max:")), 0, 2)
        spin_max = QSpinBox() if is_int else QDoubleSpinBox()
        spin_max.setRange(-1000000, 1000000)
        spin_max.setMinimumWidth(30)
        spin_max.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        spin_max.setKeyboardTracking(False)
        if not is_int:
            spin_max.setDecimals(max(4, dec))
        spin_max.setValue(int(round(max_v)) if is_int else max_v)
        grid.addWidget(spin_max, 0, 3)

        # Decimals & Step
        if not is_int:
            grid.addWidget(QLabel(tr("Dec:")), 1, 0)
            spin_dec = QSpinBox()
            spin_dec.setRange(0, 6)
            spin_dec.setMinimumWidth(30)
            spin_dec.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            spin_dec.setKeyboardTracking(False)
            spin_dec.setValue(dec)
            grid.addWidget(spin_dec, 1, 1)

            grid.addWidget(QLabel(tr("Step:")), 1, 2)
            spin_step = QDoubleSpinBox()
            spin_step.setRange(0.0001, 1000.0)
            spin_step.setDecimals(4)
            spin_step.setMinimumWidth(30)
            spin_step.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            spin_step.setKeyboardTracking(False)
            spin_step.setValue(step_v)
            grid.addWidget(spin_step, 1, 3)
        else:
            grid.addWidget(QLabel(tr("Step:")), 1, 0)
            spin_step = QSpinBox()
            spin_step.setRange(1, 1000)
            spin_step.setMinimumWidth(30)
            spin_step.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            spin_step.setKeyboardTracking(False)
            spin_step.setValue(max(1, int(round(step_v))))
            grid.addWidget(spin_step, 1, 1, 1, 3)
            spin_dec = None

        # Value
        grid.addWidget(QLabel(tr("Val:")), 2, 0)
        spin_val = QSpinBox() if is_int else QDoubleSpinBox()
        spin_val.setRange(spin_min.value(), spin_max.value())
        spin_val.setMinimumWidth(30)
        spin_val.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        spin_val.setKeyboardTracking(False)
        if not is_int:
            spin_val.setDecimals(dec)
        spin_val.setSingleStep(spin_step.value())
        spin_val.setValue(int(round(cur_val)) if is_int else cur_val)
        grid.addWidget(spin_val, 2, 1, 1, 3)

        card_lay.addLayout(grid)

        scrub = QSlider(Qt.Orientation.Horizontal)
        scrub.setMinimum(0)
        scrub.setMinimumWidth(30)
        scrub.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        steps_count = int(round(spin_max.value() - spin_min.value())) if is_int else 1000
        scrub.setMaximum(max(1, steps_count))
        if is_int:
            scrub.setValue(int(round(cur_val - spin_min.value())))
        else:
            span = max_v - min_v
            ratio = (cur_val - min_v) / span if span > 1e-9 else 0.0
            scrub.setValue(int(round(max(0.0, min(1.0, ratio)) * 1000)))
        card_lay.addWidget(scrub)

        pid = in_spec.id
        _last_cfg = None

        def _sync_config(*_):
            nonlocal _last_cfg
            if self._syncing:
                return
            new_min = spin_min.value()
            new_max = spin_max.value()
            if new_max <= new_min:
                min_delta = 1 if is_int else (0.1 if (new_min >= 0 and new_min < 1) else 1.0)
                new_max = new_min + min_delta
                spin_max.blockSignals(True)
                spin_max.setValue(new_max)
                spin_max.blockSignals(False)
            new_dec = spin_dec.value() if spin_dec is not None else 0
            new_step = spin_step.value()

            cfg_key = (new_min, new_max, new_dec, new_step)
            if cfg_key == _last_cfg:
                return
            _last_cfg = cfg_key

            if not is_int:
                spin_min.setDecimals(max(4, new_dec))
                spin_max.setDecimals(max(4, new_dec))
                spin_step.setDecimals(max(4, new_dec))
                spin_val.setDecimals(new_dec)

            spin_val.blockSignals(True)
            spin_val.setRange(new_min, new_max)
            spin_val.setSingleStep(new_step)
            spin_val.blockSignals(False)

            node_item.update_slider_config(
                pid,
                min_val=new_min,
                max_val=new_max,
                decimals=new_dec,
                step=new_step,
            )

            scrub.blockSignals(True)
            if is_int:
                scrub.setMaximum(max(1, int(round(new_max - new_min))))
                scrub.setValue(int(round(spin_val.value() - new_min)))
            else:
                span_n = new_max - new_min
                r_n = (spin_val.value() - new_min) / span_n if span_n > 1e-9 else 0.0
                scrub.setValue(int(round(max(0.0, min(1.0, r_n)) * 1000)))
            scrub.blockSignals(False)

        _last_val = None

        def _on_spin_val_committed(*_):
            nonlocal _last_val
            if self._syncing:
                return
            v = spin_val.value()
            if v == _last_val:
                return
            _last_val = v
            node_item.set_param_value_from_inspector(pid, v)
            scrub.blockSignals(True)
            mn, mx = spin_min.value(), spin_max.value()
            span = mx - mn
            if is_int:
                scrub.setValue(int(round(v - mn)))
            else:
                r = (v - mn) / span if span > 1e-9 else 0.0
                scrub.setValue(int(round(max(0.0, min(1.0, r)) * 1000)))
            scrub.blockSignals(False)

        def _on_scrub_changed(tick):
            if self._syncing:
                return
            mn, mx = spin_min.value(), spin_max.value()
            if is_int:
                v = mn + tick
            else:
                v = mn + (tick / 1000.0) * (mx - mn)
            spin_val.blockSignals(True)
            spin_val.setValue(v)
            spin_val.blockSignals(False)
            node_item.set_param_value_from_inspector(pid, v)

        spin_min.editingFinished.connect(_sync_config)
        spin_min.valueChanged.connect(_sync_config)
        spin_max.editingFinished.connect(_sync_config)
        spin_max.valueChanged.connect(_sync_config)
        if spin_dec is not None:
            spin_dec.editingFinished.connect(_sync_config)
            spin_dec.valueChanged.connect(_sync_config)
        spin_step.editingFinished.connect(_sync_config)
        spin_step.valueChanged.connect(_sync_config)
        spin_val.editingFinished.connect(_on_spin_val_committed)
        spin_val.valueChanged.connect(_on_spin_val_committed)
        scrub.valueChanged.connect(_on_scrub_changed)

        return card

    def _build_parameters_section(self, node: BaseNode, node_item: NodeItem) -> None:
        if not node.inputs:
            return

        group = QGroupBox(tr("⚙️ Sliders & Limits"))
        lay = QVBoxLayout(group)
        lay.setContentsMargins(6, 10, 6, 6)
        lay.setSpacing(6)

        has_any_param = False

        for in_spec in node.inputs:
            if in_spec.type in (SocketType.FLOAT, SocketType.INT):
                has_any_param = True
                card = self._create_numeric_param_card(in_spec, node, node_item)
                lay.addWidget(card)

            elif in_spec.choices is not None and len(in_spec.choices) > 0:
                has_any_param = True
                card = QFrame()
                card.setStyleSheet("background: #232731; border: 1px solid #2e3440; border-radius: 5px; padding: 2px;")
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(6, 6, 6, 6)
                card_lay.setSpacing(4)

                lbl = QLabel(tr(in_spec.label) + ":")
                lbl.setStyleSheet("color: #abb2bf; font-weight: bold; background: transparent;")
                lbl.setWordWrap(True)

                combo = QComboBox()
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                combo.setMinimumWidth(30)
                combo.addItems([str(c) for c in in_spec.choices])
                cur_v = node.param_values.get(in_spec.id, in_spec.default)
                for idx, c in enumerate(in_spec.choices):
                    if str(c) == str(cur_v):
                        combo.setCurrentIndex(idx)
                        break

                pid = in_spec.id

                def _on_combo(idx, p=pid, spec=in_spec):
                    if not self._syncing:
                        raw = spec.choices[idx]
                        node_item.set_param_value_from_inspector(p, raw)

                combo.currentIndexChanged.connect(_on_combo)
                card_lay.addWidget(lbl)
                card_lay.addWidget(combo)
                lay.addWidget(card)

            elif in_spec.type == SocketType.BOOL:
                has_any_param = True
                chk = QCheckBox(tr(in_spec.label))
                chk.setChecked(bool(node.param_values.get(in_spec.id, in_spec.default)))
                base_dir = os.path.dirname(os.path.abspath(__file__))
                chk_icon = os.path.join(base_dir, "icons", "checkmark.png").replace("\\", "/")
                chk.setStyleSheet(f"""
                    QCheckBox {{
                        color: #d8dee9;
                        font-size: 11px;
                        background: transparent;
                        spacing: 6px;
                    }}
                    QCheckBox::indicator {{
                        width: 14px;
                        height: 14px;
                        border: 1px solid #7e8798;
                        border-radius: 3px;
                        background: #252932;
                    }}
                    QCheckBox::indicator:hover {{
                        border-color: #88c0d0;
                        background: #2e3440;
                    }}
                    QCheckBox::indicator:checked {{
                        background: #3875d7;
                        border-color: #81a1c1;
                        image: url("{chk_icon}");
                    }}
                """)
                pid = in_spec.id

                def _on_chk(c, p=pid):
                    if not self._syncing:
                        node_item.set_param_value_from_inspector(p, c)

                chk.toggled.connect(_on_chk)
                lay.addWidget(chk)

            elif in_spec.type == SocketType.STRING:
                has_any_param = True
                card = QFrame()
                card.setStyleSheet("background: #232731; border: 1px solid #2e3440; border-radius: 5px; padding: 2px;")
                card_lay = QVBoxLayout(card)
                card_lay.setContentsMargins(6, 6, 6, 6)
                card_lay.setSpacing(4)

                lbl = QLabel(in_spec.label + ":")
                lbl.setStyleSheet("color: #abb2bf; font-weight: bold; background: transparent;")
                lbl.setWordWrap(True)

                le = QLineEdit(str(node.param_values.get(in_spec.id, in_spec.default or "")))
                le.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                le.setMinimumWidth(30)
                pid = in_spec.id

                def _on_txt_committed(p=pid):
                    if not self._syncing:
                        node_item.set_param_value_from_inspector(p, le.text())

                le.editingFinished.connect(_on_txt_committed)
                card_lay.addWidget(lbl)
                card_lay.addWidget(le)
                lay.addWidget(card)

        if has_any_param:
            self.content_layout.addWidget(group)

    def _build_actions_section(self, node: BaseNode, node_item: NodeItem) -> None:
        action_buttons = node.get_action_buttons() if hasattr(node, "get_action_buttons") else []
        if not action_buttons:
            return

        group = QGroupBox(tr("⚡ Node Actions"))
        lay = QVBoxLayout(group)
        lay.setContentsMargins(6, 10, 6, 6)
        lay.setSpacing(4)

        for btn_spec in action_buttons:
            btn = QPushButton(btn_spec.get("label", "Action"))
            btn.setFixedHeight(26)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setToolTip(btn_spec.get("tooltip", ""))
            color = btn_spec.get("color", "#2e7d32")
            text_color = btn_spec.get("text_color", "#ffffff")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: {text_color};
                    font-weight: bold;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    border: 1px solid rgba(255, 255, 255, 0.5);
                }}
            """)
            btn.clicked.connect(lambda checked=False, spec=btn_spec: node_item._handle_card_button_click(spec))
            lay.addWidget(btn)

        self.content_layout.addWidget(group)


# ============================================================================
# TABBED COMPONENT RIBBON (CATEGORIES & ICONS)
# ============================================================================
class RibbonIconButton(QToolButton):
    def __init__(
        self,
        node_cls: type[BaseNode],
        on_click: Callable[[str], None],
        is_dark: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.node_cls = node_cls
        self.type_id = node_cls.type_id
        self.on_click = on_click
        self.is_dark = is_dark
        self._drag_start_pos: Optional[QPoint] = None

        self.setFixedSize(40, 40)
        self.setIconSize(QSize(30, 30))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)

        self._raw_title = getattr(node_cls, "title", self.type_id)
        self._raw_desc = getattr(node_cls, "description", "") or "No description available."
        self._raw_cat = getattr(node_cls, "category", "")
        self.retranslate_ui()

        self.update_icon(is_dark)
        self.clicked.connect(lambda: self.on_click(self.type_id))

    def retranslate_ui(self) -> None:
        title = tr(self._raw_title)
        desc = tr(self._raw_desc)
        cat = tr(self._raw_cat)
        self.setToolTip(
            f"<div style='font-family: Segoe UI, sans-serif; font-size: 11px;'>"
            f"<b>{title}</b> <span style='color: #888;'>({cat})</span><br/>"
            f"<span style='color: #61afef; font-family: monospace;'>{self.type_id}</span><hr style='margin:3px 0;'/>"
            f"{desc}</div>"
        )

    def update_icon(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self.setIcon(get_node_icon(self.type_id, is_dark))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            if (event.pos() - self._drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData("application/x-ingetrazo-node", self.type_id.encode("utf-8"))
                mime.setText(self.type_id)
                drag.setMimeData(mime)

                icon_pix = self.icon().pixmap(32, 32)
                drag.setPixmap(icon_pix)
                drag.setHotSpot(QPoint(16, 16))

                self.setDown(False)
                self._drag_start_pos = None
                drag.exec(Qt.DropAction.CopyAction)
                return
        super().mouseMoveEvent(event)


class NodeRibbonBar(QWidget):
    def __init__(
        self,
        on_node_clicked: Callable[[str], None],
        is_dark: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.on_node_clicked = on_node_clicked
        self.is_dark = is_dark
        self.buttons: List[RibbonIconButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        layout.addWidget(self.tab_widget)

        self.populate_categories()
        self.apply_theme(self.is_dark)

    def populate_categories(self) -> None:
        self.tab_widget.clear()
        self.buttons.clear()

        cat_map: Dict[str, List[type[BaseNode]]] = {}
        for node_cls in NODE_REGISTRY.values():
            cat = getattr(node_cls, "category", "Misc")
            cat_map.setdefault(cat, []).append(node_cls)

        pref_order = [
            "Architecture", "Inputs", "Curves", "3D Solids",
            "Transforms", "Material", "Points & Vectors",
            "Math & Lists", "Scene", "Scene Output"
        ]
        sorted_cats = [c for c in pref_order if c in cat_map]
        for c in sorted(cat_map.keys()):
            if c not in sorted_cats:
                sorted_cats.append(c)

        for cat in sorted_cats:
            node_classes = sorted(cat_map[cat], key=lambda cls: getattr(cls, "title", cls.type_id))
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(0)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setFixedHeight(48)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(6, 4, 6, 4)
            container_layout.setSpacing(4)

            for node_cls in node_classes:
                btn = RibbonIconButton(node_cls, self.on_node_clicked, is_dark=self.is_dark, parent=container)
                self.buttons.append(btn)
                container_layout.addWidget(btn)

            container_layout.addStretch(1)
            scroll.setWidget(container)
            page_layout.addWidget(scroll)

            page._orig_category = cat
            self.tab_widget.addTab(page, tr(cat))

    def retranslate_ui(self) -> None:
        for idx in range(self.tab_widget.count()):
            page = self.tab_widget.widget(idx)
            orig_cat = getattr(page, "_orig_category", None)
            if orig_cat:
                self.tab_widget.setTabText(idx, tr(orig_cat))
        for btn in self.buttons:
            btn.retranslate_ui()

    def apply_theme(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        for btn in self.buttons:
            btn.update_icon(is_dark)

        if is_dark:
            self.setStyleSheet("""
                QTabWidget::pane {
                    border: none;
                    background: #1e2227;
                    border-bottom: 1px solid #3b4252;
                }
                QTabBar::tab {
                    background: #21252b;
                    color: #abb2bf;
                    padding: 3px 10px;
                    margin-right: 1px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-size: 11px;
                    font-weight: 500;
                }
                QTabBar::tab:hover {
                    background: #2c313a;
                    color: #ffffff;
                }
                QTabBar::tab:selected {
                    background: #1e2227;
                    color: #61afef;
                    border-bottom: 2px solid #61afef;
                }
                QScrollArea {
                    background: #1e2227;
                    border: none;
                }
                QScrollBar:horizontal {
                    height: 4px;
                    background: transparent;
                }
                QScrollBar::handle:horizontal {
                    background: #4c566a;
                    border-radius: 2px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QToolButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 5px;
                    padding: 1px;
                }
                QToolButton:hover {
                    background: #2c313a;
                    border: 1px solid #61afef;
                }
                QToolButton:pressed {
                    background: #3e4451;
                }
            """)
        else:
            self.setStyleSheet("""
                QTabWidget::pane {
                    border: none;
                    background: #f3f5f8;
                    border-bottom: 1px solid #d0d7de;
                }
                QTabBar::tab {
                    background: #e1e4e8;
                    color: #4c566a;
                    padding: 3px 10px;
                    margin-right: 1px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-size: 11px;
                    font-weight: 500;
                }
                QTabBar::tab:hover {
                    background: #d8dee9;
                    color: #1e2227;
                }
                QTabBar::tab:selected {
                    background: #f3f5f8;
                    color: #1976d2;
                    border-bottom: 2px solid #1976d2;
                }
                QScrollArea {
                    background: #f3f5f8;
                    border: none;
                }
                QScrollBar:horizontal {
                    height: 4px;
                    background: transparent;
                }
                QScrollBar::handle:horizontal {
                    background: #c2c9d4;
                    border-radius: 2px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QToolButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 5px;
                    padding: 1px;
                }
                QToolButton:hover {
                    background: #e2e8f0;
                    border: 1px solid #1976d2;
                }
                QToolButton:pressed {
                    background: #cbd5e1;
                }
            """)


# ============================================================================
# MAIN NODE EDITOR WIDGET
# ============================================================================
class NodeEditorWidget(QWidget):
    def __init__(
        self,
        engine: GraphEngine,
        on_bake: Callable[[], None],
        on_live_toggled: Callable[[bool], None],
        get_bridge_error: Optional[Callable[[], Optional[str]]] = None,
        on_load_selection: Optional[Callable[[], None]] = None,
        get_app: Optional[Callable[[], Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.on_bake = on_bake
        self.on_live_toggled = on_live_toggled
        self.get_bridge_error = get_bridge_error
        self.on_load_selection = on_load_selection
        self.get_app = get_app
        self._dock: Optional[Any] = None

        self._eval_timer = QTimer(self)
        self._eval_timer.setSingleShot(True)
        self._eval_timer.setInterval(16)
        self._eval_timer.timeout.connect(self._run_eval)

        self._build_ui()
        self.load_default_preset()

    def set_dock(self, dock: Any) -> None:
        self._dock = dock
        if hasattr(dock, "topLevelChanged"):
            dock.topLevelChanged.connect(self._on_dock_toplevel_changed)
        if hasattr(dock, "isFloating"):
            self._update_popout_button(dock.isFloating())

    def _on_dock_toplevel_changed(self, is_floating: bool) -> None:
        self._update_popout_button(is_floating)

    def _update_popout_button(self, is_floating: bool) -> None:
        if hasattr(self, "btn_popout"):
            self.btn_popout.setText(tr("⇲ Dock Tab") if is_floating else tr("⧉ Pop out"))
            self.btn_popout.setToolTip(
                tr("Dock back as a side tray tab") if is_floating else tr("Pop out into a separate floating window")
            )

    def _toggle_popout(self) -> None:
        dock = self._dock
        if dock is None:
            p = self.parent()
            while p is not None:
                if type(p).__name__ == "QDockWidget" or hasattr(p, "isFloating"):
                    dock = p
                    break
                p = p.parent()
        if dock is not None and hasattr(dock, "setFloating"):
            is_float = not dock.isFloating()
            dock.setFloating(is_float)
            if is_float:
                dock.resize(1060, 680)
                dock.raise_()
                dock.activateWindow()
            self._update_popout_button(is_float)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setStyleSheet("""
            QWidget {
                background: #21252b;
                color: #eceff4;
                border-bottom: 1px solid #3b4252;
            }
            QPushButton {
                background: #2c313a;
                color: #abb2bf;
                border: 1px solid #3e4451;
                border-radius: 4px;
                padding: 3px 7px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #3e4451;
                color: #ffffff;
            }
        """)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(5)

        self.btn_ribbon_toggle = QPushButton("▲")
        self.btn_ribbon_toggle.setToolTip(tr("Toggle Component Shelf (Grasshopper Ribbon)"))
        self.btn_ribbon_toggle.setStyleSheet("""
            QPushButton {
                background: #2c313a;
                color: #61afef;
                font-weight: bold;
                border: 1px solid #3e4451;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #3e4451;
                color: #ffffff;
            }
        """)

        self.btn_add = QPushButton(tr("➕ Add"))
        self.btn_add.setToolTip(tr("Add Node (Space or Tab)"))
        self.btn_reload = QPushButton("🔄")
        self.btn_reload.setToolTip(tr("Reload Nodes catalog"))
        self.chk_live = QCheckBox(tr("🔴 Live"))
        self.chk_live.setToolTip(tr("Live Viewport Sync (60 FPS)"))
        self.chk_live.setStyleSheet("color: #e5c07b; font-size: 11px;")
        self.chk_live.setChecked(True)

        self.btn_bake = QPushButton(tr("🥐 Bake"))
        self.btn_bake.setToolTip(tr("Bake current solids to IngeTrazo Scene"))
        self.btn_bake.setStyleSheet("background: #2e7d32; color: white; font-weight: bold; border-radius: 4px; padding: 3px 9px;")

        self.btn_save = QPushButton("💾")
        self.btn_save.setToolTip(tr("Save Graph (.itgraph / .json)"))
        self.btn_load = QPushButton("📂")
        self.btn_load.setToolTip(tr("Load Graph from file"))

        self.btn_load_group = QPushButton(tr("📥 From Group"))
        self.btn_load_group.setToolTip(tr("Load embedded graph from selected IngeTrazo Group"))

        self.btn_popout = QPushButton(tr("⧉ Pop out"))
        self.btn_popout.setToolTip(tr("Pop out into separate window / Dock as tab"))
        self.btn_popout.setStyleSheet("background: #3b4252; color: #61afef; border-radius: 4px; padding: 3px 7px;")

        self.btn_fit = QPushButton(tr("🔎 Fit"))
        self.btn_fit.setToolTip(tr("Fit all nodes in view (F)"))
        self.btn_fit.setStyleSheet("background: #2c313a; color: #88c0d0; border-radius: 4px; padding: 3px 7px;")

        meta = get_current_language_meta()
        self.btn_lang = QPushButton(f"{meta.get('flag', '🌐')} {meta.get('code', 'en').upper()} ▾")
        self.btn_lang.setToolTip(tr("Change Language"))
        self.btn_lang.setStyleSheet("""
            QPushButton {
                background: #2c313a;
                color: #e5c07b;
                font-weight: 500;
                border: 1px solid #3e4451;
                border-radius: 4px;
                padding: 3px 7px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #3e4451;
                color: #ffffff;
                border-color: #e5c07b;
            }
        """)

        self.lbl_status = QLabel(tr("Ready"))
        self.lbl_status.setStyleSheet("color: #98c379; font-size: 11px;")

        bar_layout.addWidget(self.btn_ribbon_toggle)
        for b in (self.btn_add, self.btn_reload, self.btn_bake, self.btn_save, self.btn_load, self.btn_load_group):
            bar_layout.addWidget(b)
        bar_layout.addWidget(self.chk_live)
        bar_layout.addWidget(self.btn_popout)
        bar_layout.addWidget(self.btn_fit)
        bar_layout.addWidget(self.btn_lang)
        bar_layout.addStretch(1)
        bar_layout.addWidget(self.lbl_status)

        self.scene = NodeCanvasScene(self.engine, self.schedule_eval, on_bake=self.on_bake, get_app=self.get_app)
        self.view = NodeCanvasView(self.scene)
        self.view.parent_editor = self

        self.inspector = NodeInspectorPanel(self)
        self.inspector.parent_editor = self

        self.splitter = InspectorSplitter(Qt.Orientation.Horizontal, parent=self)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background: #1e2227;
                width: 16px;
            }
            QSplitter::handle:hover {
                background: #232731;
            }
        """)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.inspector)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, True)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1000, 0])
        self.splitter.is_collapsed = True
        self.splitter.user_collapsed = False
        self.inspector.show()

        is_dark = True
        if self.get_app is not None:
            try:
                app_obj = self.get_app()
                if hasattr(app_obj, "theme") and isinstance(app_obj.theme, str):
                    is_dark = "dark" in app_obj.theme.lower()
            except Exception:
                pass

        self.ribbon = NodeRibbonBar(on_node_clicked=self._spawn_node_from_ribbon, is_dark=is_dark, parent=self)

        root.addWidget(bar)
        root.addWidget(self.ribbon)
        root.addWidget(self.splitter, stretch=1)

        self.btn_ribbon_toggle.clicked.connect(self._toggle_ribbon)
        self.btn_add.clicked.connect(self._open_search_under_button)
        self.btn_reload.clicked.connect(self._hot_reload_nodes)
        self.chk_live.toggled.connect(self.on_live_toggled)
        self.btn_bake.clicked.connect(lambda: self.on_bake(None))
        self.btn_save.clicked.connect(self._save_graph)
        self.btn_load.clicked.connect(self._load_graph)
        self.btn_load_group.clicked.connect(self._handle_load_from_group)
        self.btn_popout.clicked.connect(self._toggle_popout)
        self.btn_fit.clicked.connect(self.view.fit_view)
        self.btn_lang.clicked.connect(self._open_language_menu)
        register_language_listener(lambda code: self.retranslate_ui())
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

    def _toggle_ribbon(self) -> None:
        is_hidden = self.ribbon.isHidden()
        self.ribbon.setVisible(is_hidden)
        self.btn_ribbon_toggle.setText("▲" if is_hidden else "▼")
        self.btn_ribbon_toggle.setToolTip(tr("Hide Component Shelf") if is_hidden else tr("Show Component Shelf"))

    def _spawn_node_from_ribbon(self, type_id: str) -> None:
        view_rect = self.view.viewport().rect()
        scene_pt = self.view.mapToScene(view_rect.center())
        item = self.scene.spawn_node(type_id, (scene_pt.x(), scene_pt.y()))
        self.scene.clearSelection()
        item.setSelected(True)

    def set_theme(self, is_dark: bool) -> None:
        if hasattr(self, "ribbon"):
            self.ribbon.apply_theme(is_dark)

    def _on_scene_selection_changed(self) -> None:
        try:
            if not hasattr(self, "scene") or self.scene is None:
                return
            selected_nodes = [item for item in self.scene.selectedItems() if isinstance(item, NodeItem)]
        except RuntimeError:
            return

        # 1. If explicitly collapsed by user, keep it closed even when nodes are selected
        if getattr(self.splitter, "user_collapsed", False):
            if len(selected_nodes) == 1:
                self.inspector.populate(selected_nodes[0].node, selected_nodes[0], self.scene)
            elif len(selected_nodes) > 1:
                self.inspector.show_multiple(len(selected_nodes))
            else:
                self.inspector.clear_and_show_placeholder()
            return

        # 2. In auto mode: expand when a node is selected, autohide when deselected
        if len(selected_nodes) == 1:
            self.inspector.populate(selected_nodes[0].node, selected_nodes[0], self.scene)
            self.splitter.expand_panel()
        elif len(selected_nodes) > 1:
            self.inspector.show_multiple(len(selected_nodes))
            self.splitter.expand_panel()
        else:
            self.inspector.clear_and_show_placeholder()
            self.splitter.collapse_panel()

    def _open_search_under_button(self) -> None:
        btn_pos = self.btn_add.mapToGlobal(QPoint(0, self.btn_add.height() + 2))
        scene_pt = self.view.mapToScene(self.view.viewport().rect().center())
        popup = NodeSearchPopup(
            self,
            on_pick=lambda tid: self.scene.spawn_node(tid, (scene_pt.x(), scene_pt.y())),
        )
        popup.move(btn_pos)
        popup.show()
        popup.search_box.setFocus()

    def _handle_load_from_group(self) -> None:
        if self.on_load_selection:
            self.on_load_selection()

    def schedule_eval(self) -> None:
        self._eval_timer.start()

    def _run_eval(self) -> None:
        meshes, pts = self.engine.evaluate()
        for item in self.scene.node_items.values():
            if hasattr(item, "update_panel_display"):
                item.update_panel_display()
            item.update()
        bridge_err = self.get_bridge_error() if self.get_bridge_error else None
        if bridge_err:
            self.lbl_status.setStyleSheet("color: #e06c75; font-size: 11px;")
            self.lbl_status.setText(f"⚠️ Viewport: {bridge_err}")
        else:
            self.lbl_status.setStyleSheet("color: #98c379; font-size: 11px;")
            self.lbl_status.setText(f"⚡ {len(meshes)} solid(s) | {self.engine.last_eval_ms:.1f} ms")

    def _hot_reload_nodes(self) -> None:
        errs = discover_nodes(reload_modules=True)
        for n in self.engine.nodes.values():
            n.is_dirty = True
        if hasattr(self, "ribbon"):
            self.ribbon.populate_categories()
            self.ribbon.apply_theme(self.ribbon.is_dark)
        self._run_eval()
        if errs:
            self.lbl_status.setText(f"⚠️ Reload error: {errs[0].splitlines()[0]}")
        else:
            self.lbl_status.setText(f"✅ {len(NODE_REGISTRY)} nodes registered")

    def _open_language_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #21252b;
                color: #abb2bf;
                border: 1px solid #3e4451;
                border-radius: 6px;
                padding: 4px;
                font-size: 11px;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c313a;
                color: #ffffff;
            }
        """)
        cur_lang = get_current_language()
        for lang in get_available_languages():
            flag = lang.get("flag", "🌐")
            name = lang.get("native", lang.get("name", lang["code"]))
            code = lang["code"]
            is_cur = (code == cur_lang)
            prefix = "✓ " if is_cur else "   "
            action = menu.addAction(f"{prefix}{flag}  {name} ({code.upper()})")
            action.triggered.connect(lambda checked=False, c=code: self._switch_language(c))

        btn_rect = self.btn_lang.rect()
        global_pt = self.btn_lang.mapToGlobal(btn_rect.bottomLeft())
        menu.exec(global_pt)

    def _switch_language(self, code: str) -> None:
        set_language(code)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        meta = get_current_language_meta()
        self.btn_lang.setText(f"{meta.get('flag', '🌐')} {meta.get('code', 'en').upper()} ▾")
        self.btn_lang.setToolTip(tr("Change Language"))

        is_hidden = self.ribbon.isHidden() if hasattr(self, "ribbon") else False
        self.btn_ribbon_toggle.setToolTip(tr("Hide Component Shelf") if is_hidden else tr("Show Component Shelf"))
        self.btn_add.setText(tr("➕ Add"))
        self.btn_add.setToolTip(tr("Add Node (Space or Tab)"))
        self.btn_reload.setToolTip(tr("Reload Nodes catalog"))
        self.chk_live.setText(tr("🔴 Live"))
        self.chk_live.setToolTip(tr("Live Viewport Sync (60 FPS)"))
        self.btn_bake.setText(tr("🥐 Bake"))
        self.btn_bake.setToolTip(tr("Bake current solids to IngeTrazo Scene"))
        self.btn_save.setToolTip(tr("Save Graph (.itgraph / .json)"))
        self.btn_load.setToolTip(tr("Load Graph from file"))
        self.btn_load_group.setText(tr("📥 From Group"))
        self.btn_load_group.setToolTip(tr("Load embedded graph from selected IngeTrazo Group"))
        self.btn_fit.setText(tr("🔎 Fit"))
        self.btn_fit.setToolTip(tr("Fit all nodes in view (F)"))

        if hasattr(self, "_dock") and self._dock is not None:
            self._update_popout_button(self._dock.isFloating() if hasattr(self._dock, "isFloating") else False)
        else:
            self.btn_popout.setText(tr("⧉ Pop out"))
            self.btn_popout.setToolTip(tr("Pop out into separate window / Dock as tab"))

        if self.lbl_status.text() in ("Ready", "Prêt"):
            self.lbl_status.setText(tr("Ready"))

        if hasattr(self, "ribbon"):
            self.ribbon.retranslate_ui()

        if hasattr(self, "inspector"):
            self.inspector.retranslate_ui()

        if hasattr(self, "scene"):
            self.scene.retranslate_ui()

    def _save_graph(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("Save Node Graph"), "", tr("IngeTrazo Graph (*.itgraph *.json)"))
        if path:
            self.engine.save_file(path)

    def _load_graph(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Load Node Graph"), "", tr("IngeTrazo Graph (*.itgraph *.json)"))
        if path:
            self.engine.load_file(path)
            self.scene.rebuild_from_engine()

    def load_default_preset(self) -> None:
        g = self.engine.add_node("vec.grid_2d", pos=(40, 80))
        c = self.engine.add_node("solid.cylinder", pos=(310, 80))
        o = self.engine.add_node("scene.output", pos=(580, 80))
        o.set_param("group_name", "Parametric_Columns")
        o.set_param("ifc_class", "IfcColumn")
        self.engine.connect(g.id, "points", c.id, "center")
        self.engine.connect(c.id, "mesh", o.id, "mesh")
        self.scene.rebuild_from_engine()
