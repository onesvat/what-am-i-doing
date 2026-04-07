from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from what_am_i_doing.categories import (
    CATEGORY_CATALOG,
    get_category_definition,
    get_icon_for_path,
    get_description_for_path,
    resolve_category_paths,
    validate_category_path,
    catalog_as_choices,
)


class CategoriesTest(unittest.TestCase):
    def test_catalog_has_expected_categories(self) -> None:
        names = [cat.name for cat in CATEGORY_CATALOG]
        expected = [
            "coding",
            "research",
            "writing",
            "communication",
            "admin",
            "media",
            "gaming",
            "browsing",
            "adult",
            "break",
        ]
        self.assertEqual(expected, names)

    def test_get_category_definition_returns_definition(self) -> None:
        cat = get_category_definition("coding")
        self.assertIsNotNone(cat)
        self.assertEqual("coding", cat.name)
        self.assertEqual("laptop-symbolic", cat.icon)

    def test_get_category_definition_returns_none_for_unknown(self) -> None:
        cat = get_category_definition("unknown_category")
        self.assertIsNone(cat)

    def test_get_icon_for_path_returns_category_icon(self) -> None:
        icon = get_icon_for_path("coding")
        self.assertEqual("laptop-symbolic", icon)

    def test_get_icon_for_path_returns_parent_icon_for_child(self) -> None:
        icon = get_icon_for_path("communication/email")
        self.assertEqual("mail-unread-symbolic", icon)

    def test_get_icon_for_path_returns_fallback_for_unknown(self) -> None:
        icon = get_icon_for_path("unknown")
        self.assertEqual("applications-system-symbolic", icon)

    def test_get_description_for_path_returns_category_description(self) -> None:
        desc = get_description_for_path("coding")
        self.assertIn("Development", desc)

    def test_get_description_for_path_returns_subcategory_description(self) -> None:
        desc = get_description_for_path("communication/email")
        self.assertIn("Email", desc)

    def test_resolve_category_paths_expands_browsing(self) -> None:
        paths = resolve_category_paths(["browsing"])
        expected = [
            "browsing/social_media",
            "browsing/shopping",
            "browsing/news",
            "browsing/entertainment",
            "browsing/reference",
        ]
        self.assertEqual(expected, paths)

    def test_resolve_category_paths_keeps_selectable_subcategories(self) -> None:
        paths = resolve_category_paths(["communication/email"])
        self.assertEqual(["communication/email"], paths)

    def test_resolve_category_paths_keeps_top_level_without_subcategories(self) -> None:
        paths = resolve_category_paths(["coding"])
        self.assertEqual(["coding"], paths)

    def test_resolve_category_paths_keeps_selectable_top_level(self) -> None:
        paths = resolve_category_paths(["communication"])
        self.assertEqual(["communication"], paths)

    def test_validate_category_path_accepts_top_level(self) -> None:
        self.assertTrue(validate_category_path("coding"))
        self.assertTrue(validate_category_path("browsing"))

    def test_validate_category_path_accepts_known_subcategory(self) -> None:
        self.assertTrue(validate_category_path("communication/email"))
        self.assertTrue(validate_category_path("browsing/social_media"))

    def test_validate_category_path_rejects_unknown_subcategory(self) -> None:
        self.assertFalse(validate_category_path("coding/unknown"))

    def test_validate_category_path_rejects_unknown_category(self) -> None:
        self.assertFalse(validate_category_path("unknown"))

    def test_catalog_as_choices_returns_list(self) -> None:
        choices = catalog_as_choices()
        self.assertEqual(10, len(choices))
        self.assertEqual("coding", choices[0][0])


if __name__ == "__main__":
    unittest.main()
