"""End-to-end check: start the server, upload real 24-Nov phyphox ZIPs and some bad ones.
Run: python -m unittest test_walksense.py   (about 30 s, trains the models once)"""
import io
import json
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import server
import walksense as ws


def raw_zip(session, phone, typ, node=None, to=None):
    for r in ws.manifest(session):
        where = r['node'] if typ == 'stop' else r['from_node']      # walks have from_node/to_node, no node
        if r['phone'] == phone and r['type'] == typ and (node is None or where == node) and (to is None or r['to_node'] == to):
            return (ws.DATA / session / 'raw' / r['source_zip']).read_bytes(), r
    raise LookupError((session, phone, typ, node, to))


class UploadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.STATE['models'] = ws.build_models()
        server.UPLOADS = server.HERE / 'out' / 'test_uploads'     # keep test uploads out of uploads/
        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.url = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, path, data=b''):
        req = urllib.request.Request(self.url + path, data=data, method='POST')
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_read_zip(self):
        data, row = raw_zip('sesi2', 'iphone', 'stop', 'canteen')
        rec = ws.read_zip(data)
        self.assertEqual(rec['device'], row['device'])
        self.assertTrue(len(rec['mag']) > 1000 and len(rec['baro']) > 10 and rec['start_epoch'] > 1.7e9)

    def test_route_stop_walk_stop_and_floor_change(self):
        self.post('/api/reset?floor=5')
        data, _ = raw_zip('sesi2', 'iphone', 'stop', 'canteen')
        code, body = self.post('/api/upload?kind=auto&truth=canteen', data)
        self.assertEqual(code, 200, body)
        r = body['result']
        self.assertEqual((r['kind'], r['floor'], r['device']), ('stop', 5, 'iPhone17,4'))
        self.assertEqual(len(r['top3']), 3)
        self.assertIn('trained on this phone model', r['model_note'])
        self.assertEqual(body['tally']['stops'], 1)
        data, _ = raw_zip('sesi2', 'iphone', 'walk', 'canteen', None)
        code, body = self.post('/api/upload?kind=auto', data)
        self.assertEqual((code, body['result']['kind']), (200, 'walk'))
        self.assertGreater(body['result']['steps'], 5)
        # 5F stairs landing, then the 4F landing: the floor must switch to 4
        for node, floor in (('lift_stairs5', 5), ('lift_stairs5', 4)):
            for r in ws.manifest('sesi2'):
                if r['phone'] == 'iphone' and r['type'] == 'stop' and r['node'] == node and int(r['floor']) == floor:
                    code, body = self.post('/api/upload?kind=stop', (ws.DATA / 'sesi2' / 'raw' / r['source_zip']).read_bytes())
                    self.assertEqual(code, 200, body)
        self.assertEqual(body['result']['floor'], 4, body['result']['floor_note'])

    def test_bad_uploads_refused(self):
        self.assertEqual(self.post('/api/upload', b'not a zip')[0], 400)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('Accelerometer.csv', '"t","x","y","z"\n0,0,0,9.8\n')
        self.assertEqual(self.post('/api/upload', buf.getvalue())[0], 400)          # no magnetometer
        self.assertEqual(self.post('/api/upload?truth=%3Cscript%3E', b'x')[0], 400)  # place name injection
        self.assertEqual(self.post('/api/upload?kind=drop', b'x')[0], 400)
        self.assertEqual(self.post('/api/floor?floor=9')[0], 400)
        self.assertEqual(self.post('/api/upload', b'')[0], 413)


if __name__ == '__main__':
    unittest.main()
