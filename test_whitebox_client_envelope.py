import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from whitebox_bridge import BridgeApplication, MockBackend, make_server
from whitebox_client import WhiteboxClient

TOKEN = 'synthetic-test-token'


class WhiteboxClientEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(BridgeApplication(MockBackend(), TOKEN), '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = WhiteboxClient(f'http://127.0.0.1:{self.server.server_address[1]}', TOKEN, timeout=5.0)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_success_envelope_is_unwrapped_for_all_endpoints(self):
        health = self.client.health()
        self.assertEqual(health['mode'], 'mock')
        self.assertNotIn('result', health)
        info = self.client.model_info()
        self.assertEqual(info['model_id'], 'mock/no-model')
        self.assertEqual(info['hidden_size'], 8)
        scored = self.client.score_sequences('SYNTHETIC PROMPT', [' A', ' B'])
        self.assertEqual(len(scored['scores']), 2)
        cap = self.client.capture('SYNTHETIC PROMPT', layer=1, token_index=-1)
        self.assertEqual(len(cap['vector']), 8)
        patched = self.client.patch_score('SYNTHETIC PROMPT', [' A', ' B'], layer=1, vector=[0.0]*8, token_index=-1, mode='add', scale=0.0)
        self.assertEqual(len(patched['scores']), 2)

    def test_http_error_remains_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'bridge HTTP 404'):
            self.client.request('GET', '/not-an-endpoint')


class MissingResultHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        raw = json.dumps({'ok': True}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class WhiteboxClientMalformedSuccessTests(unittest.TestCase):
    def test_success_without_result_fails_closed(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), MissingResultHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = WhiteboxClient(f'http://127.0.0.1:{server.server_address[1]}', TOKEN, timeout=5.0)
            with self.assertRaisesRegex(RuntimeError, 'successful response missing result'):
                client.health()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
