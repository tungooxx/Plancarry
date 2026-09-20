"""Exact lazy model adapter for PlanLatch v7.9.

Importing this module has no torch/transformers side effects.  Real model load
occurs only when ``RealQwenRuntime`` is instantiated by an authorized science
wrapper.  All model-facing intervention semantics are frozen here before
scientific response inspection.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import planlatch_v7_9_protocol as protocol
import planlatch_v7_9_runner as core

EXPECTED_TRANSFORMERS = "4.51.3"
EXPECTED_TOKENIZERS = "0.21.1"
EXPECTED_TORCH = "2.13.0+cu130"
SOURCE_ABLATION_SITE = "qwen-mlp-down_proj-input-post-gated-last-visible-token-v1"
SOURCE_RESPONSE = "baseline-minus-zero-ablation-next-token-logprob-over-opaque-probes-v1"
PAYLOAD_SITE = "qwen-mlp-down_proj-input-post-gated-last-visible-token-v1"
PAYLOAD_COMPOSITION = "one-distinct-channel-per-payload;simultaneous-multiplicative-gain-v1"
ENDPOINT_SCORING = "exact-prefix-suffix-logprob-sum-and-mean;choice-softmax-over-mean-v1"

class ModelRuntimeViolation(RuntimeError):
    pass


def _stable_json(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha(x: Any) -> str:
    return hashlib.sha256(_stable_json(x).encode()).hexdigest()


@dataclass(frozen=True)
class ModelRuntimeFingerprint:
    model_id: str
    requested_revision: str
    resolved_revision: str
    dtype: str
    quantization: str
    device_name: str
    torch_version: str
    transformers_version: str
    tokenizers_version: str
    layer_count: int
    intermediate_sizes: tuple[int, ...]
    parameter_count: int
    candidate_channels: tuple[tuple[int,int], ...]
    candidate_channel_hash: str
    opaque_probe_token_ids: tuple[int, ...]
    opaque_probe_hash: str
    source_ablation_site: str
    source_response: str
    payload_site: str
    payload_composition: str
    endpoint_scoring: str
    fingerprint_hash: str


def _ensure_versions(torch: Any, transformers: Any, tokenizers: Any) -> None:
    got=(str(torch.__version__),str(transformers.__version__),str(tokenizers.__version__))
    want=(EXPECTED_TORCH,EXPECTED_TRANSFORMERS,EXPECTED_TOKENIZERS)
    if got != want:
        raise ModelRuntimeViolation(f"runtime package mismatch got={got} want={want}")


def _hidden_arg(args: tuple[Any,...]) -> Any:
    if not args:
        raise ModelRuntimeViolation("down_proj pre-hook received no input")
    x=args[0]
    if getattr(x,"ndim",None)!=3:
        raise ModelRuntimeViolation("expected [batch,seq,intermediate] down_proj input")
    return x


class RealQwenRuntime:
    """Qwen3 adapter with exact revision, dtype and hook semantics."""
    def __init__(self, *, device: str="cuda") -> None:
        try:
            import torch  # type: ignore
            import transformers  # type: ignore
            import tokenizers  # type: ignore
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:
            raise ModelRuntimeViolation(f"runtime imports unavailable: {type(exc).__name__}: {exc}") from exc
        _ensure_versions(torch,transformers,tokenizers)
        if device != "cuda" or not torch.cuda.is_available():
            raise ModelRuntimeViolation("exact real runtime requires CUDA")
        torch.manual_seed(0)
        if hasattr(torch.cuda,"manual_seed_all"): torch.cuda.manual_seed_all(0)
        torch.use_deterministic_algorithms(True)
        if hasattr(torch.backends,"cuda") and hasattr(torch.backends.cuda,"matmul"):
            torch.backends.cuda.matmul.allow_tf32=False
        if hasattr(torch.backends,"cudnn"):
            torch.backends.cudnn.allow_tf32=False
            torch.backends.cudnn.deterministic=True
            torch.backends.cudnn.benchmark=False
        self.torch=torch; self.transformers=transformers; self.tokenizers=tokenizers
        self.device=torch.device("cuda")
        self.tokenizer=AutoTokenizer.from_pretrained(core.MODEL_ID,revision=core.MODEL_REVISION,trust_remote_code=False)
        self.model=AutoModelForCausalLM.from_pretrained(core.MODEL_ID,revision=core.MODEL_REVISION,torch_dtype=torch.bfloat16,trust_remote_code=False,low_cpu_mem_usage=False).to(self.device).eval()
        if getattr(self.model.config,"quantization_config",None) is not None:
            raise ModelRuntimeViolation("quantized model configuration is forbidden")
        bad_dtype=[name for name,param in self.model.named_parameters() if param.is_floating_point() and param.dtype!=torch.bfloat16]
        if bad_dtype:
            raise ModelRuntimeViolation(f"non-bfloat16 floating parameters detected: {bad_dtype[:8]}")
        bad_device=[name for name,param in self.model.named_parameters() if param.device.type!="cuda"]
        if bad_device:
            raise ModelRuntimeViolation(f"offloaded/non-CUDA parameters detected: {bad_device[:8]}")
        self.layers=self._layers()
        self.intermediate_sizes=tuple(self._intermediate_size(layer) for layer in self.layers)
        self.candidate_channels=core.derive_candidate_channels(self.intermediate_sizes)
        self.candidate_channel_hash=_sha(tuple((x.block,x.channel) for x in self.candidate_channels))
        specials=set(getattr(self.tokenizer,"all_special_ids",[]) or [])
        self.probe_bank=core.derive_opaque_probe_bank(int(self.model.config.vocab_size),specials)
        self.probe_bank_hash=self.probe_bank.bank_hash

    def _layers(self):
        layers=getattr(getattr(self.model,"model",None),"layers",None)
        if layers is None: raise ModelRuntimeViolation("Qwen model.model.layers unavailable")
        return layers

    @staticmethod
    def _intermediate_size(layer: Any) -> int:
        mlp=getattr(layer,"mlp",None); down=getattr(mlp,"down_proj",None)
        n=getattr(down,"in_features",None)
        if not isinstance(n,int) or n<=0: raise ModelRuntimeViolation("Qwen MLP down_proj.in_features unavailable")
        return n

    def fingerprint(self) -> ModelRuntimeFingerprint:
        resolved_raw=getattr(self.model.config,"_commit_hash",None)
        if not isinstance(resolved_raw,str) or not resolved_raw:
            raise ModelRuntimeViolation("resolved model commit hash is unavailable; refusing requested-revision fallback")
        resolved=str(resolved_raw)
        if resolved != core.MODEL_REVISION:
            raise ModelRuntimeViolation(f"resolved model revision mismatch: {resolved}")
        coords=tuple((x.block,x.channel) for x in self.candidate_channels)
        body={
            "model_id":core.MODEL_ID,"requested_revision":core.MODEL_REVISION,"resolved_revision":resolved,
            "dtype":core.MODEL_DTYPE,"quantization":core.MODEL_QUANTIZATION,
            "device_name":str(self.torch.cuda.get_device_name(0)),"torch_version":str(self.torch.__version__),
            "transformers_version":str(self.transformers.__version__),"tokenizers_version":str(self.tokenizers.__version__),
            "layer_count":len(self.layers),"intermediate_sizes":self.intermediate_sizes,
            "parameter_count":sum(int(p.numel()) for p in self.model.parameters()),
            "candidate_channels":coords,"candidate_channel_hash":_sha(coords),
            "opaque_probe_token_ids":self.probe_bank.token_ids,"opaque_probe_hash":self.probe_bank.bank_hash,
            "source_ablation_site":SOURCE_ABLATION_SITE,"source_response":SOURCE_RESPONSE,
            "payload_site":PAYLOAD_SITE,"payload_composition":PAYLOAD_COMPOSITION,"endpoint_scoring":ENDPOINT_SCORING,
        }
        return ModelRuntimeFingerprint(**body,fingerprint_hash=_sha(body))

    def _encode(self,text: str):
        batch=self.tokenizer(text,return_tensors="pt",add_special_tokens=True)
        return {k:v.to(self.device) for k,v in batch.items()}

    def _next_probe_logp(self,batch: Mapping[str,Any]) -> tuple[float,...]:
        with self.torch.inference_mode():
            out=self.model(**batch,use_cache=False)
            lp=self.torch.log_softmax(out.logits[0,-1,:].float(),dim=-1)
        return tuple(float(lp[i].item()) for i in self.probe_bank.token_ids)

    def _zero_channel_hook(self, channel: int):
        def hook(_module: Any,args: tuple[Any,...]):
            x=_hidden_arg(args)
            if channel < 0 or channel >= int(x.shape[-1]): raise ModelRuntimeViolation("zero-ablation channel outside intermediate width")
            y=x.clone(); y[:,-1,channel]=0
            return (y,*args[1:])
        return hook

    def collect_response_tensor(self, donor_prompt: str) -> tuple[float,...]:
        """Run exact last-visible-token zero ablations; returns candidate-major/probe-major T."""
        batch=self._encode(donor_prompt)
        baseline=self._next_probe_logp(batch)
        responses=[]
        for coord in self.candidate_channels:
            down=self.layers[coord.block].mlp.down_proj
            handle=down.register_forward_pre_hook(self._zero_channel_hook(coord.channel))
            try:
                ablated=self._next_probe_logp(batch)
            finally:
                handle.remove()
            responses.extend(float(b-a) for b,a in zip(baseline,ablated))
        expected=len(self.candidate_channels)*len(self.probe_bank.token_ids)
        if len(responses)!=expected: raise ModelRuntimeViolation("response tensor width mismatch")
        return tuple(responses)

    def _payload_hooks(self,payload: protocol.PayloadManifest,prompt_index: int):
        protocol.validate_payload_manifest(payload)
        by_block: dict[int,dict[int,float]]={}
        for t in payload.triples:
            if t.transformer_block_index >= len(self.layers): raise ModelRuntimeViolation("payload block outside model")
            width=self.intermediate_sizes[t.transformer_block_index]
            if t.mlp_intermediate_channel_index >= width: raise ModelRuntimeViolation("payload channel outside model")
            slot=by_block.setdefault(t.transformer_block_index,{})
            if t.mlp_intermediate_channel_index in slot: raise ModelRuntimeViolation("payload must use distinct (block,channel) coordinates")
            slot[t.mlp_intermediate_channel_index]=float(t.gain)
        handles=[]
        for block,mapping in sorted(by_block.items()):
            def make_hook(mapping=mapping):
                def hook(_module: Any,args: tuple[Any,...]):
                    x=_hidden_arg(args)
                    if prompt_index<0 or prompt_index>=int(x.shape[1]): raise ModelRuntimeViolation("prompt boundary outside sequence")
                    y=x.clone()
                    for ch,gain in mapping.items(): y[:,prompt_index,ch]=y[:,prompt_index,ch]*gain
                    return (y,*args[1:])
                return hook
            handles.append(self.layers[block].mlp.down_proj.register_forward_pre_hook(make_hook()))
        return handles

    def _exact_prefix_ids(self,prompt: str,suffix: str):
        p=self.tokenizer(prompt,return_tensors="pt",add_special_tokens=True)["input_ids"][0]
        f=self.tokenizer(prompt+suffix,return_tensors="pt",add_special_tokens=True)["input_ids"][0]
        n=int(p.numel())
        if int(f.numel())<=n or not self.torch.equal(f[:n],p):
            raise ModelRuntimeViolation("endpoint suffix violates exact tokenizer-prefix boundary")
        return p,f

    def score_opaque_endpoints(self,visible_context: str,endpoints: Mapping[str,str],payload: protocol.PayloadManifest|None) -> dict[str,Any]:
        if len(endpoints)<2: raise ModelRuntimeViolation("at least two opaque endpoints required")
        rows={}
        for endpoint_id in sorted(endpoints):
            if any(x in endpoint_id.lower() for x in ("p","q","semantic","label")):
                raise ModelRuntimeViolation("endpoint IDs must be opaque")
            prompt_ids,full_cpu=self._exact_prefix_ids(visible_context,endpoints[endpoint_id])
            prompt_len=int(prompt_ids.numel()); full=full_cpu.unsqueeze(0).to(self.device); mask=self.torch.ones_like(full)
            handles=[]
            if payload is not None: handles=self._payload_hooks(payload,prompt_len-1)
            try:
                with self.torch.inference_mode():
                    out=self.model(input_ids=full,attention_mask=mask,use_cache=False)
                    logits=out.logits[:,:-1,:].float(); labels=full[:,1:]
                    lp=self.torch.log_softmax(logits,dim=-1).gather(-1,labels.unsqueeze(-1)).squeeze(-1)[0]
                    cont=lp[prompt_len-1:]
                    total=float(cont.sum().item()); count=int(cont.numel())
            finally:
                for h in handles: h.remove()
            rows[endpoint_id]={"logprob_sum":total,"token_count":count,"mean_logprob":total/count}
        # Choice normalization is over mean logprob, avoiding raw endpoint-length preference.
        ids=sorted(rows); vals=[rows[k]["mean_logprob"] for k in ids]; m=max(vals); z=sum(math.exp(v-m) for v in vals)
        for k,v in zip(ids,vals): rows[k]["choice_probability"]=math.exp(v-m)/z
        best=sorted(ids,key=lambda k:(-rows[k]["choice_probability"],k))[0]
        return {"endpoints":rows,"top1_endpoint":best,"payload_applied":payload is not None,"scoring_contract":ENDPOINT_SCORING}

    def parameter_sha256(self) -> str:
        """Expensive full parameter checksum, used at science boundary before/after interventions."""
        h=hashlib.sha256()
        for name,param in self.model.named_parameters():
            h.update(name.encode()); h.update(str(tuple(param.shape)).encode()); h.update(str(param.dtype).encode())
            # Hash exact storage bytes without asking NumPy to represent bfloat16.
            arr=param.detach().contiguous().view(self.torch.uint8).cpu()
            h.update(arr.numpy().tobytes())
        return h.hexdigest()
