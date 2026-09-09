"""Public boundary checks for the single-document UI compiler."""
import ast
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class UiMigrationArchitectureTest(unittest.TestCase):
    def test_package_dependencies_are_acyclic_and_do_not_import_entrypoints(self):
        root = Path(__file__).parent / 'ui_migration'
        graph = {}
        entrypoints = {'generate_arkui_page', 'generate_lanhu_source_page',
                      'generate_ui_state_previews', 'real_page_pipeline', 'layout_expressions'}
        for path in root.rglob('*.py'):
            module = 'ui_migration.' + path.relative_to(root).with_suffix('').as_posix().replace('/', '.')
            tree = ast.parse(path.read_text())
            imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            imports.update(a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names)
            self.assertFalse(imports & entrypoints, (module, imports & entrypoints))
            edges = {name for name in imports if name and name.startswith('ui_migration.')}
            graph[module] = edges
            if module.startswith('ui_migration.contracts.'):
                self.assertFalse(any(name.startswith(('ui_migration.arkui.', 'ui_migration.frontend.',
                                                     'ui_migration.runtime.')) for name in edges), module)
            if module.startswith('ui_migration.arkui.'):
                self.assertFalse(any(name.startswith(('ui_migration.frontend.', 'ui_migration.runtime.',
                                                     'ui_migration.semantics.')) for name in edges), module)
            if module.startswith('ui_migration.semantics.'):
                self.assertFalse(any(not name.startswith('ui_migration.semantics.') for name in edges), module)

        def visit(module, stack):
            self.assertNotIn(module, stack, stack + [module])
            for dependency in graph.get(module, ()):
                visit(dependency, stack + [module])

        for module in graph:
            visit(module, [])

    def test_layout_and_drawing_share_exactly_one_length_helper_requirement(self):
        from ui_migration.arkui.formatting import LayoutLengths
        from ui_migration.arkui.layout import LayoutContext, LayoutPolicy
        lengths = LayoutLengths()
        policy = LayoutPolicy(LayoutContext({}, 'source-tree', {}, {}, {},
                                           lambda *_: None, lambda *_: None, lambda *_: None, lengths))
        self.assertFalse(lengths.used)
        self.assertEqual(policy.page_layout_length(12), lengths.length(12))
        self.assertTrue(lengths.used)
        self.assertEqual(lengths.edges(dict(left=12, right=12, top=12, bottom=12)), 'this.layoutPx(12)')

    def test_unknown_image_remains_a_leaf_and_preserves_surface_owner(self):
        from ui_migration.arkui.leaves import NativeLeafEmitter
        from ui_migration.arkui.surface import SurfaceEmitter
        from page_snapshot import empty_style
        errors = []
        component = {'id': 'avatar', 'type': 'AsyncImage', 'style': empty_style()}
        component['style']['surface']['background'] = {'type': 'solid', 'color': '#FFBCC3FF'}
        result = NativeLeafEmitter(set(), {}, None, lambda *args: errors.append(args)).emit(component, '')
        surface, fields, _ = SurfaceEmitter(lambda *args: errors.append(args)).emit(component, '')
        self.assertEqual(result.lines, ['Stack() {}'])
        self.assertFalse(result.image_drawn)
        self.assertNotIn('style.asset.resource', result.consumed)
        self.assertIn("  .backgroundColor('#FFBCC3FF')", surface)
        self.assertIn('style.surface.background', fields)
        self.assertEqual(errors[0][1], 'style.asset.resource')

    def test_all_native_leaf_handlers_share_the_result_contract(self):
        from ui_migration.arkui.leaves import LeafResult, NativeLeafEmitter
        from page_renderer_test_support import empty_renderer
        from page_snapshot import empty_style
        renderer = empty_renderer()
        emitter = renderer.leaves
        self.assertIsInstance(emitter, NativeLeafEmitter)
        for kind in emitter.handlers:
            with self.subTest(kind=kind):
                style = empty_style()
                style['content']['text'] = '25%' if kind == 'ProgressRing' else 'Example'
                style['state'].update(checked=True, selected=True)
                style.setdefault('control', {}).update(value=0.25, minimum=0, maximum=1, steps=3)
                component = {'id': kind, 'type': kind, 'style': style}
                self.assertIsInstance(emitter.emit(component, ''), LeafResult)

    def test_support_report_links_resolve_to_actual_implementation_owners(self):
        from audit_page_support import build_report
        report, _ = build_report()
        self.assertIn('ui_migration/arkui/surface.py', report)
        self.assertIn('ui_migration/arkui/typography.py', report)
        self.assertIn('ui_migration/frontend/styles.py', report)

    def test_backend_can_load_without_source_or_cli_modules(self):
        program = '''
import sys
from ui_migration.contracts.lanhu import load_lanhu_page_input
from ui_migration.arkui.renderer import Renderer
assert 'generate_arkui_page' not in sys.modules
assert 'real_page_pipeline' not in sys.modules
assert 'analyze_compose_project' not in sys.modules
assert 'kotlin_psi' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-B', '-c', program],
                                cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_semantics_can_evaluate_without_project_or_target_modules(self):
        program = '''
import sys
from ui_migration.semantics.expressions import LayoutExpressions
unknown = object()
resolver = LayoutExpressions({}, {'ready': True}, lambda *_: unknown, unknown)
assert resolver.value({'kind': 'name', 'name': 'ready'}) is True
assert 'real_page_pipeline' not in sys.modules
assert 'generate_arkui_page' not in sys.modules
assert 'analyze_compose_project' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-B', '-c', program],
                                cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_reexports_one_contract_and_renderer_implementation(self):
        import generate_arkui_page as cli
        contract = importlib.import_module('ui_migration.contracts.lanhu')
        backend = importlib.import_module('ui_migration.arkui.renderer')
        self.assertIs(cli.load_lanhu_page_input, contract.load_lanhu_page_input)
        self.assertIs(cli.Renderer, backend.Renderer)

    def test_repeated_render_is_deterministic_and_does_not_mutate_contract(self):
        from generate_arkui_page import Renderer, derive_page_root, load_lanhu_page_input
        from test_generate_arkui_lanhu_input import GenerateArkUILanhuInputTest
        with tempfile.TemporaryDirectory() as folder:
            version, _ = GenerateArkUILanhuInputTest().write_inputs(Path(folder))
            page = load_lanhu_page_input(version)
            before = json.dumps(page, sort_keys=True)
            first = Renderer(derive_page_root(page), {'media:ic_cover_ellipse'}, {}, page)
            second = Renderer(derive_page_root(page), {'media:ic_cover_ellipse'}, {}, page)
            self.assertEqual(first.render(), second.render())
            self.assertEqual(first.unresolved, second.unresolved)
            self.assertEqual(json.dumps(page, sort_keys=True), before)


if __name__ == '__main__':
    unittest.main()
