"""Exercise the downloadable demo with only standard-library test dependencies."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.base = f'http://127.0.0.1:{port}'
        cls.process = subprocess.Popen(
            [sys.executable, str(root / 'valen-repro/case-viewer/server.py'), '--demo', '--port', str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                cls.get('/api/summary')
                return
            except URLError:
                if cls.process.poll() is not None:
                    raise RuntimeError('Demo server exited during startup')
                time.sleep(.1)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        raise RuntimeError('Demo server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)

    @classmethod
    def get(cls, path):
        with urlopen(cls.base + path, timeout=5) as response:
            return json.load(response)

    def test_summary_is_explicitly_synthetic(self):
        summary = self.get('/api/summary')
        self.assertTrue(summary['demo'])
        self.assertEqual(summary['benchmark']['questions'], 4)
        self.assertEqual(summary['model']['phase'], 'demo')
        self.assertIsNone(summary['model']['gpu'])

    def test_text_examples_cover_choice_noul_score_without_missing_media(self):
        examples = self.get('/api/examples')['examples']
        self.assertEqual(len(examples), 4)
        self.assertEqual(len({item['id'] for item in examples}), len(examples))
        self.assertEqual({item['question_type'] for item in examples}, {'choice', 'noul', 'score'})
        for item in examples:
            self.assertEqual(item['modality'], 'text')
            self.assertTrue(item['instructions'])
            self.assertNotIn('media_url', item)

    def test_filter_search_pagination_and_details(self):
        wrong = self.get('/api/cases?result=wrong')
        self.assertEqual(wrong['total'], 1)
        case = self.get('/api/cases/' + wrong['items'][0]['id'])
        self.assertEqual(case['source'], 'Synthetic UI examples')
        self.assertFalse(case['correct'])
        self.assertEqual(self.get('/api/cases?task=noul')['total'], 1)
        self.assertEqual(self.get('/api/cases?result=unscored')['total'], 1)
        self.assertEqual(self.get('/api/cases?search=circle')['total'], 1)
        self.assertEqual(len(self.get('/api/cases?offset=1&limit=1')['items']), 1)

    def test_original_media_and_static_assets(self):
        for path in ('/', '/app.js', '/styles.css', '/api/media/assets/shapes.svg'):
            with urlopen(self.base + path, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())

    def test_saved_latency_is_real_hardware_report_not_demo_predictions(self):
        report = self.get('/api/latency')
        self.assertTrue(report['available'])
        self.assertFalse(report['matches_current_profile'])
        self.assertEqual(report['report']['status'], 'complete')
        self.assertEqual(set(report['report']['modalities']), {'text', 'image', 'video'})
        for entry in report['report']['modalities'].values():
            samples = [sample['inference_seconds'] for sample in entry['samples']]
            self.assertEqual(len(samples), entry['sample_count'])
            self.assertAlmostEqual(sum(samples) / len(samples), entry['mean_seconds'])
            self.assertEqual(min(samples), entry['min_seconds'])
            self.assertEqual(max(samples), entry['max_seconds'])

    def test_inference_is_unavailable_and_paths_are_confined(self):
        for path, data in (('/api/infer', b'instructions=hello'), ('/api/model/unload', b'')):
            request = Request(self.base + path, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with self.assertRaises(HTTPError) as result:
                urlopen(request, timeout=5)
            self.assertEqual(result.exception.code, 409)
        for path in ('/api/cases/missing', '/api/media/%2e%2e/server.py'):
            with self.assertRaises(HTTPError) as result:
                self.get(path)
            self.assertEqual(result.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
