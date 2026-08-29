"""PRE-SCIENCE CPDS V2 static-replayability source-admission validator."""
import copy, hashlib, json
from pathlib import Path

def canonical_bytes(obj): return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def generator_identity(spec):
    x=copy.deepcopy(spec); x.pop('generator_identity_sha256',None); return sha256_bytes(canonical_bytes(x))
def structural_family_key(family): return sha256_bytes(canonical_bytes(family))
def source_snapshot_payload(snapshot):
    x=copy.deepcopy(dict(snapshot)); x.pop('snapshot_sha256',None); return x
def source_snapshot_identity(snapshot): return sha256_bytes(canonical_bytes(source_snapshot_payload(snapshot)))
def _sha(x): return isinstance(x,str) and len(x)==64 and all(c in '0123456789abcdef' for c in x)
def _forbidden(obj, forbidden):
    if isinstance(obj,dict): return any(k in forbidden or _forbidden(v,forbidden) for k,v in obj.items())
    if isinstance(obj,list): return any(_forbidden(v,forbidden) for v in obj)
    return False

def validate_generator_spec(spec):
    req={'schema','generator_name','algorithm_version','input_snapshot_schema','forbidden_input_fields','canonicalization','certificate_algorithm','development_authority','confirmation_independence_contract','carrier_visibility','generator_identity_sha256'}
    if set(spec)!=req: raise ValueError('GENERATOR_SPEC_SCHEMA')
    if spec['schema']!='PLANCARRY_CPDS_GRAPHFORK_GENERATOR_SPEC_V2_STATIC_REPLAYABILITY' or spec['algorithm_version']!=2: raise ValueError('GENERATOR_SPEC_VERSION')
    if spec['generator_identity_sha256']!=generator_identity(spec): raise ValueError('GENERATOR_IDENTITY_MISMATCH')
    if 'local_source_competence_preoutcome' in spec['input_snapshot_schema']['family_required']: raise ValueError('BEHAVIORAL_COMPETENCE_STILL_REQUIRED')
    if 'local_source_competence_preoutcome' not in spec['forbidden_input_fields']: raise ValueError('OLD_COMPETENCE_NOT_FORBIDDEN')
    return True

def _validate_step(step):
    req={'transition_key','command','from_state_id','to_state_id'}
    if not isinstance(step,dict) or set(step)!=req: raise ValueError('REPLAY_STEP_SCHEMA')
    if not all(isinstance(step[k],str) and step[k] for k in req): raise ValueError('REPLAY_STEP_VALUE')
    return step

