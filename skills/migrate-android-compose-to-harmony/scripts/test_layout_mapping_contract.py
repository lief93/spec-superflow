from __future__ import annotations

import copy
import argparse
import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from component_required_facts import build_required_facts, normalized_layout_rules
from generate_arkui_page import ArkUIPageError, Renderer, build_target_phase_consumption_gate, load_lanhu_page_input, derive_page_root, load_page_font_faces
from generate_lanhu_source_page import SourceLayout, SourceTree, resolved_alignment, page_font_faces, non_rendering_argument_calls, generate as generate_source
from real_page_pipeline import static_style_for_call
from test_generate_lanhu_source_page import source_component


def layout(nodes, width=300, height=200):
    return SourceLayout(SourceTree({
        'schema': 'android-to-harmony.source-page-spec.v1',
        'page': {'id': 'layout', 'state': 'default'},
        'root': {'source': 'Layout.kt', 'composable': 'Layout'},
        'components': nodes,
    }), width, height).calculate()


def render_nodes(nodes, width=300, height=200, perturb_reference_frames=False, resources=None, font_faces=None):
    nodes = copy.deepcopy(nodes)
    for node in nodes:
        node['source']['attributes'] = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / 'source.json'
        source.write_text(json.dumps({
            'schema': 'android-to-harmony.source-page-spec.v1',
            'page': {'id': 'layout', 'state': 'default'},
            'root': {'source': 'app/src/main/java/example/HomeScreen.kt', 'composable': 'HomeScreen'},
            'components': nodes,
        }))
        generate_source(argparse.Namespace(source_page=source, state_fixture=None,
            output_dir=root / 'page', viewport_width_dp=width, viewport_height_dp=height,
            slice_scale=2, device='layout-test'))
        page = load_lanhu_page_input(root / 'page/version_json.json')
        if perturb_reference_frames:
            for component in page['components']:
                if component.get('parent_id') is not None:
                    for field in ('bounds_dp', 'source_layout_bounds_dp'):
                        if isinstance(component.get(field), dict):
                            component[field] = {**component[field], 'width': 213.7, 'height': 93.6}
        renderer = Renderer(derive_page_root(page), resources or set(), {}, page)
        renderer.verified_font_faces = font_faces or []
        output = renderer.render()
        gate = build_target_phase_consumption_gate(page, renderer.android_page_processed_component_ids,
            set(), {}, renderer.android_page_applied_component_paths)
        return output, gate, renderer


