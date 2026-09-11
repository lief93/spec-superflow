import unittest

from page_snapshot import normalize_provenance, PageSnapshotError


class SourceProvenanceTest(unittest.TestCase):
    def test_multiline_source_evidence_is_preserved(self):
        for source in ('Material3 baseline: ButtonDefaults.buttonColors(\n\tcontainerColor = theme.primary\n)',
                       'source expression: ' + 'x' * 1000):
            entry = {'paths': ['style.surface.background'], 'origin': 'source_resolved', 'source': source}
            self.assertEqual(normalize_provenance([entry], 'provenance'), [entry])

    def test_invalid_provenance_still_fails(self):
        for source in (None, '', ' \n\t', 16, 'bad\x00value', 'bad\x1bvalue',
                       'bad\x7fvalue', 'bad\u0085value', 'x' * 10001):
            with self.subTest(source=repr(source)[:40]), self.assertRaises(PageSnapshotError):
                normalize_provenance([{'paths': ['style.surface.background'],
                    'origin': 'source_resolved', 'source': source}], 'provenance')
