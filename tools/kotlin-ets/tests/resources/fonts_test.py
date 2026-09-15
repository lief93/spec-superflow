import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("fonts", Path(__file__).resolve().parents[2] / "font-resources.py")
fonts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fonts)


class FontsTest(unittest.TestCase):
    def test_bytes_and_fresh_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "res"
            (source / "font").mkdir(parents=True)
            content = bytes(range(256))
            (source / "font" / "regular.ttf").write_bytes(content)
            manifest = fonts.materialize(source, "example", root / "output")
            symbol, relative = manifest.read_text().strip().split("=")
            self.assertEqual(symbol, "example.R.font.regular")
            self.assertEqual((manifest.parent / relative).read_bytes(), content)
            with self.assertRaises(FileExistsError):
                fonts.materialize(source, "example", root / "output")

    def test_duplicate_and_qualifier_do_not_guess(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "res"
            (source / "font").mkdir(parents=True)
            for extension in ("ttf", "otf"):
                (source / "font" / ("regular." + extension)).write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                fonts.materialize(source, "example", root / "output")
            (source / "font-night").mkdir()
            with self.assertRaisesRegex(ValueError, "Qualified"):
                fonts.materialize(source, "example", root / "output")
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
