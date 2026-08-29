import struct, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
from cpds_alfworld_static_source_transport_v1 import parse_eocd_last22, parse_central_directory, derive_train_spans, _range_get_exact, fetch_train_spans

class T(unittest.TestCase):
    def test_eocd_exact_geometry(self):
        b=struct.pack('<4s4H2LH',b'PK\x05\x06',0,0,2,2,100,878,0)
        x=parse_eocd_last22(b,1000); self.assertEqual(x['central_directory_offset'],878)
    def test_eocd_comment_fails(self):
        b=struct.pack('<4s4H2LH',b'PK\x05\x06',0,0,1,1,10,967,1)
        with self.assertRaises(ValueError): parse_eocd_last22(b,1000)
    def test_derive_train_span_disjoint(self):
        es=[{'name':'json_2.1.1/train/a/x','header_offset':0,'record_end_exclusive':10,'authorized_train':True},{'name':'json_2.1.1/train/b/x','header_offset':10,'record_end_exclusive':20,'authorized_train':True},{'name':'json_2.1.1/valid_seen/c/x','header_offset':20,'record_end_exclusive':30,'authorized_train':False}]
        self.assertEqual(derive_train_spans(es,30),[[0,20,2]])
    def test_range_guard_fails_before_network(self):
        with self.assertRaisesRegex(ValueError,'RANGE_OUTSIDE_AUTHORIZED_INTERVAL'):
            _range_get_exact('https://example.invalid',0,99,100,[(10,20)])
    def test_fetch_train_spans_emits_sequential_chunk_index(self):
        layout=[{'asset':{'id':112282473,'name':'alfworld_json_2.1.1.zip','size':10,'etag':'etag','train_spans':[[0,10,1]]},'entries':[]}]
        head={'size':10,'etag':'etag','accept_ranges':'bytes','final_url':'https://example.invalid'}
        def fake_range(_url,start,end,_total,_allowed):
            return bytes(range(start,end+1))
        with tempfile.TemporaryDirectory() as td, patch('cpds_alfworld_static_source_transport_v1._head',return_value=head), patch('cpds_alfworld_static_source_transport_v1._range_get_exact',side_effect=fake_range):
            access=fetch_train_spans(layout,Path(td),chunk_bytes=4)
        self.assertEqual([c['chunk_index'] for c in access[0]['chunks']],[0,1,2])
        self.assertEqual(access[0]['chunk_count'],3)
        self.assertEqual([(c['range_start'],c['range_end_inclusive']) for c in access[0]['chunks']],[(0,3),(4,7),(8,9)])

    def test_asset_constants_are_exact(self):
        from cpds_alfworld_static_source_transport_v1 import ASSETS
        self.assertEqual([(x['tag'],x['asset_id'],x['size']) for x in ASSETS],[('0.2.2',112282473,72018818),('0.2.2',112282926,34881784),('0.4.0',209796632,36493542)])
if __name__=='__main__': unittest.main()
