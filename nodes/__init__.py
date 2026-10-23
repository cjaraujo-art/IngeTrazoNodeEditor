# SPDX-License-Identifier: GPL-3.0-or-later
"""
Auto-discovery and hot-reloader for built-in and user custom node modules.
Automatically searches both local plugin `custom_nodes/` and persistent user directories
so custom nodes are never overwritten during extension updates.
"""

from __future__ import annotations
import importlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
from typing import List, Optional, Tuple


def get_custom_nodes_dirs() -> List[Path]:
    """
    Returns the list of directories scanned for custom nodes, ordered by priority.
    Automatically creates the folders if they do not yet exist.
    """
    dirs: List[Path] = []
    nodes_dir = Path(__file__).resolve().parent

    # 1. Bundled custom_nodes directory inside the plugin root
    bundled_dir = nodes_dir.parent / "custom_nodes"
    try:
        bundled_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if bundled_dir.is_dir() and bundled_dir not in dirs:
        dirs.append(bundled_dir)

    # 2. Persistent User Application Data directory (survives plugin updates!)
    appdata = os.environ.get("APPDATA")
    if appdata:
        user_appdata_dir = Path(appdata) / "IngeTrazo" / "custom_nodes"
        try:
            user_appdata_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if user_appdata_dir.is_dir() and user_appdata_dir not in dirs:
            dirs.append(user_appdata_dir)

    # 3. Subfolder nodes/custom_nodes/ if present
    sub_custom = nodes_dir / "custom_nodes"
    if sub_custom.is_dir() and sub_custom not in dirs:
        dirs.append(sub_custom)

    # 4. Cross-platform user home directory ~/.ingetrazo_node_editor/custom_nodes
    home_custom_dir = Path.home() / ".ingetrazo_node_editor" / "custom_nodes"
    try:
        home_custom_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if home_custom_dir.is_dir() and home_custom_dir not in dirs:
        dirs.append(home_custom_dir)

    return dirs


def get_primary_custom_nodes_dir() -> Path:
    """
    Returns the recommended folder to open in File Explorer or save new custom nodes into.
    Prefers the bundled custom_nodes folder or user AppData folder.
    """
    dirs = get_custom_nodes_dirs()
    # Prefer bundled custom_nodes if inside a writable project, otherwise AppData
    for d in dirs:
        if "custom_nodes" in d.name:
            return d
    return dirs[0] if dirs else Path(__file__).resolve().parent.parent / "custom_nodes"


