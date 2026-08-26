"""PlanUnique-only grouped exact candidate scorer.

Engineering-only runtime wrapper. Scientific semantics are inherited unchanged
from the frozen ReplayResidual runtime. Candidate commands are scored in fixed
small groups on repeated *clones* of the immutable live KV cache. The live
session cache, exact suffix token IDs, FP32 token-logprob arithmetic, arithmetic
mean, and deterministic lexical tie-break remain unchanged.

The exact-Qwen/Vast numerical/runtime canary is intentionally deferred until the
currently running scientific Vast job is terminal; this module is not authorized
for scientific execution until that independent canary/review passes.
"""
from __future__ import annotations
from typing import Any, Mapping, Sequence

import localcontinuation_science_driver_v1 as runtime_v1
import replay_residual_t1_session_runtime_v1 as base

CANDIDATE_GROUP_SIZE = 4


class PlanUniqueBatchedTokenSession(base.PersistentTokenSession):
    """Exact-scoring PlanUnique session using fixed groups on cloned KV only."""

    def _serial_from_frozen_live_cache(self, suffix_ids: Sequence[int]) -> tuple[float, int]:
        torch = base._torch()
        ids = [int(x) for x in suffix_ids]
        if not ids:
            raise base.SessionContractError("candidate suffix must be nonempty")
        local_past = base.clone_cache(self.past_key_values)
        local_logits = self.next_logits.detach().clone()
        local_len = int(self.context_len)
        total = 0.0
        for j, token_id in enumerate(ids):
            lp = torch.log_softmax(local_logits.float(), dim=-1)
            total += float(lp[0, token_id].item())
            if j + 1 < len(ids):
                local_past, local_logits = self._step_model(token_id, local_past, local_len)
                local_len += 1
        return total, len(ids)

    def _score_group(self, ids_by_row: Sequence[Sequence[int]]) -> list[tuple[float, int]]:
        """Score <=CANDIDATE_GROUP_SIZE suffixes on one repeated cloned cache."""
        torch = base._torch()
        seqs = [[int(x) for x in s] for s in ids_by_row]
        if not seqs or len(seqs) > CANDIDATE_GROUP_SIZE:
            raise base.SessionContractError("candidate group size outside frozen engineering bound")
        if any(not s for s in seqs):
            raise base.SessionContractError("candidate suffix must be nonempty")
        # The first suffix token is predicted by the exact same frozen live next_logits.
        common_lp = torch.log_softmax(self.next_logits.float(), dim=-1)
        totals = [float(common_lp[0, s[0]].item()) for s in seqs]
        active = [i for i,s in enumerate(seqs) if len(s) > 1]
        if not active:
            return [(totals[i], len(seqs[i])) for i in range(len(seqs))]

        local_past = base.clone_cache(self.past_key_values)
        if not hasattr(local_past, 'batch_repeat_interleave') or not hasattr(local_past, 'batch_select_indices'):
            # Fail-safe compatibility path: still preserves semantics, but no speed claim.
            return [self._serial_from_frozen_live_cache(s) for s in seqs]
        local_past.batch_repeat_interleave(len(active))
        first = torch.tensor([[seqs[i][0]] for i in active], dtype=torch.long, device=self.device)
        mask = torch.ones((len(active), int(self.context_len) + 1), dtype=torch.long, device=self.device)
        with torch.inference_mode():
            out = self.model(input_ids=first, attention_mask=mask, past_key_values=local_past, use_cache=True)
        if not hasattr(out, 'past_key_values') or out.past_key_values is None:
            raise base.SessionContractError("batched candidate model did not return past_key_values")
        local_past = out.past_key_values
        logits = out.logits[:, -1, :].float().detach()
        pos = 1
        while active:
            lp = torch.log_softmax(logits.float(), dim=-1)
            targets = torch.tensor([seqs[i][pos] for i in active], dtype=torch.long, device=self.device)
            vals = lp.gather(1, targets[:, None]).squeeze(1)
            for row, idx in enumerate(active):
                totals[idx] += float(vals[row].item())
            survivors_rows = [row for row, idx in enumerate(active) if len(seqs[idx]) > pos + 1]
            if not survivors_rows:
                break
            sel = torch.tensor(survivors_rows, dtype=torch.long, device=self.device)
            local_past.batch_select_indices(sel)
            next_active = [active[row] for row in survivors_rows]
            step = torch.tensor([[seqs[idx][pos]] for idx in next_active], dtype=torch.long, device=self.device)
            mask = torch.ones((len(next_active), int(self.context_len) + pos + 1), dtype=torch.long, device=self.device)
            with torch.inference_mode():
                out = self.model(input_ids=step, attention_mask=mask, past_key_values=local_past, use_cache=True)
            if not hasattr(out, 'past_key_values') or out.past_key_values is None:
                raise base.SessionContractError("batched candidate model lost past_key_values")
            local_past = out.past_key_values
            logits = out.logits[:, -1, :].float().detach()
            active = next_active
            pos += 1
        return [(totals[i], len(seqs[i])) for i in range(len(seqs))]

    def score_candidates(self, suffix_ids_by_command: Mapping[str, Sequence[int]]) -> tuple[str, dict[str, base.CandidateScore]]:
        self._assert_open()
        if not suffix_ids_by_command:
            raise base.SessionContractError("candidate map must be nonempty")
        commands = sorted(str(x) for x in suffix_ids_by_command)
        seqs = [[int(x) for x in suffix_ids_by_command[c]] for c in commands]
        if any(not s for s in seqs):
            raise base.SessionContractError("candidate suffix must be nonempty")
        before = base.cache_digest(self.past_key_values)
        before_len = base.cache_seq_len(self.past_key_values)
        before_context_len = int(self.context_len)
        before_hook_count = int(self.hook_count)
        rows: dict[str, base.CandidateScore] = {}
        for start in range(0, len(commands), CANDIDATE_GROUP_SIZE):
            stop = min(start + CANDIDATE_GROUP_SIZE, len(commands))
            scored = self._score_group(seqs[start:stop])
            for command, ids, (total, n) in zip(commands[start:stop], seqs[start:stop], scored):
                rows[command] = base.CandidateScore(command, base.token_ids_sha256(ids), n, total, total / n)
        after = base.cache_digest(self.past_key_values)
        if (
            before != after
            or base.cache_seq_len(self.past_key_values) != before_len
            or int(self.context_len) != before_context_len
            or int(self.hook_count) != before_hook_count
        ):
            raise base.SessionContractError("candidate scoring mutated live KV session")
        best = sorted(rows.values(), key=lambda r: (-r.mean_logprob, r.command))[0]
        return best.command, rows

