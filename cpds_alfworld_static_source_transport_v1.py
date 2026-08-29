from __future__ import annotations
import concurrent.futures
import hashlib
import json
import struct
import urllib.request
from pathlib import Path
from cpds_alfworld_static_source_authority_v1 import canonical_bytes, train_relative_path

UA = 'PlanCarry-CPDS-source-authority/1.0'
CHUNK_BYTES = 4 * 1024 * 1024
REPOSITORY = 'alfworld/alfworld'
ASSETS = (
    {'release_id':100989857,'tag':'0.2.2','asset_id':112282473,'name':'json_2.1.1_json.zip','size':72018818,'url':'https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_json.zip'},
    {'release_id':100989857,'tag':'0.2.2','asset_id':112282926,'name':'json_2.1.1_pddl.zip','size':34881784,'url':'https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_pddl.zip'},
    {'release_id':187391306,'tag':'0.4.0','asset_id':209796632,'name':'json_2.1.2_tw-pddl.zip','size':36493542,'url':'https://github.com/alfworld/alfworld/releases/download/0.4.0/json_2.1.2_tw-pddl.zip'},
)


def sha256(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def _head(url: str):
    req=urllib.request.Request(url,method='HEAD',headers={'User-Agent':UA,'Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return {'final_url':r.geturl(),'status':r.status,'size':int(r.headers['Content-Length']),'etag':r.headers.get('ETag'),'last_modified':r.headers.get('Last-Modified'),'accept_ranges':r.headers.get('Accept-Ranges')}

def _range_get_exact(final_url: str, start: int, end: int, total: int, allowed_ranges):
    if not any(a <= start <= end < b for a,b in allowed_ranges): raise ValueError('RANGE_OUTSIDE_AUTHORIZED_INTERVAL')
    req=urllib.request.Request(final_url,headers={'User-Agent':UA,'Accept-Encoding':'identity','Range':f'bytes={start}-{end}'})
    with urllib.request.urlopen(req,timeout=120) as r:
        if r.status != 206: raise RuntimeError('HTTP_RANGE_NOT_206')
        if r.headers.get('Content-Range') != f'bytes {start}-{end}/{total}': raise RuntimeError('HTTP_CONTENT_RANGE_MISMATCH')
        data=r.read()
    if len(data) != end-start+1: raise RuntimeError('HTTP_RANGE_LENGTH_MISMATCH')
    return data

def parse_eocd_last22(data: bytes, total_size: int):
    if len(data)!=22 or data[:4]!=b'PK\x05\x06': raise ValueError('EOCD_NOT_EXACT_LAST22')
    sig,disk,cd_disk,n_disk,n_total,cd_size,cd_offset,comment_len=struct.unpack('<4s4H2LH',data)
    if comment_len!=0 or disk!=0 or cd_disk!=0 or n_disk!=n_total: raise ValueError('EOCD_UNSUPPORTED')
    if cd_offset+cd_size != total_size-22: raise ValueError('EOCD_CD_GEOMETRY')
    return {'entry_count':n_total,'central_directory_offset':cd_offset,'central_directory_size':cd_size}

def parse_central_directory(data: bytes, expected_count: int, cd_offset: int):
    fmt='<4s6H3L5H2L'; hsz=struct.calcsize(fmt); pos=0; entries=[]
    while pos<len(data):
        if pos+hsz>len(data): raise ValueError('CENTRAL_DIRECTORY_TRUNCATED')
        vals=struct.unpack_from(fmt,data,pos)
        if vals[0]!=b'PK\x01\x02': raise ValueError('CENTRAL_DIRECTORY_SIGNATURE')
        _,vmade,vneed,flag,comp,mt,md,crc,csize,usize,nlen,xlen,clen,diskno,iattr,eattr,hoff=vals
        if 0xffffffff in (csize,usize,hoff): raise ValueError('ZIP64_NOT_AUTHORIZED')
        start=pos+hsz; nameb=data[start:start+nlen]; enc='utf-8' if flag&0x800 else 'cp437'; name=nameb.decode(enc)
        entries.append({'name':name,'header_offset':hoff,'compress_size':csize,'file_size':usize,'crc32':f'{crc:08x}','compress_type':comp,'flag_bits':flag})
        pos=start+nlen+xlen+clen
    if pos!=len(data) or len(entries)!=expected_count: raise ValueError('CENTRAL_DIRECTORY_COUNT')
    files=[e for e in entries if not e['name'].endswith('/')]
    files.sort(key=lambda e:e['header_offset'])
    for i,e in enumerate(files):
        e['record_end_exclusive']=files[i+1]['header_offset'] if i+1<len(files) else cd_offset
        if not (0<=e['header_offset']<e['record_end_exclusive']<=cd_offset): raise ValueError('LOCAL_RECORD_GEOMETRY')
        try: train_relative_path(e['name']); e['authorized_train']=True
        except ValueError: e['authorized_train']=False
    return entries

def derive_train_spans(entries, cd_offset: int):
    files=sorted((e for e in entries if not e['name'].endswith('/')),key=lambda e:e['header_offset'])
    train=[e for e in files if e.get('authorized_train',False)]; forbidden=[e for e in files if not e.get('authorized_train',False)]
    spans=[]
    for e in train:
        s,t=e['header_offset'],e['record_end_exclusive']
        if spans and spans[-1][1]==s: spans[-1][1]=t; spans[-1][2]+=1
        else: spans.append([s,t,1])
    for s,t,_ in spans:
        for f in forbidden:
            if max(s,f['header_offset']) < min(t,f['record_end_exclusive']): raise ValueError('TRAIN_SPAN_OVERLAPS_FORBIDDEN')
    return spans

def fetch_layout(asset):
    h=_head(asset['url'])
    if h['status']!=200 or h['size']!=asset['size'] or h['accept_ranges']!='bytes': raise RuntimeError('HEAD_AUTHORITY_DRIFT')
    size=h['size']; eocd=_range_get_exact(h['final_url'],size-22,size-1,size,[(size-22,size)])
    eo=parse_eocd_last22(eocd,size); cs=eo['central_directory_offset']; ce=cs+eo['central_directory_size']
    cd=_range_get_exact(h['final_url'],cs,ce-1,size,[(cs,ce)])
    entries=parse_central_directory(cd,eo['entry_count'],cs); spans=derive_train_spans(entries,cs)
    files=[e for e in entries if not e['name'].endswith('/')]
    return {'asset':{'release_id':asset['release_id'],'tag':asset['tag'],'id':asset['asset_id'],'name':asset['name'],'size':size,'etag':h['etag'],'last_modified':h['last_modified'],'eocd_range':[size-22,size-1],'eocd_sha256':sha256(eocd),'central_directory_range':[cs,ce-1],'central_directory_sha256':sha256(cd),'train_entry_count':sum(bool(e.get('authorized_train',False)) for e in files),'forbidden_entry_count':sum(not bool(e.get('authorized_train',False)) for e in files),'train_spans':spans},'entries':entries}

def fetch_train_spans(layout, output_dir: Path, chunk_bytes: int=CHUNK_BYTES):
    output_dir.mkdir(parents=True,exist_ok=True); chunks_dir=output_dir/'chunks'; seg_dir=output_dir/'segments'; chunks_dir.mkdir(exist_ok=True); seg_dir.mkdir(exist_ok=True)
    by_id={x['asset']['id']:x for x in layout}; defs={x['asset_id']:x for x in ASSETS}; jobs=[]; heads={}
    for aid,obj in by_id.items():
        a=obj['asset']; d=defs[aid]; h=_head(d['url'])
        if h['size']!=a['size'] or h['etag']!=a['etag'] or h['accept_ranges']!='bytes': raise RuntimeError('HEAD_DRIFT_BEFORE_BODY')
        heads[aid]=h
        for s,t,_ in a['train_spans']:
            for lo in range(s,t,chunk_bytes): jobs.append((aid,lo,min(t,lo+chunk_bytes)))
    def one(job):
        aid,lo,stop=job; obj=by_id[aid]; a=obj['asset']; h=heads[aid]
        allowed=[(s,t) for s,t,_ in a['train_spans']]
        data=_range_get_exact(h['final_url'],lo,stop-1,a['size'],allowed)
        p=chunks_dir/f'{aid}.{lo}-{stop-1}.bin'; p.write_bytes(data)
        return {'asset_id':aid,'range_start':lo,'range_end_inclusive':stop-1,'bytes':len(data),'sha256':sha256(data),'forbidden_overlap_count':0,'path':str(p)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex: rs=list(ex.map(one,jobs))
    access=[]
    for aid,obj in sorted(by_id.items()):
        a=obj['asset']; ars=sorted((r for r in rs if r['asset_id']==aid),key=lambda r:r['range_start']); hsh=hashlib.sha256(); total=0; expected=[]
        for s,t,_ in a['train_spans']:
            expected.extend(range(s,t,chunk_bytes))
        if [r['range_start'] for r in ars]!=expected: raise RuntimeError('CHUNK_SEQUENCE')
        out=seg_dir/(a['name']+'.train-span.bin')
        with out.open('wb') as f:
            for r in ars:
                b=Path(r['path']).read_bytes()
                if sha256(b)!=r['sha256']: raise RuntimeError('CHUNK_REHASH')
                f.write(b); hsh.update(b); total+=len(b)
        span_bytes=sum(t-s for s,t,_ in a['train_spans'])
        if total!=span_bytes: raise RuntimeError('TRAIN_SPAN_CONCAT_SIZE')
        s0=a['train_spans'][0][0]; t1=a['train_spans'][-1][1]
        access.append({'asset_id':aid,'asset_name':a['name'],'range_start':s0,'range_end_inclusive':t1-1,'bytes':total,'sha256':hsh.hexdigest(),'etag':a['etag'],'forbidden_overlap_count':0,'chunk_count':len(ars),'chunks':[{k:r[k] for k in ('range_start','range_end_inclusive','bytes','sha256','forbidden_overlap_count')} for r in ars]})
    return access

def main():
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['metadata','train-spans','all']); p.add_argument('--output-dir',default='.source_safe_a7402147_repro'); a=p.parse_args(); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    lp=out/'layout.json'
    if a.mode in {'metadata','all'}:
        layout=[fetch_layout(x) for x in ASSETS]; lp.write_bytes(canonical_bytes(layout)); print('LAYOUT_SHA256',sha256(lp.read_bytes()))
    else: layout=json.loads(lp.read_text())
    if a.mode in {'train-spans','all'}:
        access=fetch_train_spans(layout,out); ap=out/'train_span_access.json'; ap.write_bytes(canonical_bytes(access)); print('ACCESS_SHA256',sha256(ap.read_bytes()))
if __name__=='__main__': main()
