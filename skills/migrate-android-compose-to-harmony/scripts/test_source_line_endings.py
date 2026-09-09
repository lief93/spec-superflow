import hashlib
import tempfile
import unittest
from pathlib import Path

from analyze_compose_project import load_text_files, collect_composable_associations


class SourceLineEndingsTest(unittest.TestCase):
    def test_audited_crlf_source_has_the_same_ui_inventory_as_lf(self):
        source = '@Composable\nfun Page(\n    title: String,\n) {\n    Text(title)\n}\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            content = source.replace('\n', '\r\n').encode()
            (root/'Page.kt').write_bytes(content)
            (root/'.android-to-harmony-safe.json').write_text('{}')
            manifest = {'text_files': ['Page.kt'],
                        'text_file_sha256': {'Page.kt': hashlib.sha256(content).hexdigest()}}
            files = load_text_files(root, manifest)
            self.assertEqual(files['Page.kt'], source)
            self.assertEqual(collect_composable_associations(files),
                             collect_composable_associations({'Page.kt': source}))
            self.assertEqual((root/'Page.kt').read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