def msa2_arm(tok: Any, model: Any, packet: Mapping[str, Any], base_reset: Mapping[str, Any], layer: int, vector: Any | None, alpha: float, arm: str, active_residual_sha256: str) -> dict[str, Any]:
    rt = runtime_v1.replay_to_reset(packet); sess = None; rows = []
    try:
        if rt.hash() != base_reset['state_hash'] or str(rt.observation) != base_reset['observation'] or sorted(str(x) for x in rt.admissible_commands) != base_reset['commands']:
            raise runtime_v1.ExecutionContractError('ARM_RESET_STATE_MISMATCH')
        scale = alpha if vector is not None else 1.0
        sess = PlanUniqueBatchedTokenSession(model, base_reset['prefix_ids'], layer=layer, vector=vector, mode='add', scale=scale)
        sess.append_ids(base_reset['action_prompt_ids'], event='ACTION_PROMPT_0')
        for ref_pos in (2, 3):
            ref = packet['actions'][ref_pos]
            if rt.hash() != str(ref['pre_state_hash']): raise runtime_v1.ExecutionContractError(f'MSA2_REFERENCE_PRESTATE_MISMATCH:{ref_pos+1}')
            cmds = sorted(str(x) for x in rt.admissible_commands)
            if str(ref['command']) not in cmds: raise runtime_v1.ExecutionContractError('REFERENCE_ACTION_NOT_ADMISSIBLE')
            sess.append_ids(runtime_v1.suffix_map(tok, cmds)[str(ref['command'])], event=f'TEACHER_ACTION_{ref_pos+1}')
            rec = rt.step(str(ref['command']))
            if rec.error or rec.state_hash != str(ref['post_state_hash']): raise runtime_v1.ExecutionContractError('MSA2_TEACHER_REPLAY_MISMATCH')
            sess.append_ids(runtime_v1.continuation_ids(tok, rt.observation, rt.admissible_commands), event=f'TEACHER_OBS_{ref_pos+1}')
            score_ref = packet['actions'][ref_pos+1]; cmds2 = sorted(str(x) for x in rt.admissible_commands)
            if rt.hash() != str(score_ref['pre_state_hash']): raise runtime_v1.ExecutionContractError('MSA2_SCORE_STATE_MISMATCH')
            if cmds2 != sorted(str(x) for x in score_ref['admissible_commands']): raise runtime_v1.ExecutionContractError('MSA2_SCORE_ADMISSIBLE_MISMATCH')
            _best, scores = sess.score_candidates(runtime_v1.suffix_map(tok, cmds2)); scoremap = {c: float(r.mean_logprob) for c, r in scores.items()}
            rows.append({'state_match': True, 'admissible_match': True, 'reference_action': str(score_ref['command']), 'scores': scoremap})
        msa, margin = runtime_v1.phase.matched_state_msa2(rows); prov = sess.close(); sess = None
        return {'msa2': msa, 'reference_action_margin_family': margin, 'hook_count': int(prov['hook_count']), 'session_id_hash': prov['session_id_hash'], 'arm_name': arm, 'selected_layer': int(layer), 'selected_alpha': float(alpha), 'active_residual_sha256': str(active_residual_sha256), 'injected_vector_sha256': prov['injected_vector_sha256'], 'reset_prefix_sha256': prov['reset_prefix_sha256'], 'reset_snapshot_sha256': base_reset['reset_snapshot_sha256']}
    finally:
        if sess is not None and not sess.closed:
            try: sess.close()
            except Exception: pass
        rt.close()


