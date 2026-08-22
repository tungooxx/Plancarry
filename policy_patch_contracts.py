from gpu_lab.strategy import ResearchStrategyService
from gpu_lab.discovery import fallback_candidates, BRAIN_POLICY_VERSION

# Contract 1: ZERO-information "success" cannot create positive strategy weight.
svc = object.__new__(ResearchStrategyService)
candidate = {
    'action_type':'FROZEN_DIAGNOSTIC', 'priority':100.0, 'available':True,
    'generation_source':'DETERMINISTIC_DISCOVERY_FALLBACK',
    'payload':{'generation_source':'DETERMINISTIC_DISCOVERY_FALLBACK'},
    'score':{'compute_cost':0.2,'expected_discrimination':3.0},
}
zero_pattern = {
    'id':'zero', 'action_type':'FROZEN_DIAGNOSTIC','historical_successes':1,'historical_failures':0,
    'high_information_count':0,'medium_information_count':0,'low_information_count':0,'zero_information_count':1,
    'generation_sources':['DETERMINISTIC_DISCOVERY_FALLBACK'], 'applicability':'HIGH','counterexamples':[],
}
out = svc.adjust_candidates([candidate], {'applied':[zero_pattern]}, {'flag':None}, False)[0]
assert out['positive_strategy_adjustment'] == 0.0, out
assert out['final_priority'] == 100.0, out

# Contract 2: strategy history is isolated by generation source.
positive_fallback = {**zero_pattern, 'id':'positive', 'historical_successes':1,
                     'high_information_count':1,'zero_information_count':0}
configured = {**candidate, 'generation_source':'AGENDA_CONFIGURED',
              'payload':{}, 'priority':100.0}
out = svc.adjust_candidates([configured], {'applied':[positive_fallback]}, {'flag':None}, False)[0]
assert out['positive_strategy_adjustment'] == 0.0, out
assert out['strategy_pattern_ids'] == [], out

# Contract 3: informative, source-matched success still helps.
out = svc.adjust_candidates([candidate], {'applied':[positive_fallback]}, {'flag':None}, False)[0]
assert out['positive_strategy_adjustment'] == 0.08, out
assert out['final_priority'] == 108.0, out

# Contract 4: future strategy patterns preserve discovery source/signature.
params = svc._action_parameters({
    'generation_source':'DETERMINISTIC_DISCOVERY_FALLBACK',
    'payload':{'non_executing_discovery_candidate':True,
               'scientific_dimensions':{'state_variable':'mechanism-specific diagnostic'}}
})
assert params['generation_source'] == 'DETERMINISTIC_DISCOVERY_FALLBACK', params
assert params['non_executing_discovery_candidate'] is True, params
assert params['scientific_dimensions']['state_variable'] == 'mechanism-specific diagnostic', params

# Contract 5: divergent fallback generation itself remains available when genuinely needed.
items = fallback_candidates('q', ['h1'], None, 'MECHANISM_SEARCH')
assert len(items) == 3, items
assert {x['payload']['expected_distance'] for x in items} == {'MID','FAR','ORTHOGONAL'}, items
assert all(x['payload']['non_executing_discovery_candidate'] for x in items), items

assert BRAIN_POLICY_VERSION == 'brain-v3.1-discovery-search-v2', BRAIN_POLICY_VERSION
print('POLICY_PATCH_CONTRACTS_PASS')
