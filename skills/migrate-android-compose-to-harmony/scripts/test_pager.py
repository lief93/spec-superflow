import unittest
from copy import deepcopy

from test_component_ui_states import compile_states
from ui_migration.frontend.values import evaluate_expression
from ui_migration.contracts.pager import validate_pager


SOURCE = '''
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
@Composable fun Page() {
    val labels = listOf("First", "Second", "Third")
    val pager = rememberPagerState(initialPage = 1) { labels.size }
    HorizontalPager(state = pager, modifier = Modifier.fillMaxWidth().height(180.dp),
                    pageSpacing = 8.dp, contentPadding = PaddingValues(horizontal = 16.dp)) { page ->
        Column(Modifier.fillMaxSize().background(Color.Blue)) {
            Text(labels[page], color = Color.White)
        }
    }
}
'''


class PagerTest(unittest.TestCase):
    def test_tampered_pager_facts_fail_before_code_emission(self):
        facts = dict(page_count=1, initial_page=0, axis='horizontal', alignment='Start',
                     user_scroll_enabled=True, page_spacing_dp=0, content_padding_dp=None, pages=[['item']])
        validate_pager(facts, ['item'])
        for field, value in [('initial_page', '0)'), ('page_count', True), ('axis', 'diagonal'),
                             ('alignment', 'Start)'), ('page_spacing_dp', -1), ('pages', [['missing']])]:
            with self.subTest(field=field):
                changed = deepcopy(facts)
                changed[field] = value
                with self.assertRaises(ValueError):
                    validate_pager(changed, ['item'])
    def test_pager_state_uses_structured_evaluation(self):
        value = evaluate_expression('rememberPagerState(initialPage = 1, pageCount = { 3 })', {})
        self.assertEqual(value['pageCount'], 3)
        self.assertEqual(value['currentPage'], 1)

    def test_all_pages_are_expanded_and_consumed_from_single_json(self):
        _, renderer, code, result = compile_states(SOURCE)
        self.assertIn('Swiper()', code)
        for label in ('First', 'Second', 'Third'):
            self.assertIn(label, code)
        for modifier in ('.index(1)', '.loop(false)', '.autoPlay(false)', '.indicator(false)', '.itemSpace('):
            self.assertIn(modifier, code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate)

    def test_vertical_and_disabled_pager(self):
        source = SOURCE.replace('HorizontalPager', 'VerticalPager').replace(
            'pageSpacing = 8.dp', 'userScrollEnabled = false, horizontalAlignment = Alignment.End, pageSpacing = 8.dp')
        _, renderer, code, result = compile_states(source)
        self.assertIn('.vertical(true)', code)
        self.assertIn('.disableSwipe(true)', code)
        self.assertIn('.alignContent(Alignment.TopEnd)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_sibling_content_stays_in_one_page(self):
        source = SOURCE.replace('Column(Modifier.fillMaxSize().background(Color.Blue)) {', '')
        source = source.replace('Text(labels[page], color = Color.White)\n        }',
            'Text(labels[page], color = Color.White)\nText("Detail", color = Color.Black)')
        _, renderer, _, result = compile_states(source)
        pager = next(n['source']['pager'] for n in renderer.android_page_by_id.values() if n['type'] == 'HorizontalPager')
        self.assertEqual([len(roots) for roots in pager['pages']], [2, 2, 2])
        self.assertTrue(result['generation_complete'], result['unresolved'])

    def test_unknown_count_keeps_template_and_reports_incomplete(self):
        _, renderer, code, result = compile_states(SOURCE.replace('labels.size', 'unknownCount'))
        self.assertFalse(result['generation_complete'])
        self.assertTrue(any('pager' in str(u) for u in result['unresolved']))
        self.assertTrue(renderer.unresolved)
        self.assertNotIn('Swiper()', code)

    def test_unsupported_pager_modes_are_not_silently_accepted(self):
        for argument in ('pageSize = PageSize.Fixed(90.dp)', 'reverseLayout = true',
                         'flingBehavior = customFling', 'snapPosition = SnapPosition.Center'):
            with self.subTest(argument=argument):
                _, renderer, code, result = compile_states(SOURCE.replace('pageSpacing = 8.dp', argument + ', pageSpacing = 8.dp'))
                self.assertFalse(result['generation_complete'])
                self.assertIn('Swiper()', code)
                self.assertTrue(renderer.unresolved)

    def test_value_wrappers_and_named_count_lambda(self):
        source = SOURCE.replace('val pager = rememberPagerState(initialPage = 1) { labels.size }',
            'val count = labels.size\nval pager = rememberPagerState(pageCount = { count }, initialPage = 1)')
        _, renderer, code, result = compile_states(source)
        self.assertIn('Third', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_positional_state_argument(self):
        _, renderer, code, result = compile_states(SOURCE.replace('state = pager,', 'pager,'))
        self.assertIn('Third', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_empty_and_invalid_page_counts(self):
        _, renderer, _, result = compile_states(SOURCE.replace('initialPage = 1', 'initialPage = 0').replace('labels.size', '0'))
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        for count in ('-1', '201'):
            _, _, _, result = compile_states(SOURCE.replace('labels.size', count))
            self.assertFalse(result['generation_complete'])


if __name__ == '__main__':
    unittest.main()
