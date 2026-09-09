import unittest
import random
from unittest.mock import patch

from kotlin_psi import parse_expression
from ui_migration.frontend import source_symbols as symbols
from ui_migration.frontend.declaration_lookup import DeclarationLookup
from ui_migration.semantics.syntax import call_from


class SourceSymbolPerformanceTest(unittest.TestCase):
    def test_dependency_lookup_does_not_scan_unrelated_declarations(self):
        files = {'Page.kt': 'package app\nimport tokens.chosen\n'
                 '@Composable fun Page() { Text(chosen().toString()) }',
                 'Tokens.kt': 'package tokens\nfun chosen() = 12\n' + '\n'.join(
                     f'fun unused{i}() = {i}' for i in range(200))}
        with patch.object(symbols, 'function_fq_name', wraps=symbols.function_fq_name) as names:
            index = symbols.SourceSymbolIndex(files)
        self.assertIn('chosen', [d['name'] for d in index.trace('Page.kt', 'Page')['definitions']])
        self.assertLess(names.call_count, 600, 'lookup repeatedly walked unrelated symbols')
        class NoFullScan(list):
            def __iter__(self):
                raise AssertionError('query scanned the full function inventory')
        index.functions = NoFullScan(index.functions)
        self.assertEqual(index.resolve(call_from(parse_expression('notInSource()')), index.by_source['Page.kt'][0]), [])

    def test_global_values_reuse_file_owner_scope_without_leaking_between_owners(self):
        index = symbols.SourceSymbolIndex({'Page.kt': 'package app\nval shared = 12\n'
            'object A { val value = 1; fun one() = value; fun two() = value }\n'
            'object B { val value = 2; fun one() = value }'})
        a = [f for f in index.functions if f.get('owner') == 'A']
        b = next(f for f in index.functions if f.get('owner') == 'B')
        with patch.object(index, 'visible_properties', wraps=index.visible_properties) as lookup:
            first = index.global_values(a[0])
            calls = lookup.call_count
            self.assertEqual(index.global_values(a[1]), first)
            self.assertEqual(lookup.call_count, calls, 'same file/owner rebuilt all global values')
        self.assertEqual(first['value'], '1')
        self.assertEqual(index.global_values(b)['value'], '2')

    def test_repeated_property_lookup_reuses_negative_and_positive_results(self):
        index = symbols.SourceSymbolIndex({'Page.kt': 'val shared = 12\nfun Page() = 0'})
        function = index.functions[0]
        with patch.object(symbols, 'resolve_functions', wraps=symbols.resolve_functions) as resolve:
            for name in ('shared', 'missing'):
                expected = index.visible_properties(function, name)
                count = resolve.call_count
                self.assertEqual(index.visible_properties(function, name), expected)
                self.assertEqual(resolve.call_count, count)

    def test_new_index_does_not_reuse_previous_source_values(self):
        files = {'Page.kt': 'val shared = 12\nfun Page() = shared'}
        old = symbols.SourceSymbolIndex(files)
        files['Page.kt'] = 'val shared = 24\nfun Page() = shared'
        new = symbols.SourceSymbolIndex(files)
        self.assertEqual(old.global_values(old.functions[0])['shared'], '12')
        self.assertEqual(new.global_values(new.functions[0])['shared'], '24')

    def test_returned_scope_collections_cannot_corrupt_cached_results(self):
        index = symbols.SourceSymbolIndex({'Page.kt': 'val shared = 12\nfun Page() = shared'})
        function = index.functions[0]
        index.visible_properties(function, 'shared').clear()
        index.global_values(function).clear()
        self.assertEqual(len(index.visible_properties(function, 'shared')), 1)
        self.assertEqual(index.global_values(function), {'shared': '12'})

    def test_candidate_narrowing_preserves_all_lexical_rules(self):
        declarations = [dict(source=f'{package}{file}.kt', package=package, owner=owner, name=name)
                        for package in ('a', 'b') for file in range(2)
                        for owner in (None, 'Owner') for name in ('size', 'color')]
        random.Random(7).shuffle(declarations)
        lookup = DeclarationLookup(declarations, symbols.function_fq_name)
        for source in ('a0.kt', 'b1.kt', 'missing.kt'):
            for owner in (None, 'Owner'):
                for imports in ({}, {'alias': 'a.size'}, {'size': 'b.color'}, {'Lib': 'b.Owner'}):
                    for name in ('size', 'color', 'alias', 'a.size', 'Owner.size', 'Lib.color', 'missing'):
                        for wildcards in ((), ('a', 'b')):
                            scope = dict(source=source, owner=owner, imports=imports, package='a', wildcards=wildcards)
                            with self.subTest(name=name, scope=scope):
                                self.assertEqual(symbols.resolve_functions(lookup, name, **scope),
                                                 symbols.resolve_functions(declarations, name, **scope))

    def test_indexed_resolution_matches_linear_reference_including_candidate_order(self):
        index = symbols.SourceSymbolIndex({
            'Page.kt': 'package app\nimport tokens.size as named\nimport a.*\nimport b.*\n'
                       'fun Page() = 0\nfun local() = 1\n'
                       'object Owner { fun local() = 2; fun Page() = 0 }',
            'Tokens.kt': 'package tokens\nfun size() = 12\nfun size(value: Int) = value',
            'A.kt': 'package a\nfun Card() = 1\nfun String.custom() = 1',
            'B.kt': 'package b\nfun Card() = 2',
            'Other.kt': 'package app\nfun samePackage() = 1',
        })
        for function in index.functions:
            syntax = index.syntax[function['source']]
            scope = dict(source=function['source'], imports=syntax['imports'], package=syntax['package'],
                         wildcards=syntax['wildcardImports'], owner=function.get('owner'))
            for expression in ('local()', 'named()', 'named(3)', 'tokens.size()', 'Card()',
                               'samePackage()', 'absent()', '"a".custom()', '::named'):
                with self.subTest(function=symbols.function_identity(function), expression=expression):
                    call = call_from(parse_expression(expression))
                    if call is None:
                        call = next(symbols.expression_calls(parse_expression(expression)))
                    expected = symbols.resolve_functions(index.functions, call.qualified_name if call.receiver else call.name, **scope)
                    if call.receiver and not expected:
                        expected = [f for f in symbols.resolve_functions(index.functions, call.name, **scope) if f.get('receiver')]
                    expected = [f for f in expected if call.reference or symbols.matches_argument_shape(f, call)]
                    self.assertEqual(index.resolve(call, function), expected)


if __name__ == '__main__':
    unittest.main()
