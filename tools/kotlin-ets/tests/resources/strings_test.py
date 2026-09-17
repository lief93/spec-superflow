import importlib.util
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[2] / "string-resources.py"
spec = importlib.util.spec_from_file_location("strings", path)
strings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strings)


class StringsTest(unittest.TestCase):
    def test_native_formats_and_build_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "res"
            (source / "values").mkdir(parents=True)
            (source / "values" / "strings.xml").write_text(
                '<resources><string name="label">%1$s: %2$d</string>'
                '<string name="precision">%.2f</string></resources>')
            symbols = root / "R.txt"
            symbols.write_text('int string label 0x7f010001\nint string precision 0x7f010002\n')
            output = root / "output"
            result = strings.materialize(source, "example", output, symbols)
            self.assertEqual(result["defaultCount"], 1)
            self.assertEqual(result["unsupportedCount"], 1)
            self.assertIn('%1$s', (output / "base.properties").read_text())
            self.assertEqual((output / "source-resource-ids.properties").read_text(),
                             'example.R.string.label=2130771969\n')

    def test_plain_xml_entities_names_and_qualified_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "res"
            (source / "values").mkdir(parents=True)
            (source / "values-night").mkdir()
            (source / "values" / "strings.xml").write_text(
                '<resources><string name="Title">A &amp; B &#x4E2D;</string>'
                '<string name="variant">Day</string><string name="spaces">Two  spaces</string></resources>')
            (source / "values-night" / "strings.xml").write_text(
                '<resources><string name="variant">Night</string></resources>')
            output = root / "output"
            result = strings.materialize(source, "example.app", output)
            self.assertEqual(result["defaultCount"], 2)
            self.assertEqual(result["unsupportedCount"], 2)
            self.assertIn("example.app.R.string.Title=A & B \u4e2d", (output / "base.properties").read_text())
            self.assertIn("unsupported qualifier values-night", (output / "unsupported.properties").read_text())
            with self.assertRaises(FileExistsError):
                strings.materialize(source, "example.app", output)

    def test_duplicate_is_not_an_overlay_guess(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "res"
            (source / "values").mkdir(parents=True)
            for name in ("one", "two"):
                (source / "values" / (name + ".xml")).write_text(
                    '<resources><string name="title">Title</string></resources>')
            with self.assertRaisesRegex(ValueError, "Conflicting string resource"):
                strings.materialize(source, "example", root / "output")
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
