import hashlib, json
from pathlib import Path

RULE_IDS = [
  'R0_GENERATOR_AUTHORITY_FROZEN','R1_EQUAL_MATCHED_PREFIX_FIELDS','R2_GRAPH_DIVERGENCE_PREOUTCOME',
  'R3_NO_FORBIDDEN_ELIGIBILITY_DEPENDENCY','R4_NO_SECRET_OR_OUTCOME_PATH_TO_Z0_F_G','R5_CAUSAL_TRANSITION_TIMING',
  'R6_G_NONEXECUTING','R7_STATIC_REPEAT_EXPOSURE_MATCH','R8_PERMUTED_ARM_BUDGET_MATCH',
  'R9_PERMUTATION_NONIDENTITY_OR_PREOUTCOME_INELIGIBLE','R10_PRIMARY_EXCLUDES_FIRST_ACTION','R11_GUARDS_NOT_POSTOUTCOME_FILTERS',
  'R12_GRAPH_FAMILY_DISJOINT_SPLITS','R13_LEGACY_COHORTS_FORBIDDEN','R14_CONSTRUCTIBILITY_NOT_MECHANISTIC_NULL',
  'R15_NO_NUMERIC_SCIENCE_THRESHOLDS_FROZEN_HERE']

def canonical_bytes(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def generator_identity(spec):
    x=dict(spec); x.pop('generator_identity_sha256',None); return sha256_bytes(canonical_bytes(x))
def structural_family_key(family):
    x=dict(family); x.pop('local_source_competence_preoutcome',None); return sha256_bytes(canonical_bytes(x))
def validate_generator_spec(spec):
    req={'schema','generator_name','algorithm_version','input_snapshot_schema','forbidden_input_fields','canonicalization','certificate_algorithm','development_authority','confirmation_independence_contract','carrier_visibility','generator_identity_sha256'}
    if set(spec)!=req: raise ValueError('GENERATOR_SPEC_SCHEMA')
    if spec['generator_identity_sha256'] != generator_identity(spec): raise ValueError('GENERATOR_IDENTITY_MISMATCH')
    if spec['development_authority']['cohort_namespace'] != 'CPDS_DEVELOPMENT_GRAPH_FAMILIES_V1': raise ValueError('DEV_NAMESPACE')
    return True
def _unknown_or_forbidden(obj, forbidden):
    if isinstance(obj,dict):
        for k,v in obj.items():
            if k in forbidden: return True
            if _unknown_or_forbidden(v,forbidden): return True
    elif isinstance(obj,list):
        return any(_unknown_or_forbidden(v,forbidden) for v in obj)
    return False
def generate_certificate(family, spec, cohort_namespace, source_snapshot_sha256):
    validate_generator_spec(spec)
    required=set(spec['input_snapshot_schema']['family_required'])
    if set(family)!=required: raise ValueError('FAMILY_SCHEMA')
    if _unknown_or_forbidden(family,set(spec['forbidden_input_fields'])): raise ValueError('FORBIDDEN_GENERATOR_INPUT')
    for key in ['source_graph_id','goal_canonical','reset_observation_canonical','immediate_next_command_canonical']:
        if not isinstance(family[key],str) or not family[key]: raise ValueError(key)
    if not isinstance(family['allowed_pre_reset_history_canonical'],list) or not all(isinstance(x,str) for x in family['allowed_pre_reset_history_canonical']): raise ValueError('history')
    trans=family['common_prefix_transition_keys']
    if not isinstance(trans,list) or len(trans)<2 or len(set(trans))<2 or not all(isinstance(x,str) and x for x in trans): raise ValueError('transitions')
    for key in ['branch_A_equivalence_class','branch_B_equivalence_class']:
        vals=family[key]
        if not isinstance(vals,list) or not vals or vals != sorted(set(vals)) or not all(isinstance(x,str) and x for x in vals): raise ValueError(key)
    if set(family['branch_A_equivalence_class']) & set(family['branch_B_equivalence_class']): raise ValueError('BRANCH_OVERLAP')
    if not isinstance(family['divergence_depth_after_immediate'],int) or isinstance(family['divergence_depth_after_immediate'],bool) or family['divergence_depth_after_immediate']<1: raise ValueError('divergence')
    if family['local_source_competence_preoutcome'] is not True: raise ValueError('SOURCE_COMPETENCE')
    sk=structural_family_key(family)
    fid=sha256_bytes(canonical_bytes({'generator_identity_sha256':spec['generator_identity_sha256'],'cohort_namespace':cohort_namespace,'source_snapshot_sha256':source_snapshot_sha256,'structural_family_key_sha256':sk}))
    return {'structural_family_key_sha256':sk,'family_id':fid,'cohort_namespace':cohort_namespace,'source_snapshot_sha256':source_snapshot_sha256}
def generate_certificates(families,spec,cohort_namespace,source_snapshot_sha256):
    out=[generate_certificate(f,spec,cohort_namespace,source_snapshot_sha256) for f in families]
    keys=[x['structural_family_key_sha256'] for x in out]
    if len(keys)!=len(set(keys)): raise ValueError('DUPLICATE_STRUCTURAL_FAMILY')
    return sorted(out,key=lambda x:x['structural_family_key_sha256'])
def validate_disjoint(dev,confirm):
    if {x['cohort_namespace'] for x in dev} == {x['cohort_namespace'] for x in confirm}: raise ValueError('COHORT_NAMESPACE_NOT_INDEPENDENT')
    if {x['structural_family_key_sha256'] for x in dev} & {x['structural_family_key_sha256'] for x in confirm}: raise ValueError('STRUCTURAL_FAMILY_OVERLAP')
    if {x['family_id'] for x in dev} & {x['family_id'] for x in confirm}: raise ValueError('FAMILY_ID_OVERLAP')
    return True
def failed_rules(f):
    r=[]
    if not (f['generator_authority_frozen'] and f['generator_spec_present'] and f['generator_identity_matches']): r.append('R0_GENERATOR_AUTHORITY_FROZEN')
    if not f['matched_prefix_fields']: r.append('R1_EQUAL_MATCHED_PREFIX_FIELDS')
    if not f['graph_divergence_preoutcome']: r.append('R2_GRAPH_DIVERGENCE_PREOUTCOME')
    if not f['eligibility_only_preoutcome']: r.append('R3_NO_FORBIDDEN_ELIGIBILITY_DEPENDENCY')
    if f['secret_or_outcome_path_to_carrier']: r.append('R4_NO_SECRET_OR_OUTCOME_PATH_TO_Z0_F_G')
    if f['future_transition_preview']: r.append('R5_CAUSAL_TRANSITION_TIMING')
    if f['G_executes_or_forces']: r.append('R6_G_NONEXECUTING')
    if not all(f[k] for k in ['static_same_exposure_count','static_same_exposure_locations','static_same_state_capacity','static_same_runtime_geometry']): r.append('R7_STATIC_REPEAT_EXPOSURE_MATCH')
    perm=['permuted_same_z0','permuted_same_transition_multiset','permuted_same_update_count','permuted_same_F_G','permuted_same_exposure_count','permuted_same_exposure_locations','permuted_same_runtime_geometry','permuted_same_invocation_sites','permuted_same_timing_budget','permuted_only_order_differs']
    mi=['matched_info_same_capacity','matched_info_same_exposure_count','matched_info_same_exposure_locations','matched_info_same_runtime_geometry','matched_info_same_timing_budget','matched_info_no_target_dependency']
    if not all(f[k] for k in perm) or not all(f[k] for k in mi): r.append('R8_PERMUTED_ARM_BUDGET_MATCH')
    if f['permutation_nonidentity_available'] and not f['permutation_is_nonidentity']: r.append('R9_PERMUTATION_NONIDENTITY_OR_PREOUTCOME_INELIGIBLE')
    if f['primary_includes_first_action']: r.append('R10_PRIMARY_EXCLUDES_FIRST_ACTION')
    if f['guards_used_as_postoutcome_filters']: r.append('R11_GUARDS_NOT_POSTOUTCOME_FILTERS')
    if f['dev_confirm_structural_overlap'] or f['dev_confirm_family_id_overlap'] or f['confirmation_is_reordered_development']: r.append('R12_GRAPH_FAMILY_DISJOINT_SPLITS')
    if f['legacy_cohort_reused']: r.append('R13_LEGACY_COHORTS_FORBIDDEN')
    if f['constructibility_labeled_mechanistic_null']: r.append('R14_CONSTRUCTIBILITY_NOT_MECHANISTIC_NULL')
    if f['numeric_science_threshold_frozen_here']: r.append('R15_NO_NUMERIC_SCIENCE_THRESHOLDS_FROZEN_HERE')
    return r
def validate_fixture(fixture):
    got=failed_rules(fixture['facts']); exp=fixture['expected_failed_rules']
    if got!=exp: raise AssertionError(f"{fixture['id']}: expected {exp}, got {got}")
    if fixture['expected']=='PASS' and got: raise AssertionError('PASS_FAILED')
    if fixture['expected']=='FAIL' and not got: raise AssertionError('FAIL_PASSED')
    return True
def validate_contract_files(contract_path,cases_path,spec_path):
    c=json.loads(Path(contract_path).read_text()); cases=json.loads(Path(cases_path).read_text()); spec=json.loads(Path(spec_path).read_text())
    validate_generator_spec(spec)
    if c['graph_family_generator']['spec_file_sha256'] != sha256_bytes(Path(spec_path).read_bytes()): raise ValueError('SPEC_FILE_SHA')
    if c['graph_family_generator']['generator_identity_sha256'] != spec['generator_identity_sha256']: raise ValueError('CONTRACT_GENERATOR_IDENTITY')
    if c['split_contract']['development_generator_identity'] != spec['generator_identity_sha256']: raise ValueError('DEV_GENERATOR_PLACEHOLDER_OR_MISMATCH')
    per=set(c['matching_invariants']['TRANSITION_PERMUTED_vs_ALIGNED_RECURSION'])
    need={'same_G_exposure_count','same_G_exposure_locations','same_runtime_call_geometry','same_updater_invocation_sites','same_update_timing_budget','only_transition_order_differs'}
    if not need<=per: raise ValueError('PERMUTED_GEOMETRY_INCOMPLETE')
    mi=set(c['matching_invariants']['MATCHED_INFORMATION_vs_ALIGNED_RECURSION'])
    if not {'same_G_exposure_count','same_G_exposure_locations','same_runtime_call_geometry','same_update_timing_budget'}<=mi: raise ValueError('MATCHED_INFO_GEOMETRY_INCOMPLETE')
    if cases['rule_ids'] != RULE_IDS or c['machine_validation_rules'] != RULE_IDS: raise ValueError('RULE_ID_MISMATCH')
    for f in cases['fixtures']: validate_fixture(f)
    covered={r for f in cases['fixtures'] if f['expected']=='FAIL' for r in f['expected_failed_rules']}
    if set(RULE_IDS)-covered: raise ValueError('RULE_COVERAGE_INCOMPLETE')
    return {'rules':len(RULE_IDS),'fixtures':len(cases['fixtures']),'all_passed':True}