def validate_source_snapshot(snapshot,spec,expected_source_snapshot_sha256):
    validate_generator_spec(spec)
    req=set(spec['input_snapshot_schema']['required_top_level'])
    if not isinstance(snapshot,dict) or set(snapshot)!=req: raise ValueError('SOURCE_SNAPSHOT_SCHEMA')
    if not _sha(expected_source_snapshot_sha256): raise ValueError('EXTERNAL_SOURCE_SEAL_FORMAT')
    actual=source_snapshot_identity(snapshot)
    if snapshot['snapshot_sha256']!=actual or actual!=expected_source_snapshot_sha256: raise ValueError('SOURCE_SNAPSHOT_SHA')
    if _forbidden(snapshot,set(spec['forbidden_input_fields'])): raise ValueError('FORBIDDEN_SOURCE_FIELD')
    if not isinstance(snapshot['snapshot_id'],str) or not snapshot['snapshot_id']: raise ValueError('SNAPSHOT_ID')
    if not isinstance(snapshot['families'],list) or not isinstance(snapshot['static_graph_replayability_witnesses'],list): raise ValueError('SOURCE_LIST_SCHEMA')
    witnesses=snapshot['static_graph_replayability_witnesses']
    ids=[]
    wreq={'source_graph_id','initial_state_id','reset_state_id','pre_reset_steps','immediate_step','common_prefix_steps','branch_A_equivalence_class','branch_B_equivalence_class','divergence_depth_after_immediate'}
    for w in witnesses:
        if not isinstance(w,dict) or set(w)!=wreq: raise ValueError('REPLAY_WITNESS_SCHEMA')
        for k in ['source_graph_id','initial_state_id','reset_state_id']:
            if not isinstance(w[k],str) or not w[k]: raise ValueError('REPLAY_WITNESS_ID')
        ids.append(w['source_graph_id'])
        if not isinstance(w['pre_reset_steps'],list) or not isinstance(w['common_prefix_steps'],list) or not isinstance(w['immediate_step'],dict): raise ValueError('REPLAY_WITNESS_STEPS')
        for s in w['pre_reset_steps']+w['common_prefix_steps']+[w['immediate_step']]: _validate_step(s)
        for k in ['branch_A_equivalence_class','branch_B_equivalence_class']:
            v=w[k]
            if not isinstance(v,list) or not v or v!=sorted(set(v)) or not all(isinstance(x,str) and x for x in v): raise ValueError('REPLAY_WITNESS_BRANCH')
        if set(w['branch_A_equivalence_class']) & set(w['branch_B_equivalence_class']): raise ValueError('REPLAY_WITNESS_BRANCH_OVERLAP')
        if not isinstance(w['divergence_depth_after_immediate'],int) or isinstance(w['divergence_depth_after_immediate'],bool) or w['divergence_depth_after_immediate']<1: raise ValueError('REPLAY_WITNESS_DIVERGENCE')
    if len(ids)!=len(set(ids)): raise ValueError('DUPLICATE_REPLAY_WITNESS')
    return True

def _family_schema(family,spec):
    required=set(spec['input_snapshot_schema']['family_required'])
    if not isinstance(family,dict) or set(family)!=required: raise ValueError('FAMILY_SCHEMA')
    if _forbidden(family,set(spec['forbidden_input_fields'])): raise ValueError('FORBIDDEN_GENERATOR_INPUT')
    for k in ['source_graph_id','goal_canonical','reset_observation_canonical','immediate_next_command_canonical']:
        if not isinstance(family[k],str) or not family[k]: raise ValueError(k)
    h=family['allowed_pre_reset_history_canonical']
    if not isinstance(h,list) or not all(isinstance(x,str) and x for x in h): raise ValueError('history')
    t=family['common_prefix_transition_keys']
    if not isinstance(t,list) or len(t)<2 or len(set(t))!=len(t) or not all(isinstance(x,str) and x for x in t): raise ValueError('transitions')
    for k in ['branch_A_equivalence_class','branch_B_equivalence_class']:
        v=family[k]
        if not isinstance(v,list) or not v or v!=sorted(set(v)) or not all(isinstance(x,str) and x for x in v): raise ValueError(k)
    if set(family['branch_A_equivalence_class'])&set(family['branch_B_equivalence_class']): raise ValueError('BRANCH_OVERLAP')
    d=family['divergence_depth_after_immediate']
    if not isinstance(d,int) or isinstance(d,bool) or d<1: raise ValueError('divergence')

def _witness_for(family,snapshot):
    ws=[w for w in snapshot['static_graph_replayability_witnesses'] if w['source_graph_id']==family['source_graph_id']]
    if len(ws)!=1: raise ValueError('REPLAY_WITNESS_CARDINALITY')
    return ws[0]

