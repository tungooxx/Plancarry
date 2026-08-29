import copy
import tempfile
import unittest
from pathlib import Path
from cpds_alfworld_static_source_authority_v1 import *
from cpds_alfworld_static_source_authority_v1 import _forbidden_key_scan

class T(unittest.TestCase):
    def layout(self):
        return [{"asset":{"id":1,"name":"a.zip","size":1000,"etag":"e","central_directory_range":[900,977],"eocd_range":[978,999],"train_entry_count":2,"train_spans":[[100,300,2]]},"entries":[
            {"name":"json_2.1.1/train/x/traj_data.json","header_offset":100,"record_end_exclusive":200,"authorized_train":True},
            {"name":"json_2.1.1/train/y/traj_data.json","header_offset":200,"record_end_exclusive":300,"authorized_train":True},
            {"name":"json_2.1.1/valid_seen/z/traj_data.json","header_offset":300,"record_end_exclusive":500,"authorized_train":False},
        ]}]
    def access(self):
        return [{"asset_id":1,"asset_name":"a.zip","range_start":100,"range_end_inclusive":299,"bytes":200,"sha256":"0"*64,"etag":"e","forbidden_overlap_count":0}]
    def test_train_path_strict(self):
        self.assertEqual(train_relative_path("json_2.1.1/train/a/b.txt"),"a/b.txt")
        for p in ["json_2.1.1/valid_seen/a/b.txt","json_2.1.1/valid_train/a/b.txt","x/train/a"]:
            with self.assertRaises(ValueError): train_relative_path(p)
    def test_layout_and_access_accept_exact(self):
        validate_layout_asset(self.layout()[0]); validate_train_span_access(self.layout(),self.access())
    def test_forbidden_overlap_fails(self):
        x=self.layout(); x[0]["asset"]["train_spans"]=[[100,350,2]]
        with self.assertRaisesRegex(ValueError,"TRAIN_SPAN_OVERLAPS_FORBIDDEN"): validate_layout_asset(x[0])
    def test_access_range_drift_fails(self):
        a=self.access(); a[0]["range_end_inclusive"]=300
        with self.assertRaisesRegex(ValueError,"ACCESS_RANGE_DRIFT"): validate_train_span_access(self.layout(),a)
    def test_forbidden_key_recursive(self):
        with self.assertRaisesRegex(ValueError,"FORBIDDEN_PROVENANCE_KEY"):
            _forbidden_key_scan({"x":[{"future_oracle_trajectory":"x"}]})
    def test_manifest_and_unit_root_deterministic(self):
        rec=[
          {"relative_path":"g/traj_data.json","byte_size":1,"sha256":"a"*64,"source_asset_id":1,"source_asset_name":"a","source_member_name":"m1","source_member_crc32":"00000000","source_member_compress_size":1,"source_member_compress_type":0},
          {"relative_path":"g/initial_state.pddl","byte_size":1,"sha256":"b"*64,"source_asset_id":2,"source_asset_name":"b","source_member_name":"m2","source_member_crc32":"00000000","source_member_compress_size":1,"source_member_compress_type":0},
          {"relative_path":"g/game.tw-pddl","byte_size":1,"sha256":"c"*64,"source_asset_id":3,"source_asset_name":"c","source_member_name":"m3","source_member_crc32":"00000000","source_member_compress_size":1,"source_member_compress_type":0},
        ]
        rec.sort(key=lambda x:x['relative_path']); units=complete_static_graph_units(rec); self.assertEqual(units,['g'])
        art, u=build_authority_artifact(publisher_assets=[],package_provenance={},layout=[],access=[],records=rec,source_admission_refs={})
        verify_authority_artifact(art,rec,u)
        bad=copy.deepcopy(art); bad['train_file_count']+=1
        with self.assertRaises(ValueError): verify_authority_artifact(bad,rec,u)

    def test_full_manifest_from_synthetic_train_span(self):
        import hashlib, struct, zlib, binascii
        raw=b"official-train-bytes\n"
        co=zlib.compressobj(level=6,wbits=-15); comp=co.compress(raw)+co.flush()
        name="json_2.1.1/train/g/traj_data.json"; nb=name.encode()
        crc=binascii.crc32(raw)&0xffffffff
        header=struct.pack("<4s5H3L2H",b"PK\x03\x04",20,0,8,0,0,crc,len(comp),len(raw),len(nb),0)+nb
        segment=header+comp
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); sd=td/'seg'; sd.mkdir(); root=td/'train'; (root/'g').mkdir(parents=True)
            (root/'g'/'traj_data.json').write_bytes(raw)
            sp=sd/'a.zip.train-span.bin'; sp.write_bytes(segment)
            layout=[{"asset":{"id":1,"name":"a.zip","size":len(segment)+100,"etag":"e","central_directory_range":[len(segment),len(segment)+77],"eocd_range":[len(segment)+78,len(segment)+99],"train_entry_count":1,"train_spans":[[0,len(segment),1]]},"entries":[{"name":name,"header_offset":0,"record_end_exclusive":len(segment),"authorized_train":True,"compress_size":len(comp),"file_size":len(raw),"crc32":f"{crc:08x}","compress_type":8,"flag_bits":0}]}]
            access=[{"asset_id":1,"asset_name":"a.zip","range_start":0,"range_end_inclusive":len(segment)-1,"bytes":len(segment),"sha256":hashlib.sha256(segment).hexdigest(),"etag":"e","forbidden_overlap_count":0}]
            rec=build_official_train_manifest(layout,access,sd,root)
            self.assertEqual(rec[0]['sha256'],hashlib.sha256(raw).hexdigest())
            bad=bytearray(segment); bad[-1]^=1; sp.write_bytes(bad)
            with self.assertRaises(ValueError): build_official_train_manifest(layout,access,sd,root)

    def test_snapshot_envelope_exact(self):
        e=build_snapshot_provenance_envelope('a'*64,'b'*64)
        self.assertEqual(set(e),{'schema','official_static_source_authority_sha256','source_snapshot_sha256'})
        with self.assertRaises(ValueError): build_snapshot_provenance_envelope('x','b'*64)
    def test_no_historical_competence_semantics(self):
        art,_=build_authority_artifact(publisher_assets=[],package_provenance={},layout=[],access=[],records=[],source_admission_refs={})
        self.assertEqual(art['source_admission_semantics'],'STATIC_GRAPH_REPLAYABILITY_ONLY')
        self.assertNotIn('local_source_competence_preoutcome', canonical_bytes(art).decode())

if __name__=='__main__': unittest.main()
