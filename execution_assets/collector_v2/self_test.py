from pathlib import Path
import hashlib, importlib.util
HERE=Path(__file__).resolve().parent
V1=HERE.parent/"planlatch_v7_20_reserved_host_attestation_v1"/"reserved_host_attest.py"
assert hashlib.sha256(V1.read_bytes()).hexdigest()=="63506a8f2324bc6ab19aa34422d0fd678f16bfe3395c0df896df42d6f4598d10"
spec=importlib.util.spec_from_file_location("att",HERE/"reserved_host_attest.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
p=m._resolve_cuda_library("cudart")
assert "libcudart.so" in p, p
v=m.cuda_version("cudart",None,"cudaRuntimeGetVersion")
assert v=="13000", v
d=m.cuda_version("cuda","cuInit","cuDriverGetVersion")
assert int(d)>=13000, d
assert len(m.REQUIRED_FIELDS)==22
print("PASS",p,v,d)