def autonomous_arm(tok: Any, model: Any, packet: Mapping[str, Any], base_reset: Mapping[str, Any], layer: int, vector: Any | None, alpha: float, arm: str, active_residual_sha256: str, mode: str = 'add', continue_to_budget: bool = False, external_reset_snapshot_sha256: str | None = None, session_scale: float | None = None) -> dict[str, Any]:
    rt = runtime_v1.replay_to_reset(packet); sess = None; acts = []; accepted = 0
    try:
        if rt.hash() != base_reset['state_hash']: raise runtime_v1.ExecutionContractError('AUTON_RESET_STATE_MISMATCH')
        scale = 1.0 if mode == 'replace' else (alpha if vector is not None else 1.0)
        sess = PlanUniqueBatchedTokenSession(model, base_reset['prefix_ids'], layer=layer, vector=vector, mode=mode, scale=scale)
        sess.append_ids(base_reset['action_prompt_ids'], event='ACTION_PROMPT_0')
        limit = 12 if continue_to_budget else 3
        for step in range(limit):
            if rt.done or rt.won: break
            cmds = sorted(str(x) for x in rt.admissible_commands)
            if not cmds: break
            pre = rt.hash(); cmd, _scores, _ = sess.choose_and_commit(runtime_v1.suffix_map(tok, cmds), event=f'ACTION_{step+1}'); rec = rt.step(cmd); ok = rec.error is None
            accepted += int(ok); acts.append({'command': cmd, 'pre_state_hash': pre, 'post_state_hash': rec.state_hash, 'accepted': ok})
            if not ok or rt.done or rt.won: break
            sess.append_ids(runtime_v1.continuation_ids(tok, rt.observation, rt.admissible_commands), event=f'OBS_{step+1}')
        primary_acts = acts[:3]; lca = runtime_v1.phase.local_continuation_lca2(packet['actions'][:5], primary_acts); primary_valid = sum(1 for x in primary_acts if x['accepted']); prov = sess.close(); sess = None
        out = {'lca2': lca, 'task_success': 1.0 if rt.won else 0.0, 'valid_action_rate': float(primary_valid / len(primary_acts)) if primary_acts else 0.0, 'generated_action_count': len(primary_acts), 'descriptive_total_action_count': len(acts), 'hook_count': int(prov['hook_count']), 'session_id_hash': prov['session_id_hash'], 'arm_name': arm, 'selected_layer': int(layer), 'selected_alpha': float(alpha), 'active_residual_sha256': str(active_residual_sha256), 'injected_vector_sha256': prov['injected_vector_sha256'], 'reset_prefix_sha256': prov['reset_prefix_sha256'], 'reset_snapshot_sha256': base_reset['reset_snapshot_sha256'], 'external_reset_snapshot_sha256': external_reset_snapshot_sha256, 'visible_plan_slot_token_ids_sha256': base_reset.get('visible_plan_slot_token_ids_sha256'), 'first_action_excluded': True}
        if external_reset_snapshot_sha256 is not None: out['external_reset_snapshot_sha256'] = str(external_reset_snapshot_sha256)
        if base_reset.get('visible_plan_slot_token_ids_sha256') is not None: out['visible_plan_slot_token_ids_sha256'] = base_reset['visible_plan_slot_token_ids_sha256']
        return out
    finally:
        if sess is not None and not sess.closed:
            try: sess.close()
            except Exception: pass
        rt.close()
