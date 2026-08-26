#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ASSET = (
    Path(__file__).parents[1]
    / "assets"
    / "ohos-uitest-component-bounds"
    / "ComponentBounds.ets"
)

ANDROID_ASSET = (
    Path(__file__).parents[1]
    / "assets"
    / "android-compose-uitest-component-bounds"
    / "ComponentBounds.kt"
)

ANDROID_SEMANTICS_ASSET = (
    Path(__file__).parents[1]
    / "assets"
    / "android-compose-uitest-component-bounds"
    / "ComposeSemanticsComponentBounds.kt"
)

LOCAL_COMPARISON_REFERENCE = (
    Path(__file__).parents[1] / "references" / "local-image-comparison.md"
)

COMPOSE_MAPPING_REFERENCE = (
    Path(__file__).parents[1] / "references" / "compose-arkui-mapping.md"
)


class ComponentBoundsAssetTests(unittest.TestCase):
    def test_asset_exports_sanitized_runtime_bounds_without_display_content(self) -> None:
        source = ASSET.read_text(encoding="utf-8")

        self.assertIn("collectComponentBounds", source)
        self.assertIn("android-to-harmony.component-bounds.v1", source)
        self.assertIn("driver.getDisplaySize()", source)
        self.assertIn("driver.findComponent(ON.id(descriptor.id))", source)
        self.assertIn("component.getType()", source)
        self.assertIn("component.getBounds()", source)
        self.assertNotIn("getText()", source)
        self.assertNotIn("getDescription()", source)
        self.assertNotIn("getHint()", source)

    def test_android_asset_captures_tagged_compose_bounds_without_display_content(self) -> None:
        source = ANDROID_ASSET.read_text(encoding="utf-8")

        self.assertIn("captureComponentBoundsAndScreenshot", source)
        self.assertIn("ANDROID_COMPONENT_BOUNDS:", source)
        self.assertIn("android-to-harmony.component-bounds.v1", source)
        self.assertIn("uiAutomation.rootInActiveWindow", source)
        self.assertIn("viewIdResourceName", source)
        self.assertIn("getBoundsInScreen", source)
        self.assertIn("uiAutomation.takeScreenshot()", source)
        self.assertNotIn("ComposeContentTestRule", source)
        self.assertNotIn("onNodeWithText", source)
        self.assertNotIn("contentDescription", source)

    def test_legacy_compose_asset_uses_semantics_bounds_without_display_content(self) -> None:
        source = ANDROID_SEMANTICS_ASSET.read_text(encoding="utf-8")

        self.assertIn("captureComposeSemanticsComponentBoundsAndScreenshot", source)
        self.assertIn("boundsForTag: (String) -> Rect?", source)
        self.assertIn("composeRootX", source)
        self.assertIn("composeRootY", source)
        self.assertIn("uiAutomation.takeScreenshot()", source)
        self.assertNotIn("testTagsAsResourceId", source)
        self.assertNotIn("onNodeWithText", source)
        self.assertNotIn("contentDescription", source)

    def test_android_capture_workflow_documents_animation_safe_source_mapping(self) -> None:
        local_reference = LOCAL_COMPARISON_REFERENCE.read_text(encoding="utf-8")
        mapping_reference = COMPOSE_MAPPING_REFERENCE.read_text(encoding="utf-8")

        self.assertIn("testTagsAsResourceId", local_reference)
        self.assertIn("ActivityScenario", local_reference)
        self.assertIn("extract_android_component_bounds.py", local_reference)
        self.assertIn("permanent Compose animations", local_reference)
        self.assertIn("ComposeSemanticsComponentBounds.kt", local_reference)
        self.assertIn("does not provide `testTagsAsResourceId`", local_reference)
        self.assertIn("mainClock.autoAdvance = false", local_reference)
        self.assertIn("RowScope", mapping_reference)
        self.assertIn("layoutWeight", mapping_reference)


if __name__ == "__main__":
    unittest.main()
