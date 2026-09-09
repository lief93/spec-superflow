import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from ui_migration.verification.long_page import evaluate


class LongPageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = {'schema': 'long-page-check.v1', 'page_id': 'feed', 'state_id': 'loaded',
                       'components': [{'id': 'card', 'selectors': {'android': {'id': 'card'}, 'harmony': {'id': 'card'}}}],
                       'streams': [{'id': 'main', 'end_component': 'card'}], 'gaps': []}
        self.records = []
        for platform in ('android', 'harmony'):
            folder = self.root / platform
            folder.mkdir()
            image = Image.new('RGB', (100, 200), 'white')
            ImageDraw.Draw(image).rectangle((10, 20, 89, 99), fill='red')
            image.save(folder / '0.png')
            (folder / '0.json').write_text(json.dumps({'attributes': {}, 'children': [
                {'attributes': {'id': 'card', 'bounds': '[10,20][90,100]', 'origBounds': '[10,20][90,100]'}, 'children': []}]}))
            frame = {'id': '0', 'stream': 'main', 'screenshot': '0.png', 'tree': '0.json'}
            for key in ('screenshot', 'tree'):
                frame[key + '_sha256'] = hashlib.sha256((folder / frame[key]).read_bytes()).hexdigest()
            record = {'schema': 'long-page-recording.v1', 'platform': platform,
                      'page_id': 'feed', 'state_id': 'loaded',
                      'device': {'serial': platform, 'size_px': [100, 200], 'density': 1,
                                 'font_scale': 1, 'content_bounds': [0, 0, 100, 200], 'theme': 'light'},
                      'artifact_sha256': 'a' * 64, 'frames': [frame, {**frame, 'id': '1', 'after_scroll': True}]}
            path = folder / 'recording.json'
            path.write_text(json.dumps(record))
            self.records.append(path)

    def run_check(self):
        return evaluate(self.config, *self.records, self.root / 'result')

    def mutate(self, change):
        path = self.records[1]
        record = json.loads(path.read_text())
        change(record)
        path.write_text(json.dumps(record))

    def test_equal_complete_components_pass(self):
        self.assertEqual(self.run_check()['verdict'], 'pass')

    def test_missing_component_fails_by_name(self):
        self.config['components'].append({'id': 'PrimaryButton', 'selectors': {'android': {'id': 'missing'}, 'harmony': {'id': 'missing'}}})
        report = self.run_check()
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['components'][1]['id'], 'PrimaryButton')
        self.assertIn('missing', str(report['components'][1]))

    def test_state_mismatch_rejected(self):
        self.mutate(lambda r: r.update(state_id='error'))
        with self.assertRaisesRegex(ValueError, 'state'):
            self.run_check()

    def test_font_scale_mismatch_rejected(self):
        self.mutate(lambda r: r['device'].update(font_scale=1.3))
        with self.assertRaisesRegex(ValueError, 'font'):
            self.run_check()

    def test_logical_viewport_mismatch_rejected(self):
        self.mutate(lambda r: r['device'].update(density=2))
        with self.assertRaisesRegex(ValueError, 'viewport'):
            self.run_check()

    def test_hash_drift_rejected(self):
        self.mutate(lambda r: r['frames'][0].update(tree_sha256='b'*64))
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.run_check()

    def test_single_frame_cannot_prove_end(self):
        self.mutate(lambda r: r.update(frames=r['frames'][:1]))
        self.assertEqual(self.run_check()['verdict'], 'fail')

    def test_undeclared_nested_stream_cannot_count_as_covered(self):
        self.config['streams'].append({'id': 'horizontal', 'end_component': 'card'})
        self.assertEqual(self.run_check()['verdict'], 'fail')

    def test_missing_gap_is_failure(self):
        self.config['gaps'] = [{'id': 'gap', 'before': 'card', 'after': 'absent', 'axis': 'y'}]
        self.assertEqual(self.run_check()['verdict'], 'fail')

    def test_ambiguous_selector_does_not_choose_first(self):
        tree = self.records[1].parent / '0.json'
        data = json.loads(tree.read_text())
        data['children'].append(copy.deepcopy(data['children'][0]))
        tree.write_text(json.dumps(data))
        digest = hashlib.sha256(tree.read_bytes()).hexdigest()
        self.mutate(lambda r: [f.update(tree_sha256=digest) for f in r['frames']])
        self.assertEqual(self.run_check()['verdict'], 'fail')

    def test_recording_path_escape_rejected(self):
        self.mutate(lambda r: r['frames'][0].update(tree='../other.json'))
        with self.assertRaisesRegex(ValueError, 'path'):
            self.run_check()

    def rewrite_tree(self, data):
        path = self.records[1].parent / '0.json'
        path.write_text(json.dumps(data))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.mutate(lambda r: [f.update(tree_sha256=digest) for f in r['frames']])

    def test_size_delta_fails_even_if_background_pixels_match(self):
        self.rewrite_tree({'attributes': {}, 'children': [{'attributes': {
            'id': 'card', 'bounds': '[10,20][90,103]', 'origBounds': '[10,20][90,103]'}, 'children': []}]})
        self.assertEqual(self.run_check()['verdict'], 'fail')

    def test_clipped_accessibility_bounds_are_not_complete(self):
        self.rewrite_tree({'attributes': {}, 'children': [{'attributes': {
            'id': 'card', 'bounds': '[10,0][90,200]'}, 'children': []}]})
        report = self.run_check()
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['components'][0]['platforms']['harmony']['status'], 'missing')

    def test_pixels_fail_when_geometry_matches(self):
        path = self.records[1].parent / '0.png'
        Image.new('RGB',(100,200),'blue').save(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.mutate(lambda r: [f.update(screenshot_sha256=digest) for f in r['frames']])
        self.assertEqual(self.run_check()['verdict'], 'fail')

    def test_two_density_recordings_use_logical_dimensions(self):
        folder = self.records[1].parent
        with Image.open(folder/'0.png') as image:
            image.resize((200,400),Image.Resampling.NEAREST).save(folder/'0.png')
        self.rewrite_tree({'attributes': {}, 'children': [{'attributes': {
            'id': 'card', 'bounds': '[20,40][180,200]', 'origBounds': '[20,40][180,200]'}, 'children': []}]})
        digest = hashlib.sha256((folder/'0.png').read_bytes()).hexdigest()
        self.mutate(lambda r: (r['device'].update(size_px=[200,400],density=2,content_bounds=[0,0,200,400]),
                               [f.update(screenshot_sha256=digest) for f in r['frames']]))
        self.assertEqual(self.run_check()['verdict'], 'pass')

    def tall_recordings(self, omit_top=False, conflict=False):
        for path in self.records:
            record = json.loads(path.read_text())
            record['frames'] = []
            for index, offset in enumerate((0,100,100)):
                image = Image.new('RGB',(100,200),'red' if not conflict or index == 0 else 'blue')
                image_path = path.parent/f'tall-{index}.png'
                tree_path = path.parent/f'tall-{index}.json'
                image.save(image_path)
                tree_path.write_text(json.dumps({'attributes':{},'children':[{'attributes':{
                    'id':'card','bounds':f'[10,0][90,200]','origBounds':f'[10,{-offset}][90,{300-offset}]'},'children':[]}]}))
                if omit_top and index == 0:
                    continue
                record['frames'].append({'id':str(index),'stream':'main','after_scroll':index>0,
                    'tree':tree_path.name,'tree_sha256':hashlib.sha256(tree_path.read_bytes()).hexdigest(),
                    'screenshot':image_path.name,'screenshot_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest()})
            path.write_text(json.dumps(record))

    def test_oversized_component_stitches_with_full_pixel_coverage(self):
        self.tall_recordings()
        report = self.run_check()
        self.assertEqual(report['verdict'],'pass')
        self.assertEqual(report['components'][0]['platforms']['android']['size_dp'],[80,300])

    def test_oversized_component_missing_strip_fails(self):
        self.tall_recordings(omit_top=True)
        report = self.run_check()
        self.assertEqual(report['verdict'],'fail')
        self.assertLess(report['components'][0]['platforms']['android']['pixel_coverage'],1)

    def test_stitch_overlap_content_change_is_not_accepted(self):
        self.tall_recordings(conflict=True)
        report = self.run_check()
        self.assertEqual(report['verdict'],'fail')
        self.assertEqual(report['components'][0]['platforms']['android']['status'],'unstable_pixels_across_scroll')

    def test_duplicate_frame_is_not_end_without_scroll_action(self):
        self.mutate(lambda r: r['frames'][-1].pop('after_scroll'))
        self.assertEqual(self.run_check()['verdict'],'fail')


if __name__ == '__main__':
    unittest.main()
