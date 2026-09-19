"""Environment-only prospective TRAIN cohort materializer for PlanLatch v7.9.

This module performs no tokenizer/model/CUDA calls. It audits ALFWorld
json_2.1.1/train task families, excludes any family name already referenced in
project design/science artifacts, validates both semantic completion orders by
environment replay, and freezes exactly 36 fresh base-task identities.

Scientific mechanics remain delegated to the independently reviewed v7.9
runner/driver. The only substantive prompt program reused here is the
established PlanCarry two-order form:
  RESET block + PLAN OPTIONS + fixed OPTION A/B + ACTIVE ORDER marker.
Matched sham uses ARCHIVED ORDER + ACTIVE ORDER NONE.

A/H are hidden construction-path variables: all four A/H render routes are
required to emit byte-identical text for a fixed base/S/sham/M0. M0 fixes
option orientation before S assignment but is never serialized as a label.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

# Bind the exact persistent official ALFWorld corpus before importing the legacy runtime.
# This avoids its historical attempt to create a /opt/gpu-lab/data symlink on read-only hosts.
os.environ["ALFWORLD_DATA"] = "/opt/gpu-lab/envs/plancarry-alfworld-data"

from alfworld_runtime import AlfRuntime, replay, _facts, stable_json as alf_stable_json
import planlatch_v7_9_runner as core
import planlatch_v7_9_execution_driver as driver

EXPERIMENT_ID = driver.EXPERIMENT_ID
DESIGN_ID = driver.DESIGN_ID
SEMANTIC_HASH = driver.SEMANTIC_HASH
KIND = driver.ROOT_KIND
TRAIN_ROOT = Path("/opt/gpu-lab/envs/plancarry-alfworld-data/json_2.1.1/train")
DATASET_ROOT = TRAIN_ROOT.parent
PROJECT_RESULTS_ROOTS = (Path("results/design"), Path("results/science"))
FAMILY_RE = re.compile(r"(pick_two_obj_and_place-[A-Za-z0-9]+-None-[A-Za-z0-9]+-\d+)")
FAMILY_PARSE_RE = re.compile(r"^pick_two_obj_and_place-(.+?)-None-(.+?)-\d+$")
TRIAL_SALT = "planlatch-v7.9-train-trial-2026-09-19"
COHORT_SALT = "planlatch-v7.9-train-fresh36-2026-09-19"
M0_SALT = "planlatch-v7.9-m0-option-orientation-2026-09-19"
PROVENANCE_SALT = "planlatch-v7.9-provenance-v1"
TARGET_B = 36
OUTPUT_DIR_DEFAULT = Path("results/design/planlatch_v7_9_train_input")

RESET_TEMPLATE = (
    "TASK\n{TASK_TEXT}\n"
    "CURRENT OBSERVATION\n{RESET_OBSERVATION}\n"
    "ADMISSIBLE COMMANDS\n{ONE_COMMAND_PER_LINE_LEXICOGRAPHIC}\n"
    "<STATE_END>\n"
)
ACTIVE_TEMPLATE = (
    "{RESET_BLOCK}PLAN OPTIONS\n"
    "OPTION A: {CLAUSE_A}\n"
    "OPTION B: {CLAUSE_B}\n"
    "ACTIVE ORDER: {ORDER}\n"
    "<STATE_END>\n"
)
SHAM_TEMPLATE = (
    "{RESET_BLOCK}PLAN OPTIONS\n"
    "OPTION A: {CLAUSE_A}\n"
    "OPTION B: {CLAUSE_B}\n"
    "ARCHIVED ORDER: {ORDER}\n"
    "ACTIVE ORDER: NONE\n"
    "<STATE_END>\n"
)
# Semantics-free, identical suffix. Exact bytes are frozen by WASHOUT_HASH.
# It follows an already identical <STATE_END> boundary in every cell.
WASHOUT_SUFFIX = "\n<NEUTRAL_WASHOUT>\n\n</NEUTRAL_WASHOUT>\n"
WASHOUT_HASH = hashlib.sha256(WASHOUT_SUFFIX.encode("utf-8")).hexdigest()

DONOR_PROGRAM_DESCRIPTOR = {
    "version": "planlatch-v7.9-train-donor-program-v1",
    "reset_template": RESET_TEMPLATE,
    "active_template": ACTIVE_TEMPLATE,
    "sham_template": SHAM_TEMPLATE,
    "washout_sha256": WASHOUT_HASH,
    "S": {"p": "A THEN B", "q": "B THEN A"},
    "M0": "sha256-pre-S option-orientation bit; identifier not serialized",
    "A_H": "hidden equivalent constructor routes; byte-identical output required",
    "task_source": "visible initial TextWorld task line only",
    "reset_context": "exact environment replay reset observation + lexicographically sorted admissible commands",
    "option_clause": "Complete {object} from {source} into {target}.",
    "sham": "ARCHIVED ORDER matching S plus ACTIVE ORDER NONE",
}
DONOR_PROGRAM_HASH = hashlib.sha256(
    json.dumps(DONOR_PROGRAM_DESCRIPTOR, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
).hexdigest()


class BuilderViolation(RuntimeError):
    pass


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha_json(value: Any) -> str:
    return sha_text(stable_json(value))


def _artifact_files(output_dir: Path) -> list[Path]:
    out = output_dir.resolve()
    files: list[Path] = []
    for root in PROJECT_RESULTS_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".json", ".jsonl", ".txt"}:
                continue
            try:
                if p.resolve().is_relative_to(out):
                    continue
            except ValueError:
                pass
            files.append(p)
    return sorted(files, key=lambda p: p.as_posix())


def exclusion_snapshot(output_dir: Path) -> dict[str, Any]:
    referenced: set[str] = set()
    file_rows = []
    for p in _artifact_files(output_dir):
        raw = p.read_bytes()
        text = raw.decode("utf-8", errors="ignore")
        hits = sorted(set(FAMILY_RE.findall(text)))
        referenced.update(hits)
        file_rows.append({
            "path": p.as_posix(),
            "sha256": sha_bytes(raw),
            "family_hit_count": len(hits),
        })
    return {
        "scanner_version": "planlatch-v7.9-global-family-reference-scan-v1",
        "roots": [p.as_posix() for p in PROJECT_RESULTS_ROOTS],
        "output_dir_excluded": output_dir.as_posix(),
        "file_count": len(file_rows),
        "file_rows": file_rows,
        "referenced_families": sorted(referenced),
        "snapshot_hash": sha_json(file_rows),
        "referenced_family_set_hash": sha_json(sorted(referenced)),
    }


def choose_trial(family: Path) -> Path:
    games = sorted(family.glob("trial_*/game.tw-pddl"))
    if not games:
        raise BuilderViolation(f"no game trial: {family.name}")
    return min(games, key=lambda p: sha_text(f"{TRIAL_SALT}|{family.name}|{p.parent.name}"))


def family_goal(name: str) -> tuple[str, str]:
    m = FAMILY_PARSE_RE.match(name)
    if not m:
        raise BuilderViolation(f"unexpected family name: {name}")
    return m.group(1).lower(), m.group(2).lower()


def strip_typed(value: str) -> str:
    return re.sub(
        r"\s*:\s*(?:object|receptacle|otype|rtype|location|agent)\s*$",
        "",
        value.strip(),
        flags=re.I,
    )


def parse_fact_state(info: Mapping[str, Any]) -> dict[str, Any]:
    obj_type: dict[str, str] = {}
    rec_type: dict[str, str] = {}
    in_rec: dict[str, str] = {}
    openable: set[str] = set()
    for fact in _facts(dict(info)):
        low = fact.lower()
        m = re.match(r"objecttype\((.*?),\s*(.*?)\)$", low)
        if m:
            obj_type[strip_typed(m.group(1))] = strip_typed(m.group(2)).removesuffix("type")
            continue
        m = re.match(r"receptacletype\((.*?),\s*(.*?)\)$", low)
        if m:
            rec_type[strip_typed(m.group(1))] = strip_typed(m.group(2)).removesuffix("type")
            continue
        m = re.match(r"inreceptacle\((.*?),\s*(.*?)\)$", low)
        if m:
            in_rec[strip_typed(m.group(1))] = strip_typed(m.group(2))
            continue
        m = re.match(r"openable\((.*?)\)$", low)
        if m:
            openable.add(strip_typed(m.group(1)))
    return {"obj_type": obj_type, "rec_type": rec_type, "in_rec": in_rec, "openable": openable}


def exact_command(rt: AlfRuntime, text: str) -> str:
    if text not in rt.admissible_commands:
        raise BuilderViolation(f"missing admissible command {text!r}")
    return text


def do(rt: AlfRuntime, text: str, records: list[Any]) -> Any:
    out = rt.step(exact_command(rt, text))
    if out.error:
        raise BuilderViolation(str(out.error))
    records.append(out)
    return out


def go_open(rt: AlfRuntime, receptacle: str, records: list[Any]) -> None:
    do(rt, f"go to {receptacle}", records)
    if f"open {receptacle}" in rt.admissible_commands:
        do(rt, f"open {receptacle}", records)


def branch_from_reset(
    game: str, prefix_records: list[Any], first: Mapping[str, Any],
    second: Mapping[str, Any], target_rec: str
) -> dict[str, Any]:
    rt = replay(game, prefix_records, max_steps=40)
    records: list[Any] = []
    try:
        take_first = f'take {first["object"]} from {first["source"]}'
        if take_first not in rt.admissible_commands:
            go_open(rt, str(first["source"]), records)
        first_divergent = take_first if not records else records[0].command
        do(rt, take_first, records)
        go_open(rt, target_rec, records)
        do(rt, f'move {first["object"]} to {target_rec}', records)
        go_open(rt, str(second["source"]), records)
        do(rt, f'take {second["object"]} from {second["source"]}', records)
        go_open(rt, target_rec, records)
        do(rt, f'move {second["object"]} to {target_rec}', records)
        return {
            "valid": bool(rt.won),
            "done": bool(rt.done),
            "final_hash": rt.hash(),
            "actions": [x.command for x in records],
            "first_divergent": first_divergent,
        }
    finally:
        rt.close()


def _task_line(initial_observation: str) -> str:
    rows = [line.strip() for line in initial_observation.splitlines() if line.strip().startswith("Your task is to:")]
    if len(rows) != 1:
        raise BuilderViolation(f"TASK_TEXT_EXTRACTION_FAILED count={len(rows)}")
    return rows[0]


def audit_family(family: Path) -> dict[str, Any]:
    game = choose_trial(family)
    target_type, target_rec_type = family_goal(family.name)
    rt = AlfRuntime(str(game), max_steps=40)
    prefix: list[Any] = []
    try:
        initial_obs = rt.observation
        initial_hash = rt.hash()
        initial_commands = list(rt.admissible_commands)
        fs = parse_fact_state(rt.info)
        target_recs = sorted(
            r for r, t in fs["rec_type"].items()
            if t == target_rec_type and f"go to {r}" in initial_commands
        )
        if not target_recs:
            return {"family": family.name, "eligible": False, "reason": "NO_TARGET_RECEPTACLE_COMMAND"}
        target_rec = target_recs[0]
        objects = []
        for obj, typ in fs["obj_type"].items():
            if typ != target_type:
                continue
            src = fs["in_rec"].get(obj)
            if not src or fs["rec_type"].get(src) == target_rec_type:
                continue
            objects.append({
                "object": obj,
                "source": src,
                "source_type": fs["rec_type"].get(src),
                "source_openable": src in fs["openable"],
            })
        objects.sort(key=lambda x: (x["source"], x["object"]))
        if len(objects) < 2:
            return {"family": family.name, "eligible": False, "reason": "LT2_UNFINISHED_TARGET_OBJECTS"}
        by_source: dict[str, list[dict[str, Any]]] = {}
        for obj in objects:
            by_source.setdefault(str(obj["source"]), []).append(obj)
        delayed_groups = [(s, xs) for s, xs in by_source.items() if len(xs) >= 2]
        delayed_groups.sort(key=lambda z: (-len(z[1]), z[0]))
        if delayed_groups:
            src, xs = delayed_groups[0]
            pair = xs[:2]
            go_open(rt, src, prefix)
            delayed = True
        else:
            first_by_source = [sorted(xs, key=lambda x: x["object"])[0] for _, xs in sorted(by_source.items())]
            if len(first_by_source) < 2:
                return {"family": family.name, "eligible": False, "reason": "NO_TWO_DISTINCT_SOURCES"}
            pair = first_by_source[:2]
            delayed = False
        reset_hash = rt.hash()
        reset_obs = rt.observation
        reset_cmds = list(rt.admissible_commands)
        prefix_actions = [x.command for x in prefix]
        task_text = _task_line(initial_obs)
    finally:
        rt.close()

    raw_a, raw_b = pair
    branch_a = branch_from_reset(str(game), prefix, raw_a, raw_b, target_rec)
    branch_b = branch_from_reset(str(game), prefix, raw_b, raw_a, target_rec)
    if not (branch_a["valid"] and branch_b["valid"]):
        return {
            "family": family.name, "eligible": False, "reason": "BRANCH_REPLAY_NOT_BOTH_SUCCESS",
            "a_valid": branch_a["valid"], "b_valid": branch_b["valid"],
        }
    rel_game = game.relative_to(DATASET_ROOT).as_posix()
    return {
        "family": family.name,
        "eligible": True,
        "trial": game.parent.name,
        "game_path": rel_game,
        "game_sha256": sha_file(game),
        "target_object_type": target_type,
        "target_receptacle_type": target_rec_type,
        "target_receptacle": target_rec,
        "object_a": raw_a,
        "object_b": raw_b,
        "delayed_divergence": delayed,
        "common_prefix_actions": prefix_actions,
        "initial_state_hash": initial_hash,
        "task_text": task_text,
        "reset_state_hash": reset_hash,
        "reset_observation": reset_obs,
        "reset_observation_sha256": sha_text(reset_obs),
        "reset_admissible_commands": reset_cmds,
        "reset_admissible_commands_sha256": sha_text(alf_stable_json(reset_cmds)),
        "a_first_divergent_action": branch_a["first_divergent"],
        "b_first_divergent_action": branch_b["first_divergent"],
        "branch_a_actions": branch_a["actions"],
        "branch_b_actions": branch_b["actions"],
        "branch_a_won": branch_a["valid"],
        "branch_b_won": branch_b["valid"],
    }


def m0_for(row: Mapping[str, Any]) -> tuple[str, int]:
    digest = sha_text(f'{M0_SALT}|{row["family"]}|{row["trial"]}|{row["reset_state_hash"]}')
    return "m0-" + digest[:16], int(digest[:2], 16) % 2


def option_assignment(row: Mapping[str, Any]) -> dict[str, Any]:
    m0, bit = m0_for(row)
    if bit == 0:
        option_a, option_b = row["object_a"], row["object_b"]
        cmd_a, cmd_b = row["a_first_divergent_action"], row["b_first_divergent_action"]
    else:
        option_a, option_b = row["object_b"], row["object_a"]
        cmd_a, cmd_b = row["b_first_divergent_action"], row["a_first_divergent_action"]
    return {"m0": m0, "orientation_bit": bit, "option_a": option_a, "option_b": option_b, "command_a": cmd_a, "command_b": cmd_b}


def clause(obj: Mapping[str, Any], target: str) -> str:
    return f'Complete {obj["object"]} from {obj["source"]} into {target}.'


def reset_block(row: Mapping[str, Any]) -> str:
    return RESET_TEMPLATE.format(
        TASK_TEXT=row["task_text"],
        RESET_OBSERVATION=row["reset_observation"],
        ONE_COMMAND_PER_LINE_LEXICOGRAPHIC="\n".join(sorted(row["reset_admissible_commands"])),
    )


def _semantic_body(row: Mapping[str, Any], s: str, sham: bool) -> tuple[str, dict[str, Any]]:
    assigned = option_assignment(row)
    ca = clause(assigned["option_a"], str(row["target_receptacle"]))
    cb = clause(assigned["option_b"], str(row["target_receptacle"]))
    order = "A THEN B" if s == "p" else "B THEN A"
    values = {
        "RESET_BLOCK": reset_block(row), "CLAUSE_A": ca, "CLAUSE_B": cb, "ORDER": order,
    }
    template = SHAM_TEMPLATE if sham else ACTIVE_TEMPLATE
    return template.format(**values) + WASHOUT_SUFFIX, assigned


def render_donor_prompt(row: Mapping[str, Any], s: str, sham: bool, a: int, h: int) -> tuple[str, dict[str, Any]]:
    """Render by four equivalent hidden constructor routes.

    A/H select implementation routes only. They cannot alter visible bytes.
    """
    canonical, assigned = _semantic_body(row, s, sham)
    # Route A=0 uses the canonical format result directly.
    if a == 0:
        candidate = canonical
    else:
        # Route A=1 rebuilds through line chunks.
        base = canonical.removesuffix(WASHOUT_SUFFIX)
        candidate = "".join(base.splitlines(keepends=True)) + WASHOUT_SUFFIX
    if h == 0:
        out = candidate
    else:
        # H=1 round-trips exact UTF-8 to a new object; no visible chronology bit survives.
        out = candidate.encode("utf-8").decode("utf-8")
    if out != canonical:
        raise BuilderViolation("hidden A/H constructor path changed donor-visible bytes")
    return out, assigned


def _lex_bag(text: str) -> list[str]:
    return sorted(re.findall(r"\w+|[^\w\s]", text.lower(), flags=re.UNICODE))


def opaque_endpoints(assigned: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    # Endpoint IDs are fixed by command lexical order, not semantic p/q identity.
    commands = sorted([str(assigned["command_a"]), str(assigned["command_b"])])
    if commands[0] == commands[1]:
        raise BuilderViolation("divergent commands must differ")
    endpoints = {"e0": commands[0], "e1": commands[1]}
    p_cmd, q_cmd = str(assigned["command_a"]), str(assigned["command_b"])
    orientation = {
        eid: ("p" if cmd == p_cmd else "q" if cmd == q_cmd else "")
        for eid, cmd in endpoints.items()
    }
    if sorted(orientation.values()) != ["p", "q"]:
        raise BuilderViolation("opaque endpoint orientation failed")
    return endpoints, orientation


def audit_candidates(output_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if TRAIN_ROOT.name != "train" or "valid_" in TRAIN_ROOT.as_posix():
        raise BuilderViolation("PlanLatch v7.9 builder requires exact TRAIN root")
    exclusion = exclusion_snapshot(output_dir)
    referenced = set(exclusion["referenced_families"])
    families = sorted(p for p in TRAIN_ROOT.glob("pick_two_obj_and_place-*") if p.is_dir())
    fresh = [p for p in families if p.name not in referenced]
    rows = []
    for i, family in enumerate(fresh, 1):
        try:
            row = audit_family(family)
        except Exception as exc:
            row = {"family": family.name, "eligible": False, "reason": "EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}
        rows.append(row)
        if i % 25 == 0:
            print(stable_json({"stage": "environment_audit", "attempted": i, "eligible": sum(bool(x.get("eligible")) for x in rows)}), flush=True)
    return exclusion, rows


def choose_cohort(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    eligible = [dict(r) for r in rows if r.get("eligible") is True]
    eligible.sort(key=lambda r: sha_text(f'{COHORT_SALT}|{r["family"]}|{r["trial"]}|{r["reset_state_hash"]}'))
    if len(eligible) < TARGET_B:
        raise BuilderViolation(f"need {TARGET_B} eligible fresh TRAIN families, got {len(eligible)}")
    return eligible[:TARGET_B]


def task_metadata(selected: Sequence[Mapping[str, Any]]) -> tuple[list[core.BaseTaskMetadata], dict[str, dict[str, Any]]]:
    tasks = []
    by_task: dict[str, dict[str, Any]] = {}
    for row in selected:
        m0, bit = m0_for(row)
        task_id = f'planlatch-v79-train::{row["family"]}::{row["trial"]}'
        seed = f'{PROVENANCE_SALT}|{task_id}|{row["reset_state_hash"]}'
        dep = {"base_task_identity": task_id}
        for key in core.DEPENDENCY_KEY_TYPES:
            if key == "base_task_identity":
                continue
            dep[key] = f'{key}-' + sha_text(f"{seed}|{key}")[:20]
        tag = "xr-" + sha_text(f'{row["game_path"]}|{row["reset_state_hash"]}')[:20]
        task = core.BaseTaskMetadata(task_id, m0, dep, tag, "train", True)
        tasks.append(task)
        by_task[task_id] = {**dict(row), "m0": m0, "orientation_bit": bit}
    return tasks, by_task


def validate_prompt_program(frame: core.FrameFreeze, by_task: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str, bool], list[tuple[int, int, str]]] = {}
    semantic_pairs: dict[tuple[str, bool], dict[str, str]] = {}
    for cell in frame.cells:
        prompt, _ = render_donor_prompt(by_task[cell.task_id], cell.s, cell.sham, cell.a, cell.h)
        groups.setdefault((cell.task_id, cell.s, cell.sham), []).append((cell.a, cell.h, prompt))
        semantic_pairs.setdefault((cell.task_id, cell.sham), {})[cell.s] = prompt
        # Hidden labels must not be serialized literally as metadata.
        for forbidden in (f"A={cell.a}", f"H={cell.h}", cell.m0):
            if forbidden in prompt:
                raise BuilderViolation(f"hidden constructor metadata leaked into donor prompt: {forbidden}")
    for key, rows in groups.items():
        if len({p for _, _, p in rows}) != 1:
            raise BuilderViolation(f"A/H byte identity failed: {key}")
    for key, pair in semantic_pairs.items():
        if set(pair) != {"p", "q"}:
            raise BuilderViolation("missing p/q prompt pair")
        if _lex_bag(pair["p"]) != _lex_bag(pair["q"]):
            raise BuilderViolation(f"p/q lexical multiset mismatch: {key}")
    return {
        "a_h_byte_identity": True,
        "p_q_lexical_multiset_equal": True,
        "hidden_metadata_absent": True,
        "checked_cells": len(frame.cells),
    }


def _write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    return sha_file(path)


def materialize(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise BuilderViolation(f"output directory must be fresh: {output_dir}")
    exclusion, audit_rows = audit_candidates(output_dir)
    selected = choose_cohort(audit_rows)
    referenced = set(exclusion["referenced_families"])
    if referenced.intersection(r["family"] for r in selected):
        raise BuilderViolation("fresh cohort intersects prior referenced families")

    tasks, by_task = task_metadata(selected)
    frame = core.compile_pre_response_frame(tasks)
    core.verify_complete_cells(frame)
    if len(frame.block_ids) != 36 or len(frame.cells) != 36 * 16:
        raise BuilderViolation("reviewed frame did not produce exact 36×16 schedule")
    partition_counts = {name: sum(1 for b in frame.block_ids if frame.partition_by_block[b] == name) for name in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION")}
    if partition_counts != {"FIT":12,"PILOT":8,"SUPPORT":12,"CROSS_REALIZATION":4}:
        raise BuilderViolation(f"partition counts mismatch: {partition_counts}")
    prompt_audit = validate_prompt_program(frame, by_task)

    output_dir.mkdir(parents=True)
    partition_rows: dict[str, list[dict[str, Any]]] = {k: [] for k in ("FIT","PILOT","SUPPORT","CROSS_REALIZATION")}
    orientations: dict[str, dict[str, dict[str, str]]] = {"PILOT": {}, "CROSS_REALIZATION": {}}
    for cell in frame.cells:
        rowmeta = by_task[cell.task_id]
        prompt, assigned = render_donor_prompt(rowmeta, cell.s, cell.sham, cell.a, cell.h)
        endpoints, orientation = opaque_endpoints(assigned)
        visible = reset_block(rowmeta)
        if "ACTIVE ORDER:" in visible or "ARCHIVED ORDER:" in visible:
            raise BuilderViolation("relay/actuator visible context leaks semantic order")
        rec: dict[str, Any] = {
            "cell_id": cell.cell_id,
            "task_id": cell.task_id,
            "donor_prompt": prompt,
        }
        if cell.partition == "FIT":
            rec.update({
                "actuator_visible_context": visible,
                "actuator_endpoints": endpoints,
                "actuator_orientation": orientation,
            })
        if cell.partition in ("PILOT", "CROSS_REALIZATION"):
            rec.update({
                "relay_visible_context": visible,
                "relay_endpoints": endpoints,
                "valid_endpoint_ids": sorted(endpoints),
            })
            orientations[cell.partition][cell.cell_id] = orientation
        partition_rows[cell.partition].append(rec)

    partition_refs = {}
    for name in ("FIT","SUPPORT","PILOT","CROSS_REALIZATION"):
        path = output_dir / f"{name}.json"
        digest = _write_json(path, {"partition": name, "records": partition_rows[name]})
        partition_refs[name] = {"path": path.as_posix(), "sha256": digest}
    orientation_refs = {}
    for name in ("PILOT","CROSS_REALIZATION"):
        path = output_dir / f"{name}_orientation.json"
        digest = _write_json(path, {"partition": name, "orientations": orientations[name]})
        orientation_refs[name] = {"path": path.as_posix(), "sha256": digest}

    selected_family_names = [r["family"] for r in selected]
    selected_summary = []
    for row in selected:
        assigned = option_assignment(row)
        task_id = f'planlatch-v79-train::{row["family"]}::{row["trial"]}'
        selected_summary.append({
            "task_id": task_id,
            "family": row["family"],
            "trial": row["trial"],
            "game_path": row["game_path"],
            "game_sha256": row["game_sha256"],
            "reset_state_hash": row["reset_state_hash"],
            "reset_observation_sha256": row["reset_observation_sha256"],
            "reset_admissible_commands_sha256": row["reset_admissible_commands_sha256"],
            "branch_a_won": row["branch_a_won"],
            "branch_b_won": row["branch_b_won"],
            "delayed_divergence": row["delayed_divergence"],
            "m0": assigned["m0"],
            "orientation_bit": assigned["orientation_bit"],
            "option_a_object": assigned["option_a"]["object"],
            "option_b_object": assigned["option_b"]["object"],
            "p_command": assigned["command_a"],
            "q_command": assigned["command_b"],
        })
    cohort = {
        "kind": "PLANLATCH_V79_FRESH_TRAIN_COHORT_PRE_SCIENCE_V1",
        "scientific_result": "NOT_ASSESSED",
        "experiment_id": EXPERIMENT_ID,
        "design_id": DESIGN_ID,
        "semantic_hash": SEMANTIC_HASH,
        "source_split": "train",
        "train_root": TRAIN_ROOT.as_posix(),
        "trial_salt": TRIAL_SALT,
        "cohort_salt": COHORT_SALT,
        "m0_salt": M0_SALT,
        "selected_count": len(selected),
        "selected_families": selected_family_names,
        "selected_family_set_hash": sha_json(selected_family_names),
        "exclusion_snapshot_hash": exclusion["snapshot_hash"],
        "excluded_referenced_family_set_hash": exclusion["referenced_family_set_hash"],
        "excluded_referenced_family_count": len(exclusion["referenced_families"]),
        "scanned_prior_artifact_count": exclusion["file_count"],
        "fresh_candidate_count": len(audit_rows),
        "fresh_eligible_count": sum(r.get("eligible") is True for r in audit_rows),
        "selection_happened_after_eligibility_audit": True,
        "no_replacement_after_selection": True,
        "environment_only": True,
        "model_calls": 0,
        "tokenizer_loads": 0,
        "selected": selected_summary,
        "frame": {
            "frame_hash": frame.frame_hash,
            "dependency_hash": frame.dependency_hash,
            "block_ids": list(frame.block_ids),
            "partition_by_block": dict(frame.partition_by_block),
            "partition_counts": partition_counts,
            "cell_count": len(frame.cells),
        },
        "prompt_program": {
            **DONOR_PROGRAM_DESCRIPTOR,
            "donor_program_hash": DONOR_PROGRAM_HASH,
            "washout_literal": WASHOUT_SUFFIX,
            "washout_sha256": WASHOUT_HASH,
            "prompt_audit": prompt_audit,
        },
        "partition_hashes": {k:v["sha256"] for k,v in partition_refs.items()},
        "orientation_sidecar_hashes": {k:v["sha256"] for k,v in orientation_refs.items()},
    }
    cohort_sha = _write_json(output_dir / "cohort_manifest.json", cohort)

    task_rows = [{
        "task_id": t.task_id,
        "m0": t.m0,
        "dependency_keys": dict(t.dependency_keys),
        "cross_realization_tag": t.cross_realization_tag,
        "split": t.split,
        "never_consumed": t.never_consumed,
    } for t in tasks]
    freshness = {
        "all_task_ids_never_consumed": True,
        "method": "family name absent from every pre-existing results/design and results/science text artifact at freeze time",
        "excluded_family_set_hash": exclusion["referenced_family_set_hash"],
        "exclusion_snapshot_hash": exclusion["snapshot_hash"],
        "selected_family_set_hash": sha_json(selected_family_names),
        "selected_intersection_with_excluded": [],
        "source_split": "train",
        "environment_audit_only_before_freeze": True,
        "model_calls_before_freeze": 0,
    }
    root = {
        "kind": KIND,
        "experiment_id": EXPERIMENT_ID,
        "tasks": task_rows,
        "partition_files": partition_refs,
        "orientation_files": orientation_refs,
        "freshness_attestation": freshness,
        "donor_program_hash": DONOR_PROGRAM_HASH,
        "washout_hash": WASHOUT_HASH,
        "cohort_manifest": {"path": (output_dir / "cohort_manifest.json").as_posix(), "sha256": cohort_sha},
    }
    root_sha = _write_json(output_dir / "root.json", root)

    # Re-open through reviewed driver and prove exact frame/partition coverage.
    loaded = driver.load_root_input(output_dir / "root.json")
    reframe = core.compile_pre_response_frame(loaded.tasks)
    core.verify_complete_cells(reframe)
    if reframe.frame_hash != frame.frame_hash or reframe.dependency_hash != frame.dependency_hash:
        raise BuilderViolation("reviewed driver/frame round-trip mismatch")
    for name in ("FIT","SUPPORT","PILOT","CROSS_REALIZATION"):
        records = driver._partition_records(loaded.partition_files[name], name)
        driver._verify_partition_coverage(reframe, name, records)
    for name in ("PILOT","CROSS_REALIZATION"):
        rows = driver._orientation_rows(loaded.orientation_files[name], name)
        expected_ids = {c.cell_id for c in reframe.cells if c.partition == name and not c.sham}
        # Sidecars intentionally include sham too because raw arm scores later skip sham;
        # exact partition cell coverage is safer and still sealed from score production.
        if set(rows) != {c.cell_id for c in reframe.cells if c.partition == name}:
            raise BuilderViolation(f"orientation sidecar coverage mismatch: {name}")

    result = {
        "kind": "PLANLATCH_V79_TRAIN_INPUT_MATERIALIZATION_NOT_SCIENTIFIC_EVIDENCE",
        "scientific_result": "NOT_ASSESSED",
        "output_dir": output_dir.as_posix(),
        "root_sha256": root_sha,
        "cohort_manifest_sha256": cohort_sha,
        "selected_count": 36,
        "fresh_eligible_count": cohort["fresh_eligible_count"],
        "prior_referenced_family_count": cohort["excluded_referenced_family_count"],
        "frame_hash": frame.frame_hash,
        "dependency_hash": frame.dependency_hash,
        "partition_counts": partition_counts,
        "cell_count": len(frame.cells),
        "donor_program_hash": DONOR_PROGRAM_HASH,
        "washout_hash": WASHOUT_HASH,
        "a_h_byte_identity": prompt_audit["a_h_byte_identity"],
        "p_q_lexical_multiset_equal": prompt_audit["p_q_lexical_multiset_equal"],
        "model_calls": 0,
        "tokenizer_loads": 0,
        "scientific_execution_performed": False,
    }
    _write_json(output_dir / "materialization_summary.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default=str(OUTPUT_DIR_DEFAULT))
    args = p.parse_args(argv)
    out = Path(args.output_dir)
    result = materialize(out)
    print(stable_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