def create_custom_node_file(
    title: str,
    category: str = "Custom",
    target_dir: Optional[Path] = None,
) -> Tuple[Path, str]:
    """
    Scaffolds a new custom node .py file from the template.
    Returns (created_file_path, class_name).
    """
    out_dir = target_dir or get_primary_custom_nodes_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize title to class name (e.g. "My Wall Panel" -> "MyWallPanelNode")
    words = re.findall(r"[A-Za-z0-9]+", title)
    if not words:
        words = ["MyCustomNode"]
    clean_base = "".join(w.capitalize() for w in words)
    cls_name = f"{clean_base}Node" if not clean_base.endswith("Node") else clean_base

    # Generate snake_case filename
    file_stem = re.sub(r"(?<!^)(?=[A-Z])", "_", clean_base).lower()
    type_id = f"custom.{file_stem}"

    file_path = out_dir / f"{file_stem}.py"
    counter = 1
    while file_path.exists():
        file_path = out_dir / f"{file_stem}_{counter}.py"
        counter += 1

    content = f'''# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom Parametric Node: {title}."""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from node_base import BaseNode, InputSpec, OutputSpec, register_node
except (ImportError, ValueError):
    from ..core_types import AccessMode, CurveData, MeshData, SocketType, Vec3
    from ..node_base import BaseNode, InputSpec, OutputSpec, register_node


@register_node
class {cls_name}(BaseNode):
    """
    Custom Parametric Node created in IngeTrazo Node Editor.
    """
    type_id = "{type_id}"
    title = "{title}"
    category = "{category or 'Custom'}"
    description = "Custom parametric generator for {title}."
    header_color = (80, 120, 160)

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=3.0, min_val=0.1, step=0.25),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=2.5, min_val=0.1, step=0.25),
        InputSpec("depth", "Depth (m)", SocketType.FLOAT, default=0.3, min_val=0.05, step=0.05),
    ]
    outputs = [
        OutputSpec("mesh", "Solid Mesh", SocketType.MESH),
    ]

    def compute(self, origin: Vec3, width: float, height: float, depth: float) -> Dict[str, Any]:
        p0 = origin or Vec3(0, 0, 0)
        w = max(0.01, float(width))
        h = max(0.01, float(height))
        d = max(0.01, float(depth))

        # Generate a watertight 3D cuboid
        solid = MeshData.create_box(p0, w, d, h)
        solid.name = "{clean_base}"
        return {{"mesh": solid}}
'''
    with open(file_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    return file_path, cls_name


def create_addon_folder(
    addon_name: str,
    target_dir: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """
    Scaffolds a new Addon / Plugin Pack directory containing:
      - __init__.py (with ADDON_NAME and starter custom node)
      - icons/ folder (for node PNG/SVG icons)
    All nodes inside this folder automatically appear in their own dedicated Tab on the ribbon!
    Returns (addon_dir_path, init_py_path).
    """
    base_dir = target_dir or get_primary_custom_nodes_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    # Clean folder name (e.g. "Seg Nodes" -> "seg_nodes")
    clean_stem = re.sub(r"[^\w\s-]", "", addon_name).strip()
    folder_name = re.sub(r"[-\s]+", "_", clean_stem).lower()
    if not folder_name:
        folder_name = "my_addon"

    addon_dir = base_dir / folder_name
    counter = 1
    while addon_dir.exists():
        addon_dir = base_dir / f"{folder_name}_{counter}"
        counter += 1

    addon_dir.mkdir(parents=True, exist_ok=True)
    icons_dir = addon_dir / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Starter class name and type_id
    words = re.findall(r"[A-Za-z0-9]+", addon_name) or ["Custom"]
    clean_base = "".join(w.capitalize() for w in words)
    cls_name = f"{clean_base}SampleNode"
    type_id = f"{folder_name}.sample"
    icon_tag = "".join(w[0].upper() for w in words[:3])

    init_file = addon_dir / "__init__.py"
    content = f'''# SPDX-License-Identifier: GPL-3.0-or-later
"""
{addon_name} — Addon for IngeTrazo Node Editor.
All nodes defined in this folder appear automatically in the '{addon_name}' tab!
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
# ADDON CONFIGURATION
# ============================================================================
# This name appears as the Category and dedicated Tab in the Node Editor!
ADDON_NAME = "{addon_name}"
ADDON_AUTHOR = "Author"
ADDON_VERSION = "1.0.0"


# ============================================================================
# CUSTOM NODES
# ============================================================================
@register_node
class {cls_name}(BaseNode):
    """
    Sample parametric node for {addon_name}.
    """
    type_id = "{type_id}"
    title = "{addon_name} Box"
    category = "{addon_name}"
    description = "Parametric box generator for {addon_name}."
    header_color = (65, 117, 164)
    icon_tag = "{icon_tag}"  # Text badge or emoji (e.g. "SN", "🧱", "📐")
    # icon = "my_node.png"   # Optional: place image in icons/ folder!

    inputs = [
        InputSpec("origin", "Origin", SocketType.VEC3, default=Vec3(0, 0, 0), hide_widget=True),
        InputSpec("width", "Width (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.1),
        InputSpec("depth", "Depth (m)", SocketType.FLOAT, default=2.0, min_val=0.1, step=0.1),
        InputSpec("height", "Height (m)", SocketType.FLOAT, default=3.0, min_val=0.1, step=0.1),
    ]
    outputs = [
        OutputSpec("mesh", "Solid Mesh", SocketType.MESH),
    ]

    def compute(self, origin: Vec3, width: float, depth: float, height: float) -> Dict[str, Any]:
        p0 = origin or Vec3(0, 0, 0)
        solid = MeshData.create_box(p0, max(0.01, float(width)), max(0.01, float(depth)), max(0.01, float(height)))
        solid.name = "{clean_base}Solid"
        return {{"mesh": solid}}
'''
    with open(init_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    return addon_dir, init_file


def _load_py_file(
    py_file: Path,
    reload_modules: bool,
    errors: List[str],
    default_category: Optional[str] = None,
    addon_dir: Optional[Path] = None,
) -> bool:
    """Safely loads or reloads an isolated .py file without letting exceptions crash the application."""
    if py_file.name.startswith(".") or "__pycache__" in py_file.parts:
        return False

    stem = py_file.stem
    # Stable unique module identifier
    safe_hash = abs(hash(str(py_file.resolve()))) % 1000000
    mod_id = f"custom_node_{stem}_{safe_hash}"

    mod = None
    if mod_id in sys.modules and not reload_modules:
        mod = sys.modules[mod_id]
    else:
        # Load or re-execute module from spec (avoids "spec not found" on reload)
        try:
            spec = importlib.util.spec_from_file_location(mod_id, str(py_file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules[mod_id] = mod
                spec.loader.exec_module(mod)
        except Exception as exc:
            errors.append(f"{py_file.name}: {exc}\n{traceback.format_exc()}")
            return False

    if mod is None:
        return False

    # Apply Addon Category and Icon Directory to all BaseNode subclasses in this module
    addon_name = (
        getattr(mod, "ADDON_NAME", None)
        or getattr(mod, "CATEGORY", None)
        or getattr(mod, "ADDON_TITLE", None)
        or default_category
        or "Custom"
    )

    resolved_addon_dir = addon_dir or py_file.parent
    icons_dir = None
    if (resolved_addon_dir / "icons").is_dir():
        icons_dir = resolved_addon_dir / "icons"
    elif (py_file.parent / "icons").is_dir():
        icons_dir = py_file.parent / "icons"

    import inspect
    from node_base import BaseNode, NODE_REGISTRY

    for attr_name, attr_val in list(mod.__dict__.items()):
        if inspect.isclass(attr_val) and issubclass(attr_val, BaseNode) and attr_val is not BaseNode:
            cls = attr_val
            # Store addon file and directory metadata on class for stale cleanup & icon resolution
            cls._addon_file = str(py_file.resolve())
            if resolved_addon_dir:
                cls._addon_dir = str(resolved_addon_dir.resolve())
            if icons_dir:
                cls._addon_icons_dir = str(icons_dir.resolve())

            # Assign category if not custom-specified
            current_cat = getattr(cls, "category", "")
            if not current_cat or current_cat in ("Custom", "General", "Misc"):
                cls.category = addon_name

            # Ensure type_id is registered
            if getattr(cls, "type_id", None):
                NODE_REGISTRY[cls.type_id] = cls

    return True


def discover_nodes(reload_modules: bool = False) -> List[str]:
    """
    Imports all .py files in `nodes/` and in all `custom_nodes/` directories so `@register_node` runs.
    Ensures custom nodes are recognized automatically without modifying plugin code.
    Returns a list of any load errors (isolated so broken nodes never crash IngeTrazo).
    """
    errors: List[str] = []
    nodes_dir = Path(__file__).resolve().parent
    pkg_name = __name__

    # 1. Ensure plugin root is in sys.path so node modules can import core_types and node_base
    parent_dir = str(nodes_dir.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    # Clean up stale custom nodes from deleted files or folders on reload
    if reload_modules:
        from node_base import NODE_REGISTRY
        stale_type_ids = []
        for tid, ncls in list(NODE_REGISTRY.items()):
            a_file = getattr(ncls, "_addon_file", None)
            a_dir = getattr(ncls, "_addon_dir", None)
            if a_file and not Path(a_file).exists():
                stale_type_ids.append(tid)
            elif a_dir and not Path(a_dir).exists():
                stale_type_ids.append(tid)
        for tid in stale_type_ids:
            NODE_REGISTRY.pop(tid, None)

    # 2. Discover built-in nodes inside nodes/
    for py_file in sorted(nodes_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        stem = py_file.stem
        loaded = False
        for mod_name in [f"{pkg_name}.{stem}", stem]:
            try:
                if mod_name in sys.modules:
                    if reload_modules:
                        importlib.reload(sys.modules[mod_name])
                    loaded = True
                    break
                else:
                    importlib.import_module(mod_name)
                    loaded = True
                    break
            except Exception:
                continue

        if not loaded:
            _load_py_file(py_file, reload_modules, errors)

    # 3. Discover user custom nodes & addon packages in custom_nodes/ directories
    seen_files = set()
    for c_dir in get_custom_nodes_dirs():
        if not c_dir.is_dir():
            continue

        c_str = str(c_dir)
        if c_str not in sys.path:
            sys.path.insert(0, c_str)

        # Scan entries inside the custom_nodes folder
        for item in sorted(c_dir.iterdir()):
            if item.name.startswith((".", "_")) or item.name == "__pycache__":
                continue

            # CASE A: Addon folder (e.g. custom_nodes/seg_nodes/ or custom_nodes/Seg Nodes/)
            if item.is_dir():
                addon_dir = item
                addon_str = str(addon_dir)
                if addon_str not in sys.path:
                    sys.path.insert(0, addon_str)

                # Default addon name derived from folder name
                folder_addon_name = item.name.replace("_", " ").strip().title()

                # Find all .py files in this addon folder
                init_file = addon_dir / "__init__.py"
                all_py = sorted(addon_dir.rglob("*.py"))
                # If __init__.py exists, load it first
                if init_file.is_file():
                    all_py = [init_file] + [f for f in all_py if f != init_file]

                for py_file in all_py:
                    if py_file.name.startswith(".") or "__pycache__" in py_file.parts:
                        continue
                    resolved = py_file.resolve()
                    if resolved in seen_files:
                        continue
                    seen_files.add(resolved)
                    _load_py_file(
                        py_file,
                        reload_modules=reload_modules,
                        errors=errors,
                        default_category=folder_addon_name,
                        addon_dir=addon_dir,
                    )

            # CASE B: Single-file Addon directly in custom_nodes/ (e.g. custom_nodes/seg nodes.py)
            elif item.is_file() and item.suffix.lower() == ".py":
                resolved = item.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)
                file_addon_name = item.stem.replace("_", " ").strip().title()
                _load_py_file(
                    item,
                    reload_modules=reload_modules,
                    errors=errors,
                    default_category=file_addon_name,
                    addon_dir=item.parent,
                )

    return errors
