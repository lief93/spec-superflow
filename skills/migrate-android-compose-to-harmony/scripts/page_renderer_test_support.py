"""Minimal constructed contexts for layout-policy unit tests, not source fallbacks."""
from generate_arkui_page import Renderer
from ui_migration.arkui.fonts import FontRegistry
from ui_migration.arkui.layout import LayoutContext, LayoutPolicy
from ui_migration.arkui.typography import TypographyEmitter


def empty_renderer():
    page = {
        'by_id': {}, 'components': [], 'instances_by_call_id': {},
        'runtime_elided_source_components': [],
    }
    renderer = Renderer({'source': 'Fixture.kt', 'composable': 'Fixture'}, set(), {}, page)
    renderer.typography = TypographyEmitter(FontRegistry([]), renderer.layout, renderer.add_page_json_unresolved)
    return renderer


def layout_policy(renderer):
    renderer.layout = LayoutPolicy(LayoutContext(
        renderer.android_page_by_id, renderer.android_page_layout_mode,
        renderer.android_source_layout_by_subject, renderer._page_constraint_states,
        renderer._page_match_parent_sizes, renderer.record_page_paths,
        renderer.record_page_layout_rule, renderer.add_page_json_unresolved, renderer.lengths,
    ))
    renderer.typography = TypographyEmitter(FontRegistry(renderer.verified_font_faces),
                                            renderer.layout, renderer.add_page_json_unresolved)
    renderer.leaves.layout = renderer.layout
    return renderer.layout
