from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_compose_project import (
    UI_SEMANTIC_ARGUMENTS,
    extract_semantic_ui_calls,
    lexical_code_mask,
    local_value_expressions,
)


class SourceControlFlowTest(unittest.TestCase):
    def test_nested_if_else_and_implicit_foreach_context_are_preserved(self) -> None:
        body = """
Column {
    if (state.cards.isNotEmpty()) {
        if (state.cards.size < 2) {
            Text("One card")
        }
    } else {
        Text("No cards")
    }
    val items = listOf(Action.Send, Action.Pay)
    items.forEach {
        Icon(painter = painterResource(it.icon), contentDescription = null)
    }
}
"""

        calls = extract_semantic_ui_calls(
            relative="Home.kt",
            source_text=body,
            composable="Home",
            body=body,
            body_opening=0,
            associated_custom_images=set(),
            resolved_custom_composables={},
            resolved_custom_composable_parameters={},
        )
        texts = [call for call in calls if call["component"] == "Text"]
        icon = next(call for call in calls if call["component"] == "Icon")

        self.assertEqual(
            texts[0]["visibility_condition"]["expression"],
            "(state.cards.isNotEmpty()) && (state.cards.size < 2)",
        )
        self.assertEqual(
            texts[1]["visibility_condition"]["expression"],
            "!(state.cards.isNotEmpty())",
        )
        self.assertEqual(
            icon["list_item_context"],
            {"collection": "items", "item_parameter": "it"},
        )

    def test_async_image_model_and_multiline_builder_are_preserved(self) -> None:
        body = """
Column {
    val imageRequest = ImageRequest.Builder(context)
        .data(item.imageUrl)
        .crossfade(true)
        .build()
    AsyncImage(model = imageRequest, contentDescription = null)
}
"""

        self.assertIn("model", UI_SEMANTIC_ARGUMENTS)
        self.assertEqual(
            local_value_expressions(body, lexical_code_mask(body))["imageRequest"],
            "ImageRequest.Builder(context) .data(item.imageUrl) .crossfade(true) .build()",
        )

    def test_when_type_branches_inside_foreach_are_preserved(self) -> None:
        body = """
Column {
    items.forEach {
        when (it) {
            is MenuItem.Section -> {
                Text(text = it.title.asString())
            }
            is MenuItem.Item -> {
                Icon(painter = painterResource(it.entry.iconRes), contentDescription = null)
            }
        }
    }
}
"""

        calls = extract_semantic_ui_calls(
            relative="Profile.kt",
            source_text=body,
            composable="Profile",
            body=body,
            body_opening=0,
            associated_custom_images=set(),
            resolved_custom_composables={},
            resolved_custom_composable_parameters={},
        )
        text = next(call for call in calls if call["component"] == "Text")
        icon = next(call for call in calls if call["component"] == "Icon")

        self.assertEqual(
            text["visibility_condition"]["expression"],
            "it is MenuItem.Section",
        )
        self.assertEqual(
            icon["visibility_condition"]["expression"],
            "(it is MenuItem.Item) && !(it is MenuItem.Section)",
        )
        self.assertEqual(
            text["list_item_context"],
            {"collection": "items", "item_parameter": "it"},
        )

    def test_subjectless_when_expression_branches_are_preserved(self) -> None:
        body = """
Column {
    when {
        state.profile != null -> ProfileContent()
        state.isLoading -> ProfileSkeleton()
        else -> EmptyProfile()
    }
}
"""

        calls = extract_semantic_ui_calls(
            relative="Profile.kt",
            source_text=body,
            composable="Profile",
            body=body,
            body_opening=0,
            associated_custom_images=set(),
            resolved_custom_composables={
                "ProfileContent": [{"source": "Profile.kt", "composable": "ProfileContent"}],
                "ProfileSkeleton": [{"source": "Profile.kt", "composable": "ProfileSkeleton"}],
                "EmptyProfile": [{"source": "Profile.kt", "composable": "EmptyProfile"}],
            },
            resolved_custom_composable_parameters={},
        )
        by_component = {call["component"]: call for call in calls}

        self.assertEqual(
            by_component["ProfileContent"]["visibility_condition"]["expression"],
            "state.profile != null",
        )
        self.assertEqual(
            by_component["ProfileSkeleton"]["visibility_condition"]["expression"],
            "(state.isLoading) && !(state.profile != null)",
        )
        self.assertEqual(
            by_component["EmptyProfile"]["visibility_condition"]["expression"],
            "!(state.profile != null || state.isLoading)",
        )


if __name__ == "__main__":
    unittest.main()
