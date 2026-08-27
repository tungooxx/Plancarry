import hashlib, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
P=ROOT/'plancarry_successor_feature_constructibility_prereg_v2_20260827.json'
POP=ROOT/'plancarry_successor_feature_fresh_population_v1_20260827.json'
D=json.loads(P.read_text())
assert hashlib.sha256(POP.read_bytes()).hexdigest()=='d35271102561040901ead7a663e080242b577c9afd75743f94ad3cce014d24d2'
assert D['population_sha256']=='d35271102561040901ead7a663e080242b577c9afd75743f94ad3cce014d24d2'
assert D['future_split_access'] is False and D['environment_execution_in_design']==0 and D['model_calls_in_design']==0
assert D['predictive_procedure']['constructibility_distance']['rows_included']==[3,4]
assert D['predictive_procedure']['constructibility_distance']['rows_excluded']==[1,2]
g=.8
def l1(a,b): return sum(abs(x/255-y/255) for x,y in zip(a,b))
def dfuture(a3,b3,a4,b4): return g**2*l1(a3,b3)+g**3*l1(a4,b4)
# Rejected v1 counterexample: row2 distinct one-hots alone produced 1.6; v2 must score exactly zero if rows3/4 match.
a2=[255,0,0,0,0,0]; b2=[0,255,0,0,0,0]
r3=[43,43,43,42,42,42]; r4=[42,43,43,43,42,42]
old_row2=g*l1(a2,b2)
assert abs(old_row2-1.6)<1e-12
assert dfuture(r3,r3,r4,r4)==0.0
assert dfuture(r3,r3,r4,r4)<D['predictive_procedure']['constructibility_distance']['threshold']
# A genuinely different predicted future can exceed the threshold independently of row2.
x=[255,0,0,0,0,0]; y=[0,255,0,0,0,0]
assert dfuture(x,y,x,y) > 0.50
# Branch plausibility guard is nontrivial.
def softmax(xs):
 m=max(xs); e=[math.exp(x-m) for x in xs]; z=sum(e); return [v/z for v in e]
assert sorted(softmax([0,0,0,0,0,0]),reverse=True)[1] >= 0.10
assert sorted(softmax([10,0,0,0,0,0]),reverse=True)[1] < 0.10
# Fixed neutral causal-control row and serialization geometry are exact.
neutral=[43,43,43,42,42,42]
assert sum(neutral)==255
vals=[neutral]*4
s='SF1:'+''.join(f'{v:02x}' for row in vals for v in row)
assert len(s.encode('ascii'))==52 and len(s.removeprefix('SF1:'))==48
# Repaired time shuffle fixes row1+row2 and permutes only row3,row4.
rows=[a2,b2,r3,r4]; shuffled=[rows[0],rows[1],rows[3],rows[2]]
assert shuffled[0]==rows[0] and shuffled[1]==rows[1] and shuffled[2]==rows[3] and shuffled[3]==rows[2]
# Population split must remain exact and untouched.
pop=json.loads(POP.read_text()); ph=[x['phase'] for x in sorted(pop['paths'],key=lambda z:z['index'])]
assert len(pop['paths'])==37
assert ph[:16]==['constructibility']*16
assert ph[16:32]==['causal_development_locked']*16
assert ph[32:]==['spare_locked']*5
print(json.dumps({'verdict':'PASS_STATIC_PRE_SCIENCE_V2','old_row2_discounted_l1':old_row2,'v2_identical_future_l1':dfuture(r3,r3,r4,r4),'v2_distinct_future_l1':dfuture(x,y,x,y),'population_sha256':hashlib.sha256(POP.read_bytes()).hexdigest()},sort_keys=True))
