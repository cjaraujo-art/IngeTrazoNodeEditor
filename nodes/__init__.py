# SPDX-License-Identifier: GPL-3.0-or-later
"""Auto-discovery and hot-reloader for custom node modules."""

from __future__ import annotations
import importlib
import importlib.util
from pathlib import Path
import sys
import traceback


def discover_nodes(reload_modules: bool = False) -> list[str]:
    """
    Imports all .py files in the `nodes/` directory so `@register_node` decorators run.
    Returns a list of any load errors (isolated so a broken custom node never crashes IngeTrazo).
    """
    errors: list[str] = []
    nodes_dir = Path(__file__).resolve().parent
    pkg_name = __name__

    # Ensure parent dir is in sys.path so node modules can import core_types and node_base
    parent_dir = str(nodes_dir.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    for py_file in sorted(nodes_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        stem = py_file.stem
        # Try both package-qualified import and direct import
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
            # Fallback to direct file execution via spec
            try:
                mod_id = f"ingetrazo_node_{stem}"
                spec = importlib.util.spec_from_file_location(mod_id, str(py_file))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_id] = mod
                    spec.loader.exec_module(mod)
                    loaded = True
            except Exception as exc:
                errors.append(f"{py_file.name}: {exc}\n{traceback.format_exc()}")

    return errors
