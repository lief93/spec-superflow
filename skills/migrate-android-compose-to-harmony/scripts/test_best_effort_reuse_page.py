"""Exercise relaxed component reuse through every public generation stage."""
import json
from pathlib import Path
import unittest

import test_page_commands as commands


TARGETS = {
    'StatusLabel.ets': '''@Component
export struct StatusLabel {
  @Require @Prop label: string | Resource
  @Prop gap: Length = 0
  build() { Text(this.label).fontSize(this.gap) }
}
''',
    'Caption.ets': '''@Component
export struct Caption {
  @Prop title: string = 'Library default'
  @Require @Prop count: number
  @Require @Prop active: boolean
  @BuilderParam content: () => void
  build() {
    Column() {
      Text(this.title)
      Text(this.count.toString())
      this.content()
    }
  }
}
''',
    'Notice.ets': '''@Builder
export function Notice(prefix: string = 'Prefix', label: string, onAction: () => void) {
  Text(prefix + label).onClick(onAction)
}
''',
}


class BestEffortReusePageTest(unittest.TestCase):
    setUp = commands.PageCommandsTest.setUp
    run_tool = commands.PageCommandsTest.run_tool
    full_args = commands.PageCommandsTest.full_args

    def generate(self):
        (self.source/'Page.kt').write_text('''package example
@Composable fun Page() { Column {
    Caption("Source label", Modifier.fillMaxWidth())
    Notice("Visible label")
    StatusLabel("Live label", 12.dp)
} }
@Composable fun Caption(label: String, modifier: Modifier) { Text("Android internals") }
@Composable fun Notice(label: String) { Text(label) }
@Composable fun StatusLabel(label: String, gap: Dp) { Text(label) }
''')
        self.snapshot, self.contract = self.root/'reuse-snapshot', self.root/'reuse-contract.json'
        self.run_tool('prepare_safe_snapshot.py', '--source', self.source, '--snapshot', self.snapshot)
        self.run_tool('analyze_compose_project.py', '--snapshot', self.snapshot, '--output', self.contract)
        self.run_tool('generate_project_style_definitions.py', '--contract', self.contract, '--output', self.styles, '--refresh')
        target = self.root/'harmony'
        self.run_tool('init_harmony_project.py', '--output', target, '--contract', self.contract,
                      '--project-name', 'ReusePage', '--bundle-name', 'com.example.reusepage', '--sdk-version', '6.0.0(20)')
        component_dir = target/'entry/src/main/ets/components'
        component_dir.mkdir()
        for name, content in TARGETS.items():
            (component_dir/name).write_text(content)
        result = self.run_tool('migrate_compose_page.py', *self.full_args())
        return result, target

    def test_full_page_outputs_reuse_and_reports_degradation(self):
        result, target = self.generate()
        self.assertEqual(result['status'], 'partial_generation', result)
        self.assertFalse(result['generation_complete'])
        self.assertTrue(all(s['status'] == 'completed' for s in result['stages']))
        code = '\n'.join(p.read_text() for p in (target/'entry/src/main/ets/generated').rglob('*.ets'))
        self.assertIn('Caption(', code)
        self.assertIn('count: 0', code)
        self.assertIn('Notice(undefined, "", () => {})', code)
        self.assertNotIn('Android internals', code)
        self.assertIn('StatusLabel({ label: "" })', code)
        self.assertNotIn('label: props.label', code)
        self.assertNotIn('gap: props.gap', code)
        self.assertGreater(result['diagnosis']['counts']['defaulted'], 0)
        self.assertIn('component reuse parameter', Path(result['diagnosis_report']).read_text())
        manifest = json.loads(Path(result['arkui']['manifest']).read_text())
        self.assertEqual(len(manifest['reused_business_components']), 3)
        for name, content in TARGETS.items():
            self.assertEqual((target/'entry/src/main/ets/components'/name).read_text(), content)


if __name__ == '__main__':
    unittest.main()
