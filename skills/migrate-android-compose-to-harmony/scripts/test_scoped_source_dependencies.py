import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from analyze_compose_project import analyze
from real_page_pipeline import build_source_page_spec
from ui_migration.frontend.source_symbols import SourceSymbolIndex, function_identity


class ScopedSourceDependenciesTest(unittest.TestCase):
    def test_unrelated_bodies_are_not_dependency_analyzed(self):
        files = {'Page.kt': '@Composable fun Page() { Child() }\n@Composable fun Child() { Text("A") }',
                 'Unrelated.kt': '\n'.join(f'fun unused{i}() = remote{i}()' for i in range(300))}
        with patch.object(SourceSymbolIndex, 'referenced_properties', autospec=True, return_value=[]) as properties:
            index = SourceSymbolIndex(files, roots=[('Page.kt', 'Page')])
        self.assertEqual(len(index.functions), 302)
        self.assertEqual(len(index.edges), 2)
        self.assertEqual(properties.call_count, 2)
        self.assertFalse(any(f['source'] == 'Unrelated.kt' for f in index.functions if function_identity(f) in index.edges))

    def test_scoped_trace_matches_full_across_properties_extensions_slots_and_cycles(self):
        files = {
            'Page.kt': '''package app
import pieces.*
import tokens.width
@Composable fun Page() { LazyColumn { section(::Label) }; Box(Modifier.card(width)) {} }
@Composable fun Label() { Text("Label") }
''',
            'Parts.kt': '''package pieces
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.ui.Modifier
typealias Items = LazyListScope
fun Items.section(content: @Composable () -> Unit) { item { content() }; tail() }
fun Items.tail() { item { Text("End") } }
fun Modifier.card(width: Int) = this.width(width.dp)
fun unrelated() = other()
fun other() = unrelated()
''',
            'Tokens.kt': 'package tokens\nimport size.compute as read\nval width = read()\n',
            'Size.kt': 'package size\nfun compute() = 90\n',
        }
        full = SourceSymbolIndex(files)
        scoped = SourceSymbolIndex(files, roots=[('Page.kt', 'Page')])
        self.assertEqual(scoped.trace('Page.kt', 'Page'), full.trace('Page.kt', 'Page'))
        self.assertIn('compute', [n['name'] for n in scoped.trace('Page.kt', 'Page')['definitions']])
        self.assertLess(len(scoped.edges), len(full.edges))

    def test_default_parameter_dependency_and_property_initializer_are_followed(self):
        files = {'Page.kt': '''package app
import defaults.title
@Composable fun Page() { Label() }
@Composable fun Label(value: String = title()) { Text(value) }
''', 'Defaults.kt': 'package defaults\nimport tokens.value\nfun title() = value\n',
            'Tokens.kt': 'package tokens\nval value = compute()\nfun compute() = "Title"\n'}
        index = SourceSymbolIndex(files, roots=[('Page.kt', 'Page')])
        names = {f['name'] for f in index.trace('Page.kt', 'Page')['definitions']}
        self.assertTrue({'Page', 'Label', 'title', 'compute'}.issubset(names), names)

    def test_ambiguity_cycles_and_later_trace_are_not_truncated(self):
        files = {'Page.kt': 'package app\nimport a.*\nimport b.*\n'
            '@Composable fun Page() { Card() }\n@Composable fun Other() { Text("Later") }',
            'A.kt': 'package a\n@Composable fun Card() { again() }\nfun again() { Card() }',
            'B.kt': 'package b\n@Composable fun Card() { Text("B") }'}
        full = SourceSymbolIndex(files)
        scoped = SourceSymbolIndex(files, roots=[('Page.kt', 'Page')])
        self.assertEqual(scoped.trace('Page.kt', 'Page'), full.trace('Page.kt', 'Page'))
        count = len(scoped.edges)
        self.assertEqual(scoped.trace('Page.kt', 'Other'), full.trace('Page.kt', 'Other'))
        self.assertEqual(len(scoped.edges), count + 1)

    def test_page_inventory_matches_full_and_does_not_assume_test_directories_are_unused(self):
        files = {'Page.kt': 'package app\nimport pieces.Label\n@Composable fun Page() { Column { Label() } }',
                 'androidTest/Parts.kt': 'package pieces\n@Composable fun Label() { Text("Kept") }',
                 'Unused.kt': '@Composable fun Unused() { Column { Text("Not shown") } }'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            contract = analyze(root, {}, files)
            with patch.object(SourceSymbolIndex, 'from_root', wraps=SourceSymbolIndex.from_root) as factory:
                source = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a'*64, root)
            factory.assert_called_once_with(root, roots=[('Page.kt', 'Page')])
            original = SourceSymbolIndex.from_root.__func__
            with patch.object(SourceSymbolIndex, 'from_root', classmethod(
                    lambda cls, path, **kwargs: original(cls, path))):
                full = build_source_page_spec(contract, 'Page.kt', 'Page', 'page', 'default', 'a'*64, root)
        self.assertEqual(source, full)
        self.assertIn('Kept', [n['style']['content']['text'] for n in source['components']])


if __name__ == '__main__':
    unittest.main()