class LayoutMappingContractTest(unittest.TestCase):
    def test_compose_border_is_draw_only_not_parent_measure(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0, width_dp=100, height_dp=40)
        root['style']['surface']['border'] = {'width_dp': 1, 'color': '#FF123456', 'style': 'solid'}
        output, gate, _ = render_nodes([root])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        parent = output[output.index(".id('root')"):]
        self.assertNotIn('.border({', parent)
        self.assertIn('.overlay(this.pageBorder0()', parent)
        self.assertIn('this.pageBorder0Width = current.width', parent)
        self.assertIn('.width(this.pageBorder0Width)', output)
        self.assertIn("Math.max(1, Math.ceil(this.getUIContext().vp2px(1))) + 'px'", output)
        self.assertIn('.hitTestBehavior(HitTestMode.Transparent)', output)

    def test_verified_text_uses_font_metrics_and_between_line_spacing(self):
        text = source_component('text', 'Text', parent_id=None, sibling_index=0,
                                text='Sample', font_size_sp=16)
        text['style']['typography'].update(font_family='SampleFont', font_weight=500, line_height_sp=28, color='#FF333333')
        faces = [{'alias': 'Sample500', 'match_names': ['samplefont'], 'weight': 500, 'rawfile': 'fonts/sample.ttf'}]
        output, gate, _ = render_nodes([text], font_faces=faces)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.halfLeading(true)', output)
        self.assertIn('.fontSize(this.nativeFontSize(16))', output)
        self.assertIn("Math.floor(this.getUIContext().fp2px(size)) + 'px'", output)
        self.assertIn(".lineHeight(this.nativeLineHeight($rawfile('fonts/sample.ttf'), 16))", output)
        self.assertIn(".constraintSize({ minHeight: this.nativeLineHeight($rawfile('fonts/sample.ttf'), 16) })", output)
        self.assertIn(".lineSpacing(this.nativeLineSpacing($rawfile('fonts/sample.ttf'), 16, 28), { onlyBetweenLines: true })", output)
        self.assertIn('font.getMetrics()', output)
        self.assertNotIn('.lineHeight(28)', output)
        text['style']['layout']['height_dp'] = 10
        output, gate, _ = render_nodes([text], font_faces=faces)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.height(this.layoutPx(10))', output)
        self.assertNotIn('.constraintSize({ minHeight: this.nativeLineHeight', output)

    def test_layout_pixels_use_runtime_density_not_reference_density(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0,
                                width_dp=48, height_dp=48)
        root['style']['layout']['padding_dp'] = dict.fromkeys(['left', 'right', 'top', 'bottom'], 4)
        output, gate, _ = render_nodes([root])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.width(this.layoutPx(48))', output)
        self.assertIn('.padding(this.layoutPx(4))', output)
        self.assertIn("Math.round(this.getUIContext().vp2px(value)) + 'px'", output)

    def test_async_image_uses_model_url_without_preview_fallback(self):
        image = source_component('avatar', 'AsyncImage', parent_id=None, sibling_index=0,
                                 width_dp=48, height_dp=48)
        image['style']['asset'].update(resource='https://example.com/avatar.svg?seed=sample', content_scale='fit')
        output, gate, renderer = render_nodes([image])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(renderer.unresolved, [])
        self.assertIn("Image('https://example.com/avatar.svg?seed=sample')", output)
        self.assertNotIn('.alt(', output)
        for invalid in ('javascript:bad', 'file:///private/file', 'https://user:secret@example.com/image', 'https://[bad', 'missing_asset'):
            image['style']['asset']['resource'] = invalid
            _, gate, renderer = render_nodes([image])
            self.assertEqual(gate['verdict'], 'fail', invalid)
            self.assertTrue(renderer.unresolved)

    def test_clip_is_emitted_not_only_marked_consumed(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0,
                                width_dp=48, height_dp=48)
        root['style']['surface']['clip'] = True
        root['style']['surface']['corner_radius_dp'] = dict.fromkeys(
            ['top_left', 'top_right', 'bottom_left', 'bottom_right'], 24)
        output, gate, _ = render_nodes([root])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.clip(true)', output)
        root['style']['surface']['clip'] = False
        output, _, _ = render_nodes([root])
        self.assertNotIn('.clip(true)', output)

    def test_shadow_dp_fields_convert_to_runtime_pixels(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0,
                                width_dp=200, height_dp=100)
        for radius, dx, dy in ((20, 0, 4), (7.5, -3.5, 2.25), (0, 0, 0)):
            with self.subTest(radius=radius, dx=dx, dy=dy):
                root['style']['surface']['shadows'] = [{
                    'color': '#1A000000', 'blur_radius_dp': radius,
                    'offset_x_dp': dx, 'offset_y_dp': dy, 'spread_radius_dp': 0,
                }]
                output, gate, renderer = render_nodes([root])
                self.assertEqual(gate['verdict'], 'pass', gate['failures'])
                self.assertEqual(renderer.unresolved, [])
                self.assertIn(
                    '.shadow({ radius: this.getUIContext().vp2px(' + str(radius) + '), '
                    "color: '#1A000000', offsetX: this.getUIContext().vp2px(" + str(dx) + '), '
                    'offsetY: this.getUIContext().vp2px(' + str(dy) + ') })', output)
                wider, _, _ = render_nodes([root], width=450, height=900)
                self.assertEqual(output, wider)

    def test_image_intrinsic_size_is_distinct_from_source_modifier_size(self):
        call = {'source': 'Image.kt', 'line': 1, 'component': 'Image',
                'semantic_arguments': {'painter': {'expression': 'painterResource(R.drawable.circle)'}},
                'ordered_modifier_chain': [{'name': 'size', 'arguments': '48.dp, 24.dp'}]}
        style, _, unresolved = static_style_for_call(call, {}, None, asset_index={
            'circle': {'sha256': 'a' * 64, 'path': 'res/drawable/circle.xml', 'width_dp': 200, 'height_dp': 100},
        })
        self.assertEqual(unresolved, [])
        self.assertEqual((style['asset']['width_dp'], style['asset']['height_dp']), (200, 100))
        self.assertEqual((style['layout']['width_dp'], style['layout']['height_dp']), (48, 24))
        component = source_component('image', 'Image', parent_id=None, sibling_index=0)
        component['style'] = style
        component['modifiers'] = call['ordered_modifier_chain']
        facts = [f for f in build_required_facts(component) if f['origin'] == 'modifier']
        self.assertEqual({f['path'] for f in facts}, {'style.layout.width_dp', 'style.layout.height_dp'})
        self.assertTrue(all(f['status'] == 'resolved' for f in facts))

    def test_intrinsic_image_uses_bounded_native_measure_not_fixed_frame(self):
        root = source_component('root', 'BoxWithConstraints', parent_id=None, sibling_index=0,
                                width_dp=300, height_dp=136, children_ids=['image'])
        root['style']['layout']['alignment'] = 'TopEnd'
        image = source_component('image', 'Image', parent_id='root', sibling_index=0)
        image['style']['asset'].update(resource='circle', width_dp=200, height_dp=200, content_scale='fit')
        output, gate, _ = render_nodes([root, image], resources={'media:circle'})
        changed, _, _ = render_nodes([root, image], resources={'media:circle'}, perturb_reference_frames=True)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(output, changed)
        self.assertNotIn('.width(200)', output)
        self.assertNotIn('.height(200)', output)
        self.assertIn('.constraintSize({ maxWidth: 200, maxHeight: 200 })', output)
        self.assertIn('.aspectRatio(1)', output)
        image['style']['layout'].update(width_dp=48, height_dp=24)
        output, gate, _ = render_nodes([root, image], resources={'media:circle'})
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.width(this.layoutPx(48))', output)
        self.assertIn('.height(this.layoutPx(24))', output)
        self.assertNotIn('maxWidth: 200', output)

    def test_legacy_image_size_facts_require_regeneration(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0, children_ids=['image'])
        image = source_component('image', 'Image', parent_id='root', sibling_index=0)
        image['style']['asset'].update(resource='circle', width_dp=200, height_dp=200, content_scale='fit')
        _, _, renderer = render_nodes([root, image], resources={'media:circle'})
        component = renderer.android_page_by_id['image']
        component['required_facts'] = [{'path': 'style.asset.width_dp', 'origin': 'modifier', 'status': 'resolved'}]
        self.assertEqual(renderer.page_snapshot_intrinsic_image_lines(component), [])
        self.assertTrue(any('legacy image JSON' in item['reason'] for item in renderer.unresolved))

    def test_unsupported_intrinsic_scale_does_not_silently_use_fit(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0, children_ids=['image'])
        image = source_component('image', 'Image', parent_id='root', sibling_index=0)
        image['style']['asset'].update(resource='circle', width_dp=200, height_dp=200, content_scale='crop')
        _, gate, renderer = render_nodes([root, image], resources={'media:circle'})
        self.assertEqual(gate['verdict'], 'fail')
        self.assertTrue(any('intrinsic image measurement' in item['reason'] for item in renderer.unresolved))
        image['style']['layout'].update(width_dp=48, height_dp=24)
        output, gate, renderer = render_nodes([root, image], resources={'media:circle'})
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(renderer.unresolved, [])
        self.assertIn('.objectFit(ImageFit.Cover)', output)

    def test_wrap_text_and_wrappers_do_not_consume_estimated_dimensions(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['wrapper'])
        wrapper = source_component('wrapper', 'Column', parent_id='root', sibling_index=0, children_ids=['text'])
        text = source_component('text', 'Text', parent_id='wrapper', sibling_index=0)
        text['style']['content']['text'] = 'Sample'
        text['style']['typography'].update(font_size_sp=14, font_weight=400, color='#FF333333')
        nodes = [root, wrapper, text]
        output, gate, _ = render_nodes(nodes)
        changed, changed_gate, _ = render_nodes(nodes, perturb_reference_frames=True)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(changed_gate['verdict'], 'pass', changed_gate['failures'])
        self.assertEqual(output, changed)
        self.assertNotIn('.height(17.5)', output)
        self.assertNotIn('.constraintSize(', output)

    def test_explicit_text_size_and_constraints_are_still_emitted(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['text'])
        text = source_component('text', 'Text', parent_id='root', sibling_index=0, width_dp=90, height_dp=40)
        text['modifiers'] = [{'name': 'widthIn', 'arguments': 'min = 60.dp, max = 120.dp'}]
        text['style']['content']['text'] = 'Sample'
        text['style']['typography'].update(font_size_sp=14, font_weight=400, color='#FF333333')
        output, gate, _ = render_nodes([root, text])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('.width(this.layoutPx(90))', output)
        self.assertIn('.height(this.layoutPx(40))', output)
        self.assertIn('.constraintSize({ minWidth: this.layoutPx(60), maxWidth: this.layoutPx(120) })', output)

    def test_button_children_do_not_reintroduce_reference_size(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['button'])
        button = source_component('button', 'TextButton', parent_id='root', sibling_index=0, children_ids=['first', 'last'])
        nodes = [root, button]
        for index, name in enumerate(('first', 'last')):
            text = source_component(name, 'Text', parent_id='button', sibling_index=index, text=name, font_size_sp=14)
            text['style']['typography'].update(font_weight=400, color='#FF333333')
            nodes.append(text)
        output, gate, _ = render_nodes(nodes)
        changed, _, _ = render_nodes(nodes, perturb_reference_frames=True)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(output, changed)
        self.assertIn('.constraintSize({ minHeight: this.layoutPx(48) })', output)

    def test_custom_wrapper_forwards_width_rule_not_reference_frame(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['card'])
        card = source_component('card', 'CardContent', parent_id='root', sibling_index=0,
                                children_ids=['native'], definition_id='card-definition')
        card['source']['custom_component'] = True
        card['modifiers'] = [{'name': 'fillMaxWidth', 'arguments': ''}]
        native = source_component('native', 'Column', parent_id='card', sibling_index=0, children_ids=['label'])
        native['modifiers'] = copy.deepcopy(card['modifiers'])
        label = source_component('label', 'Text', parent_id='native', sibling_index=0, text='Native size', font_size_sp=14)
        label['style']['typography'].update(font_weight=400, color='#FF333333')
        output, gate, _ = render_nodes([root, card, native, label])
        changed, _, _ = render_nodes([root, card, native, label], perturb_reference_frames=True)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(output, changed)
        self.assertGreaterEqual(output.count(".width('100%')"), 3)

    def test_intrinsic_cross_axis_stretch_reaches_custom_component_surface(self):
        root = source_component('root', 'Row', parent_id=None, sibling_index=0, children_ids=['card'])
        root['modifiers'] = [{'name': 'height', 'arguments': 'IntrinsicSize.Max'}]
        card = source_component('card', 'CardContent', parent_id='root', sibling_index=0,
                                children_ids=['surface'], definition_id='card-definition')
        card['source']['custom_component'] = True
        card['modifiers'] = [{'name': 'fillMaxHeight', 'arguments': ''}]
        surface = source_component('surface', 'Box', parent_id='card', sibling_index=0, children_ids=['label'])
        surface['modifiers'] = copy.deepcopy(card['modifiers'])
        label = source_component('label', 'Text', parent_id='surface', sibling_index=0, text='Short', font_size_sp=14)
        label['style']['typography'].update(font_weight=400, color='#FF333333')
        nodes = [root, card, surface, label]
        output, gate, _ = render_nodes(nodes)
        changed, _, _ = render_nodes(nodes, perturb_reference_frames=True)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(output, changed)
        self.assertEqual(output.count('.alignSelf(ItemAlign.Stretch)'), 1)
        self.assertNotIn(".id('card')", output)
        self.assertNotRegex(output, r'\.height\([0-9]')

    def test_project_typography_overrides_framework_defaults(self):
        call = {'source': 'Button.kt', 'line': 1, 'component': 'Text',
                'semantic_arguments': {'style': {'expression': 'MaterialTheme.typography.titleSmall'}},
                'ordered_modifier_chain': []}
        styles = {'titleSmall': {'expression': 'TextStyle(fontSize = 16.sp, fontFamily = AppFont, fontWeight = FontWeight.SemiBold)'}}
        style, _, unresolved = static_style_for_call(call, {}, None, font_family_tokens={'AppFont'}, theme_text_styles=styles)
        self.assertEqual(style['typography']['font_size_sp'], 16)
        self.assertEqual(style['typography']['font_family'], 'AppFont')
        self.assertIsNone(style['typography']['line_height_sp'])
        self.assertEqual(unresolved, [])
        call['semantic_arguments']['fontSize'] = {'expression': '18.sp'}
        self.assertEqual(static_style_for_call(call, {}, None, theme_text_styles=styles)[0]['typography']['font_size_sp'], 18)

    def test_ambiguous_project_typography_is_not_a_framework_default(self):
        from real_page_pipeline import selected_theme_text_styles, RealPageError
        with self.assertRaises(RealPageError):
            selected_theme_text_styles({'theme_applications': [
                {'arguments': {'typography': {'expression': 'first'}}},
                {'arguments': {'typography': {'expression': 'second'}}},
            ], 'typography_sets': []})

    def test_project_typography_selection_uses_theme_application(self):
        from real_page_pipeline import selected_theme_text_styles
        actual = {'titleSmall': {'expression': 'TextStyle(fontSize = 16.sp)'}}
        inventory = {'typography_sets': [
            {'name': 'unused', 'styles': {}}, {'name': 'appStyles', 'styles': actual}],
            'theme_applications': [{'arguments': {'typography': {'expression': 'appStyles'}}}]}
        self.assertEqual(selected_theme_text_styles(inventory), actual)

    def test_width_height_overload_is_not_square(self):
        call = {'source': 'Layout.kt', 'line': 1, 'component': 'Box',
                'semantic_arguments': {}, 'ordered_modifier_chain': [{
                    'name': 'size', 'arguments': '48.dp, 24.dp',
                    'dimensions': [{'value': '48', 'unit': 'dp'}, {'value': '24', 'unit': 'dp'}],
                }]}
        style, _, unresolved = static_style_for_call(call, {}, None)
        self.assertEqual((style['layout']['width_dp'], style['layout']['height_dp']), (48, 24))
        self.assertEqual(unresolved, [])

    def test_weights_use_ratio_and_fill_false_keeps_intrinsic_content(self):
        row = source_component('row', 'Row', parent_id=None, sibling_index=0, children_ids=['a', 'b'])
        a = source_component('a', 'Box', parent_id='row', sibling_index=0, width_dp=20, height_dp=20)
        b = source_component('b', 'Box', parent_id='row', sibling_index=1, height_dp=20)
        a['modifiers'] = [{'name': 'weight', 'arguments': '1f'}]
        b['modifiers'] = [{'name': 'weight', 'arguments': '2f'}]
        frames = layout([row, a, b])
        self.assertEqual([frames[x]['width'] for x in ('a', 'b')], [100, 200])
        a['modifiers'][0]['arguments'] = '1f, fill = false'
        frames = layout([row, a, b])
        self.assertEqual([frames[x]['width'] for x in ('a', 'b')], [20, 200])

    def test_box_positional_enum_covers_all_nine_alignments(self):
        for value in ('TopStart', 'TopCenter', 'TopEnd', 'CenterStart', 'Center',
                      'CenterEnd', 'BottomStart', 'BottomCenter', 'BottomEnd'):
            with self.subTest(value=value):
                box = source_component('box', 'Box', parent_id=None, sibling_index=0)
                box['arguments'] = {'positional': [{'expression': 'Alignment.' + value}]}
                self.assertEqual(resolved_alignment(box), value)

    def test_minimum_constraints_are_normalized_and_affect_measurement(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['box'])
        box = source_component('box', 'Box', parent_id='root', sibling_index=0, width_dp=40)
        box['modifiers'] = [{'name': 'heightIn', 'arguments': 'min = 80.dp, max = 120.dp'}]
        self.assertTrue(normalized_layout_rules(box))
        box['required_facts'] = build_required_facts(box)
        self.assertTrue(any(x['path'].startswith('source.') for x in box['required_facts']))
        self.assertEqual(layout([root, box])['box']['height'], 80)

    def test_fill_fraction_changes_source_measurement(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['box'])
        box = source_component('box', 'Box', parent_id='root', sibling_index=0, height_dp=20)
        box['modifiers'] = [{'name': 'fillMaxWidth', 'arguments': '0.5f'}]
        self.assertEqual(layout([root, box])['box']['width'], 150)

    def test_unresolved_fraction_is_not_replaced_with_full_width(self):
        box = {'modifiers': [{'name': 'fillMaxWidth', 'arguments': 'fraction'}]}
        rules = normalized_layout_rules(box)
        self.assertFalse(any(x.get('fraction') == 1 for x in rules))

    def test_unhandled_fields_cannot_pass_using_component_bounds(self):
        for path, value in [('alignment', 'End'), ('margin_dp', {'left': 12}), ('aspect_ratio', 2)]:
            c = {'id': 'box', 'type': 'Box', 'style': {'layout': {path: value}}}
            gate = build_target_phase_consumption_gate({'components': [c]}, {'box'}, set(), {},
                {'box': {'bounds_dp.width', 'bounds_dp.height', 'source_layout_bounds_dp'}})
            self.assertEqual(gate['verdict'], 'fail', path)

    def test_normalized_modifier_must_be_consumed_by_exact_path(self):
        c = {'id': 'box', 'type': 'Box', 'required_facts': [{
            'path': 'source.modifiers.align', 'status': 'resolved', 'expression': 'Alignment.End',
        }]}
        gate = build_target_phase_consumption_gate({'components': [c]}, {'box'}, set(), {}, {})
        self.assertEqual(gate['verdict'], 'fail')

    def test_spaced_by_alignment_is_not_silently_dropped(self):
        renderer = object.__new__(Renderer)
        c = {'id': 'column', 'type': 'Column', 'style': {'layout': {
            'alignment': 'Start',
            'vertical_arrangement': 'Arrangement.spacedBy(8.dp, Alignment.CenterVertically)',
        }}}
        self.assertEqual(renderer.page_snapshot_arrangement_space(c), '8')
        self.assertIn('.justifyContent(FlexAlign.Center)', renderer.page_snapshot_container_alignment_lines(c))

    def test_weight_fill_flag_is_preserved_for_target(self):
        c = {'id': 'box', 'type': 'Box', 'source': {'layoutRules': [{
            'kind': 'weight', 'value': 1, 'fill': False, 'source_modifier_index': 0,
        }]}}
        # A fill=false child must not itself become a forced-size weighted node.
        self.assertIsNone(Renderer.page_snapshot_source_layout_weight(c))

    def test_nested_scroll_has_required_fact_and_actual_scroll_container(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['row'])
        root['modifiers'] = [{'name': 'then', 'arguments': 'Modifier.verticalScroll(rememberScrollState())'}]
        row = source_component('row', 'Box', parent_id='root', sibling_index=0, width_dp=100, height_dp=600)
        row['style']['surface']['background'] = {'type': 'solid', 'color': '#FF112233'}
        output, gate, _ = render_nodes([root, row])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertIn('Scroll() {', output)
        self.assertIn('.scrollable(ScrollDirection.Vertical)', output)
        self.assertIn('.height(this.layoutPx(600))', output)
        self.assertNotIn('.position(', output)
        self.assertTrue(any(c['path'] == 'source.modifiers.verticalscroll' and c['status'] == 'consumed' for c in gate['checks']))

    def test_unknown_container_and_fill_false_fail_in_actual_renderer(self):
        for component_type, modifiers in [('UnsupportedLayout', []), ('Box', [{'name': 'weight', 'arguments': '1f, fill=false'}])]:
            root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['box'])
            box = source_component('box', component_type, parent_id='root', sibling_index=0, children_ids=['leaf'])
            box['modifiers'] = modifiers
            leaf = source_component('leaf', 'Box', parent_id='box', sibling_index=0, width_dp=30, height_dp=30)
            leaf['style']['surface']['background'] = {'type': 'solid', 'color': '#FF112233'}
            _, gate, renderer = render_nodes([root, box, leaf])
            self.assertEqual(gate['verdict'], 'fail')
            self.assertTrue(renderer.unresolved)

    def test_shared_source_call_does_not_hide_missing_instance_consumption(self):
        components = [{'id': key, 'source': {'call_id': 'same-call'}, 'style': {'layout': {'width_dp': 20}}} for key in ('a', 'b')]
        gate = build_target_phase_consumption_gate({'components': components}, {'a', 'b'}, {'same-call'},
            {'same-call': {'style.layout.width_dp'}}, {'a': {'style.layout.width_dp'}})
        self.assertEqual([(x['component_id'], x['path']) for x in gate['failures']], [('b', 'style.layout.width_dp')])

    def test_symbolic_fact_cannot_pass_with_matching_path(self):
        c = {'id': 'box', 'required_facts': [{'path': 'style.layout.padding_dp', 'status': 'symbolic'}]}
        gate = build_target_phase_consumption_gate({'components': [c]}, {'box'}, set(), {},
            {'box': {'style.layout.padding_dp'}})
        self.assertEqual(gate['verdict'], 'fail')

    def test_fill_fraction_survives_box_parent(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0, children_ids=['child'])
        child = source_component('child', 'Box', parent_id='root', sibling_index=0, height_dp=20)
        child['modifiers'] = [{'name': 'fillMaxWidth', 'arguments': '0.5f'}]
        self.assertEqual(layout([root, child])['child']['width'], 150)

    def test_unknown_modifier_is_not_silently_dropped(self):
        c = source_component('box', 'Box', parent_id=None, sibling_index=0)
        c['modifiers'] = [{'name': 'customUnimplementedLayout', 'arguments': ''}]
        facts = build_required_facts(c)
        self.assertTrue(any(f['path'] == 'source.modifiers.customunimplementedlayout' and f['status'] == 'unresolved' for f in facts))

    def test_small_material_top_bar_includes_content_height_and_padding(self):
        root = source_component('root', 'Column', parent_id=None, sibling_index=0, children_ids=['bar'])
        bar = source_component('bar', 'CenterAlignedTopAppBar', parent_id='root', sibling_index=0,
                               padding_dp={'left': 0, 'right': 0, 'top': 16, 'bottom': 0})
        self.assertEqual(layout([root, bar])['bar']['height'], 80)

    def test_font_definition_becomes_json_faces_and_target_bytes_are_verified(self):
        text = source_component('title', 'Text', parent_id=None, sibling_index=0)
        text['style']['typography']['font_family'] = 'primaryFontFamily'
        source = {'components': [text], 'source_tokens': [{'kind': 'font_family', 'name': 'primaryFontFamily',
            'expression': 'FontFamily(Font(R.font.example, FontWeight.SemiBold))'}]}
        faces = page_font_faces(source)
        self.assertEqual(faces, [{'family': 'primaryFontFamily', 'resource': 'example', 'weight': 600}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = 'entry/src/main/resources/rawfile/fonts/example.ttf'
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b'font integrity fixture')
            (root / '.migration').mkdir()
            (root / '.migration/assets.json').write_text(json.dumps({'schema': 'android-to-harmony.asset-ledger.v1',
                'assets': {relative: {'asset_path': 'app/src/main/res/font/example.ttf',
                    'destination_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}}))
            verified = load_page_font_faces(root, 'entry', {'font_faces': faces})
            self.assertEqual(verified[0]['weight'], 600)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ArkUIPageError, 'hash/path mismatch'):
                load_page_font_faces(root, 'entry', {'font_faces': faces})

    def test_scroll_retains_offscreen_children_and_native_layout(self):
        root = source_component('root', 'LazyColumn', parent_id=None, sibling_index=0,
                                children_ids=[f'row{i}' for i in range(10)])
        rows = [source_component(f'row{i}', 'Box', parent_id='root', sibling_index=i,
                                 width_dp=100, height_dp=80) for i in range(10)]
        for row in rows:
            row['style']['surface']['background'] = {'type': 'solid', 'color': '#FF112233'}
        output, gate, _ = render_nodes([root, *rows])
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertEqual(output.count('.height(this.layoutPx(80))'), 10)
        self.assertIn(".id('row9')", output)
        self.assertIn('Scroll() {', output)
        self.assertNotIn('.position(', output)

    def test_spacer_inside_box_is_not_illegal_arkui_blank(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0, children_ids=['space'])
        spacer = source_component('space', 'Spacer', parent_id='root', sibling_index=0, height_dp=16)
        output, gate, _ = render_nodes([root, spacer])
        self.assertNotIn('Blank()', output)
        self.assertEqual(gate['verdict'], 'pass')

    def test_image_property_helper_is_not_a_visual_child(self):
        parent = source_component('image', 'AsyncImage', parent_id=None, sibling_index=0, children_ids=['helper'])
        parent['arguments'] = {'semantic': {'placeholder': {'expression': 'makePainter(R.drawable.avatar)'}}}
        helper = source_component('helper', 'makePainter', parent_id='image', sibling_index=0)
        self.assertEqual(non_rendering_argument_calls({'components': [parent, helper]}), ['helper'])
        helper['type'] = 'Badge'
        self.assertEqual(non_rendering_argument_calls({'components': [parent, helper]}), [])

    def test_ordered_padding_size_cannot_pass_as_flat_properties(self):
        c = source_component('box', 'Box', parent_id=None, sibling_index=0, width_dp=48)
        c['modifiers'] = [{'name': 'padding', 'arguments': '8.dp'}, {'name': 'width', 'arguments': '48.dp'}]
        self.assertTrue(any(f['path'] == 'source.modifiers.order' and f['status'] == 'unresolved' for f in build_required_facts(c)))

    def test_missing_offset_rule_is_unresolved_not_inferred_from_bbox(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0,
                                width_dp=300, height_dp=200, children_ids=['child'])
        root['style']['layout']['alignment'] = 'Center'
        child = source_component('child', 'Box', parent_id='root', sibling_index=0, width_dp=40, height_dp=20)
        child['modifiers'] = [{'name': 'offset', 'arguments': 'x = 12.dp, y = -4.dp'}]
        _, _, original = render_nodes([root, child])
        page = copy.deepcopy(original.android_page_input)
        component = page['by_id']['child']
        component['source']['layoutRules'] = []
        component['source_layout_bounds_dp'].update(x=171, y=117)
        renderer = Renderer(derive_page_root(page), set(), {}, page)
        output = renderer.render()
        self.assertNotIn('.translate(', output)
        self.assertTrue(any(item.get('path') == 'source.modifiers.offset' for item in renderer.unresolved))
        gate = build_target_phase_consumption_gate(page, renderer.android_page_processed_component_ids,
            set(), {}, renderer.android_page_applied_component_paths)
        self.assertEqual(gate['verdict'], 'fail')

    def test_box_alignment_and_child_override_do_not_depend_on_bbox(self):
        alignments = {'TopStart': 'TopStart', 'TopCenter': 'Top', 'TopEnd': 'TopEnd',
                      'CenterStart': 'Start', 'Center': 'Center', 'CenterEnd': 'End',
                      'BottomStart': 'BottomStart', 'BottomCenter': 'Bottom', 'BottomEnd': 'BottomEnd'}
        for source_alignment, target_alignment in alignments.items():
            with self.subTest(alignment=source_alignment):
                root = source_component('root', 'Box', parent_id=None, sibling_index=0,
                                        width_dp=300, height_dp=200, children_ids=['child'])
                root['style']['layout']['alignment'] = source_alignment
                child = source_component('child', 'Box', parent_id='root', sibling_index=0, width_dp=40, height_dp=20)
                child['modifiers'] = [{'name': 'align', 'arguments': 'Alignment.BottomEnd'}]
                output, gate, _ = render_nodes([root, child])
                changed, _, _ = render_nodes([root, child], perturb_reference_frames=True)
                self.assertEqual(output, changed)
                self.assertEqual(gate['verdict'], 'pass', gate['failures'])
                self.assertIn('.alignContent(Alignment.' + target_alignment + ')', output)
                self.assertIn('.align(Alignment.BottomEnd)', output)
                self.assertNotIn('.position(', output)
                self.assertNotIn('.translate(', output)

    def test_constant_offset_uses_rule_not_component_bbox(self):
        root = source_component('root', 'Box', parent_id=None, sibling_index=0,
                                width_dp=300, height_dp=200, children_ids=['child'])
        child = source_component('child', 'Box', parent_id='root', sibling_index=0, width_dp=40, height_dp=20)
        child['modifiers'] = [{'name': 'offset', 'arguments': 'x = 12.dp, y = -4.dp'}]
        output, gate, renderer = render_nodes([root, child])
        changed, _, _ = render_nodes([root, child], perturb_reference_frames=True)
        self.assertEqual(output, changed)
        self.assertIn('.translate({ x: 12, y: -4 })', output)
        self.assertEqual(gate['verdict'], 'pass', gate['failures'])
        self.assertFalse(renderer.unresolved)


if __name__ == '__main__':
    unittest.main()
