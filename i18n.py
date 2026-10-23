# SPDX-License-Identifier: GPL-3.0-or-later
"""
Internationalization (i18n) and localization module for IngeTrazo Node Editor.
Provides translation dictionary loading, dynamic language discovery, and live UI re-translation.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_CURRENT_LANG: str = "en"
_TRANSLATIONS: Dict[str, str] = {}
_FALLBACK_TRANSLATIONS: Dict[str, str] = {}
_AVAILABLE_LANGUAGES: Dict[str, Dict[str, str]] = {}
_LISTENERS: List[Callable[[str], None]] = []
_INITIALIZED: bool = False

LANGUAGES_DIR = Path(__file__).resolve().parent / "languages"
CONFIG_FILE = Path.home() / ".ingetrazo_node_editor_config.json"


def _load_json_file(file_path: Path) -> Dict[str, Any]:
    """Safely load and parse a JSON translation file."""
    if not file_path.is_file():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as ex:
        print(f"[i18n] Error loading {file_path}: {ex}")
        return {}


def _discover_languages() -> None:
    """Scans the languages/ directory for all *.json files and reads their metadata."""
    global _AVAILABLE_LANGUAGES
    _AVAILABLE_LANGUAGES.clear()

    if not LANGUAGES_DIR.is_dir():
        try:
            LANGUAGES_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return

    for p in sorted(LANGUAGES_DIR.glob("*.json")):
        code = p.stem.lower()
        data = _load_json_file(p)
        meta = data.get("_meta", {})
        _AVAILABLE_LANGUAGES[code] = {
            "code": code,
            "name": meta.get("name", code.upper()),
            "native": meta.get("native", meta.get("name", code.upper())),
            "flag": meta.get("flag", "🌐"),
            "file": str(p),
        }


def _load_translations(code: str) -> Dict[str, str]:
    """Extract flat translation key-value map from a language JSON file."""
    file_path = LANGUAGES_DIR / f"{code.lower()}.json"
    data = _load_json_file(file_path)
    # Support both flat JSON and categorized JSON (translations section)
    if "translations" in data and isinstance(data["translations"], dict):
        return data["translations"]
    return {k: str(v) for k, v in data.items() if not k.startswith("_")}


def _load_persisted_lang() -> str:
    """Reads the persisted language code from the user configuration file."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return str(cfg.get("language", "en")).lower()
        except Exception:
            pass
    return "en"


def _save_persisted_lang(code: str) -> None:
    """Persists the selected language code to user configuration file."""
    try:
        cfg = {}
        if CONFIG_FILE.is_file():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
        cfg["language"] = code
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as ex:
        print(f"[i18n] Could not persist language selection: {ex}")


def init(default_lang: Optional[str] = None) -> None:
    """Initializes the translation system, loading all available languages."""
    global _CURRENT_LANG, _TRANSLATIONS, _FALLBACK_TRANSLATIONS, _INITIALIZED
    _discover_languages()

    # Load English as universal fallback
    _FALLBACK_TRANSLATIONS = _load_translations("en")

    target_lang = default_lang or _load_persisted_lang()
    if target_lang not in _AVAILABLE_LANGUAGES and "en" in _AVAILABLE_LANGUAGES:
        target_lang = "en"

    _CURRENT_LANG = target_lang
    if _CURRENT_LANG == "en":
        _TRANSLATIONS = _FALLBACK_TRANSLATIONS
    else:
        _TRANSLATIONS = _load_translations(_CURRENT_LANG)

    _INITIALIZED = True


def get_available_languages() -> List[Dict[str, str]]:
    """Returns a list of available language dictionaries sorted by display name."""
    if not _INITIALIZED:
        init()
    # Preferred ordering for quick selection
    codes = list(_AVAILABLE_LANGUAGES.keys())
    preferred = ["en", "ar", "fr", "zh"]
    sorted_codes = [c for c in preferred if c in codes] + [c for c in sorted(codes) if c not in preferred]
    return [_AVAILABLE_LANGUAGES[c] for c in sorted_codes]


def get_current_language() -> str:
    """Returns the currently active language code (e.g. 'en', 'fr')."""
    if not _INITIALIZED:
        init()
    return _CURRENT_LANG


def get_current_language_meta() -> Dict[str, str]:
    """Returns metadata for the currently active language."""
    if not _INITIALIZED:
        init()
    return _AVAILABLE_LANGUAGES.get(_CURRENT_LANG, {
        "code": _CURRENT_LANG,
        "name": _CURRENT_LANG.upper(),
        "flag": "🌐"
    })


def set_language(code: str, notify: bool = True) -> bool:
    """
    Sets active language, loads its translation dictionary, persists selection,
    and notifies all registered UI listeners.
    """
    global _CURRENT_LANG, _TRANSLATIONS
    code = code.lower().strip()
    if not _INITIALIZED:
        init()

    if code not in _AVAILABLE_LANGUAGES:
        # Check if file exists on disk
        target_file = LANGUAGES_DIR / f"{code}.json"
        if target_file.is_file():
            _discover_languages()
        else:
            return False

    _CURRENT_LANG = code
    if code == "en":
        _TRANSLATIONS = _FALLBACK_TRANSLATIONS
    else:
        _TRANSLATIONS = _load_translations(code)

    _save_persisted_lang(code)

    if notify:
        for cb in list(_LISTENERS):
            try:
                cb(code)
            except Exception as ex:
                print(f"[i18n] Error executing listener callback: {ex}")

    return True


def register_language_listener(callback: Callable[[str], None]) -> None:
    """Registers a callback function to be called when the active language changes."""
    if callback not in _LISTENERS:
        _LISTENERS.append(callback)


def unregister_language_listener(callback: Callable[[str], None]) -> None:
    """Removes a registered language listener callback."""
    if callback in _LISTENERS:
        _LISTENERS.remove(callback)


def tr(text_or_key: str, default: Optional[str] = None) -> str:
    """
    Translates a given string or lookup key into the currently active language.
    Falls back to English if untranslated in the active language, and finally
    to `default` or the original `text_or_key`.
    """
    if not _INITIALIZED:
        init()

    if not text_or_key:
        return text_or_key

    # Check active language
    val = _TRANSLATIONS.get(text_or_key)
    if val is not None and val != "":
        return val

    # Fallback to English
    val_fb = _FALLBACK_TRANSLATIONS.get(text_or_key)
    if val_fb is not None and val_fb != "":
        return val_fb

    return default if default is not None else text_or_key


def reload_languages() -> None:
    """Forces re-scanning of the languages directory and reloads dictionaries."""
    global _INITIALIZED
    _INITIALIZED = False
    init(_CURRENT_LANG)