def validate_static_replayability(family,w):
    if w['source_graph_id']!=family['source_graph_id']: raise ValueError('REPLAY_GRAPH_ID')
    pre=w['pre_reset_steps']; hist=family['allowed_pre_reset_history_canonical']
    if [s['command'] for s in pre]!=hist: raise ValueError('REPLAY_HISTORY_COMMANDS')
    cur=w['initial_state_id']
    for s in pre:
        if s['from_state_id']!=cur: raise ValueError('REPLAY_PRE_STATE_CHAIN')
        cur=s['to_state_id']
    if cur!=w['reset_state_id']: raise ValueError('REPLAY_RESET_NOT_REACHED')
    imm=w['immediate_step']
    if imm['from_state_id']!=w['reset_state_id'] or imm['command']!=family['immediate_next_command_canonical']: raise ValueError('REPLAY_IMMEDIATE_ILLEGAL')
    cur=imm['to_state_id']
    common=w['common_prefix_steps']
    if [s['transition_key'] for s in common]!=family['common_prefix_transition_keys']: raise ValueError('REPLAY_COMMON_KEYS')
    for s in common:
        if s['from_state_id']!=cur: raise ValueError('REPLAY_COMMON_STATE_CHAIN')
        cur=s['to_state_id']
    if w['branch_A_equivalence_class']!=family['branch_A_equivalence_class'] or w['branch_B_equivalence_class']!=family['branch_B_equivalence_class']: raise ValueError('REPLAY_BRANCH_CLASSES')
    if w['divergence_depth_after_immediate']!=family['divergence_depth_after_immediate']: raise ValueError('REPLAY_DIVERGENCE')
    return True

def generate_certificate(family,spec,cohort_namespace,source_snapshot,expected_source_snapshot_sha256):
    validate_source_snapshot(source_snapshot,spec,expected_source_snapshot_sha256)
    _family_schema(family,spec)
    if not any(family==x for x in source_snapshot['families']): raise ValueError('FAMILY_NOT_IN_AUTHENTICATED_SNAPSHOT')
    validate_static_replayability(family,_witness_for(family,source_snapshot))
    sk=structural_family_key(family)
    fid=sha256_bytes(canonical_bytes({'generator_identity_sha256':spec['generator_identity_sha256'],'cohort_namespace':cohort_namespace,'source_snapshot_sha256':expected_source_snapshot_sha256,'structural_family_key_sha256':sk}))
    return {'structural_family_key_sha256':sk,'family_id':fid,'cohort_namespace':cohort_namespace,'source_snapshot_sha256':expected_source_snapshot_sha256,'source_admission':'STATIC_GRAPH_REPLAYABILITY_ONLY'}

def generate_certificates(families,spec,cohort_namespace,source_snapshot,expected_source_snapshot_sha256):
    out=[generate_certificate(f,spec,cohort_namespace,source_snapshot,expected_source_snapshot_sha256) for f in families]
    ks=[x['structural_family_key_sha256'] for x in out]
    if len(ks)!=len(set(ks)): raise ValueError('DUPLICATE_STRUCTURAL_FAMILY')
    return sorted(out,key=lambda x:x['structural_family_key_sha256'])

def validate_contract_files(contract_path,spec_path):
    c=json.loads(Path(contract_path).read_text()); s=json.loads(Path(spec_path).read_text())
    validate_generator_spec(s)
    if c['graph_family_generator']['spec_file_sha256']!=sha256_bytes(Path(spec_path).read_bytes()): raise ValueError('SPEC_FILE_SHA')
    if c['graph_family_generator']['generator_identity_sha256']!=s['generator_identity_sha256']: raise ValueError('CONTRACT_GENERATOR_IDENTITY')
    rep=c['graph_family_generator']['source_admission_semantic_repair']
    if rep['selected_family']!='REMOVE_FIELD_WITH_STATIC_REPLAYABILITY_CERTIFICATE': raise ValueError('SEMANTIC_REPAIR_CHOICE')
    if rep['local_source_competence_preoutcome_status']!='REMOVED_AND_FORBIDDEN_FROM_FAMILY_ADMISSION': raise ValueError('OLD_COMPETENCE_STATUS')
    if 'static_graph_replayability_certificate_valid' not in c['eligibility_and_guards']['eligibility_allowed']: raise ValueError('STATIC_REPLAY_ELIGIBILITY')
    if c['scientific_result']!='NOT_ASSESSED': raise ValueError('SCIENCE_SCOPE')
    return True
