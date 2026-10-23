# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import i18n


class TestI18n(unittest.TestCase):
    def setUp(self):
        # Reset i18n state to English for clean test baseline
        i18n.init("en")

    def tearDown(self):
        # Restore English at teardown
        i18n.set_language("en", notify=False)

    def test_available_languages(self):
        langs = i18n.get_available_languages()
        codes = [item["code"] for item in langs]
        self.assertIn("en", codes)
        self.assertIn("fr", codes)
        self.assertIn("zh", codes)
        self.assertIn("ar", codes)

        fr_meta = next(item for item in langs if item["code"] == "fr")
        self.assertEqual(fr_meta["name"], "French")
        self.assertEqual(fr_meta["native"], "Français")

        zh_meta = next(item for item in langs if item["code"] == "zh")
        self.assertEqual(zh_meta["name"], "Chinese (Simplified)")
        self.assertEqual(zh_meta["native"], "简体中文")

        ar_meta = next(item for item in langs if item["code"] == "ar")
        self.assertEqual(ar_meta["name"], "Arabic")
        self.assertEqual(ar_meta["native"], "العربية")

    def test_simplified_chinese_translation(self):
        success = i18n.set_language("zh", notify=False)
        self.assertTrue(success)
        self.assertEqual(i18n.get_current_language(), "zh")
        self.assertEqual(i18n.tr("Ready"), "就绪")
        self.assertEqual(i18n.tr("Curves"), "曲线")
        self.assertEqual(i18n.tr("Count X"), "X 数量")
        self.assertEqual(i18n.tr("Spacing X"), "X 间距")
        self.assertEqual(i18n.tr("Geometry"), "几何体")
        self.assertEqual(i18n.tr("Live Preview"), "实时预览")
        self.assertEqual(i18n.tr("🥐 Bake to IngeTrazo"), "🥐 烘焙到 IngeTrazo")

    def test_arabic_translation(self):
        success = i18n.set_language("ar", notify=False)
        self.assertTrue(success)
        self.assertEqual(i18n.get_current_language(), "ar")
        self.assertEqual(i18n.tr("Ready"), "جاهز")
        self.assertEqual(i18n.tr("Curves"), "المنحنيات")
        self.assertEqual(i18n.tr("Count X"), "عدد X")
        self.assertEqual(i18n.tr("Spacing X"), "المسافة X")
        self.assertEqual(i18n.tr("Geometry"), "الهندسة ثلاثية الأبعاد")
        self.assertEqual(i18n.tr("Live Preview"), "معاينة مباشرة")
        self.assertEqual(i18n.tr("🥐 Bake to IngeTrazo"), "🥐 تحويل إلى مشهد IngeTrazo")

    def test_english_translation(self):
        i18n.set_language("en", notify=False)
        self.assertEqual(i18n.get_current_language(), "en")
        self.assertEqual(i18n.tr("Ready"), "Ready")
        self.assertEqual(i18n.tr("Curves"), "Curves")
        self.assertEqual(i18n.tr("📋 Node Properties"), "📋 Node Properties")

    def test_french_translation(self):
        success = i18n.set_language("fr", notify=False)
        self.assertTrue(success)
        self.assertEqual(i18n.get_current_language(), "fr")
        self.assertEqual(i18n.tr("Ready"), "Prêt")
        self.assertEqual(i18n.tr("Curves"), "Courbes")
        self.assertEqual(i18n.tr("3D Solids"), "Solides 3D")
        self.assertEqual(i18n.tr("📋 Node Properties"), "📋 Propriétés du nœud")
        self.assertEqual(i18n.tr("Clear Face"), "Effacer la face")

    def test_node_terms_translation(self):
        i18n.set_language("fr", notify=False)
        # Ports from user's sample nodes
        self.assertEqual(i18n.tr("Count X"), "Nombre X")
        self.assertEqual(i18n.tr("Count Y"), "Nombre Y")
        self.assertEqual(i18n.tr("Spacing X"), "Espacement X")
        self.assertEqual(i18n.tr("Spacing Y"), "Espacement Y")
        self.assertEqual(i18n.tr("Radius (m)"), "Rayon (m)")
        self.assertEqual(i18n.tr("Height (m)"), "Hauteur (m)")
        self.assertEqual(i18n.tr("Base Pt"), "Pt de base")
        self.assertEqual(i18n.tr("Geometry"), "Géométrie")
        self.assertEqual(i18n.tr("Group Name"), "Nom de groupe")
        self.assertEqual(i18n.tr("BIM Tag"), "Balise BIM")
        self.assertEqual(i18n.tr("Live Preview"), "Aperçu en direct")
        self.assertEqual(i18n.tr("🥐 Bake to IngeTrazo"), "🥐 Figer dans IngeTrazo")
        self.assertEqual(i18n.tr("Baked"), "Figé")
        self.assertEqual(i18n.tr("Result"), "Résultat")

    def test_node_help_description_translation(self):
        import node_base
        import nodes
        nodes.discover_nodes()

        plane_cls = node_base.NODE_REGISTRY.get("vec.plane_normal")
        self.assertIsNotNone(plane_cls)
        plane_desc = plane_cls.description

        # In English
        i18n.set_language("en", notify=False)
        self.assertIn("Constructs an orthonormal 3D plane", i18n.tr(plane_desc))

        # In French
        i18n.set_language("fr", notify=False)
        fr_plane_desc = i18n.tr(plane_desc)
        self.assertIn("Construit un système de coordonnées de plan 3D", fr_plane_desc)
        self.assertNotIn("Constructs an orthonormal", fr_plane_desc)

    def test_fallback_to_english_and_raw_key(self):
        i18n.set_language("fr", notify=False)
        # Test key that exists in neither en nor fr: returns original key or default
        self.assertEqual(i18n.tr("NonExistentKey12345"), "NonExistentKey12345")
        self.assertEqual(i18n.tr("NonExistentKey12345", default="FallbackValue"), "FallbackValue")

    def test_listener_callback(self):
        notifications = []

        def on_lang_changed(code):
            notifications.append(code)

        i18n.register_language_listener(on_lang_changed)
        try:
            i18n.set_language("fr", notify=True)
            self.assertEqual(notifications, ["fr"])
            i18n.set_language("en", notify=True)
            self.assertEqual(notifications, ["fr", "en"])
        finally:
            i18n.unregister_language_listener(on_lang_changed)


if __name__ == "__main__":
    unittest.main()
