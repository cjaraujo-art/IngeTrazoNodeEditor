# SPDX-License-Identifier: GPL-3.0-or-later
"""Image sampling and heightfield terrain nodes for IngeTrazo."""

from __future__ import annotations
import math
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QFileDialog
except ImportError:
    QImage = None
    QColor = None
    QFileDialog = None

try:
    from ..core_types import CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from core_types import CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node


@register_node
class ImageSamplerNode(BaseNode):
    type_id = "input.image_sampler"
    title = "Image Sampler (Heightfield)"
    category = "Inputs"
    description = (
        "Samples an image file (PNG/JPG/BMP) or procedural ripple to produce a 3D terrain\n"
        "displacement mesh, point cloud, and brightness values (0.0 to 1.0).\n"
        "Click '🖼️ Select Image' on the node card to pick a file from disk."
    )
    header_color = (68, 85, 110)

    inputs = [
        InputSpec("path", "Image Path", SocketType.STRING, default=""),
        InputSpec("size_x", "Size X (m)", SocketType.FLOAT, default=10.0, min_val=0.1, step=1.0),
        InputSpec("size_y", "Size Y (m)", SocketType.FLOAT, default=10.0, min_val=0.1, step=1.0),
        InputSpec("min_z", "Min Z (m)", SocketType.FLOAT, default=0.0, step=0.25),
        InputSpec("max_z", "Max Z (m)", SocketType.FLOAT, default=2.0, step=0.25),
        InputSpec("count_u", "Resolution U", SocketType.INT, default=30, min_val=2, max_val=200, step=1),
        InputSpec("count_v", "Resolution V", SocketType.INT, default=30, min_val=2, max_val=200, step=1),
        InputSpec("invert", "Invert", SocketType.BOOL, default=False),
        InputSpec("flip_normals", "Flip Normals", SocketType.BOOL, default=False),
    ]
    outputs = [
        OutputSpec("mesh", "Terrain Mesh", SocketType.MESH),
        OutputSpec("points", "Grid Points", SocketType.VEC3),
        OutputSpec("values", "Heights (0-1)", SocketType.FLOAT),
        OutputSpec("width", "Img Width", SocketType.INT),
        OutputSpec("height", "Img Height", SocketType.INT),
    ]

    def get_action_buttons(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "btn_pick_img",
                "label": "🖼️ Select Image",
                "tooltip": "Choose an image file from disk to use as heightfield",
                "color": "#3b4252",
                "action": "pick_image_dialog",
            }
        ]

    def get_card_badge_text(self) -> Optional[str]:
        p = self.param_values.get("path", "")
        if p and os.path.exists(p):
            return os.path.basename(p)
        return "Procedural Ripple"

    def pick_image_dialog(self) -> None:
        if QFileDialog is None:
            return
        fname, _ = QFileDialog.getOpenFileName(
            None,
            "Select Heightmap Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.tif);;All Files (*)",
        )
        if fname:
            self.set_param("path", fname)
            self.is_dirty = True

    def compute(
        self,
        path: str,
        size_x: float,
        size_y: float,
        min_z: float,
        max_z: float,
        count_u: int,
        count_v: int,
        invert: bool,
        flip_normals: bool = False,
    ) -> Dict[str, Any]:
        nu = max(2, min(200, int(count_u)))
        nv = max(2, min(200, int(count_v)))
        sx = max(0.01, float(size_x))
        sy = max(0.01, float(size_y))
        z_min = float(min_z)
        z_max = float(max_z)
        z_span = z_max - z_min

        qimg: Optional[Any] = None
        if path and isinstance(path, str) and os.path.isfile(path) and QImage is not None:
            loaded = QImage(path)
            if not loaded.isNull():
                qimg = loaded

        img_w = qimg.width() if qimg else 128
        img_h = qimg.height() if qimg else 128

        # Sample grid: row-major order (outer loop V, inner loop U)
        pts: List[Vec3] = []
        vals: List[float] = []

        for j in range(nv):
            v_ratio = j / float(nv - 1)
            y = v_ratio * sy
            for i in range(nu):
                u_ratio = i / float(nu - 1)
                x = u_ratio * sx

                if qimg is not None:
                    px = int(min(img_w - 1, max(0, u_ratio * (img_w - 1))))
                    # PySide6: invert Y coordinate so top of image maps to +Y
                    py = int(min(img_h - 1, max(0, (1.0 - v_ratio) * (img_h - 1))))
                    col = qimg.pixelColor(px, py)
                    # Standard luminance formula: 0.299 R + 0.587 G + 0.114 B
                    lum = (0.299 * col.red() + 0.587 * col.green() + 0.114 * col.blue()) / 255.0
                else:
                    # Procedural ripple
                    nx = u_ratio * 2.0 - 1.0
                    ny = v_ratio * 2.0 - 1.0
                    r = math.sqrt(nx * nx + ny * ny) * math.pi * 3.0
                    lum = math.sin(r) * 0.5 + 0.5

                if invert:
                    lum = 1.0 - lum

                z = z_min + lum * z_span
                pts.append(Vec3(x, y, z))
                vals.append(lum)

        # Build mesh using shared vertices and correct row-major indexing
        mesh = MeshData.create_from_points(
            pts=pts,
            u_count=nu,
            v_count=nv,
            closed_u=False,
            closed_v=False,
            swap_uv=False,
            triangulate=False,
            flip_normals=flip_normals,
            name="HeightfieldTerrain",
        )

        return {
            "mesh": mesh,
            "points": pts,
            "values": vals,
            "width": img_w,
            "height": img_h,
        }
