import unittest

from test_component_ui_states import compile_states


class OverlayTest(unittest.TestCase):
    def test_alert_dialog_preserves_slots_in_native_modal(self):
        _, renderer, code, result = compile_states('''
@Composable fun Page() { Box {
    Text("Behind", color = Color.Black)
    AlertDialog(onDismissRequest = {}, containerColor = Color.White,
        title = { Text("Title", color = Color.Black) },
        text = { Text("Body", color = Color.Black) },
        confirmButton = { TextButton(onClick = {}) { Text("OK") } },
        dismissButton = { TextButton(onClick = {}) { Text("Cancel") } })
} }
''')
        self.assertIn('.bindContentCover(', code)
        for text in ('Behind', 'Title', 'Body', 'OK', 'Cancel'):
            self.assertIn(text, code)
        self.assertIn('.fontSize(24)', code)
        self.assertIn('.fontSize(14)', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)
        self.assertEqual(renderer.test_phase_gate['verdict'], 'pass', renderer.test_phase_gate['failures'])

    def test_dialog_is_a_separate_root_not_an_extra_page_layout_root(self):
        _, renderer, code, result = compile_states('''
@Composable fun Page() {
    Column { Text("Page", color = Color.Black) }
    Dialog(onDismissRequest = {}, properties = DialogProperties(dismissOnClickOutside = false)) {
        Box(Modifier.size(120.dp).background(Color.Blue)) { Text("Dialog", color = Color.White) }
    }
}
''')
        self.assertIn('.bindContentCover(', code)
        self.assertIn('Dialog', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)

    def test_sheet_content_and_custom_handle_are_not_lost(self):
        _, renderer, code, result = compile_states('''
@Composable fun Page() { Box {
    ModalBottomSheet(onDismissRequest = {}, containerColor = Color.White,
        dragHandle = { Text("Handle", color = Color.Black) }) {
        Text("Sheet content", color = Color.Black)
    }
} }
''')
        self.assertIn('.bindSheet(', code)
        self.assertIn('Sheet content', code)
        self.assertIn('Handle', code)
        self.assertTrue(result['generation_complete'], result['unresolved'])
        self.assertFalse(renderer.unresolved, renderer.unresolved)


if __name__ == '__main__':
    unittest.main()
