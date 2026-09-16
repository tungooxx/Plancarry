#!/usr/bin/env python3
from __future__ import annotations
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from whitebox_bridge import BridgeApplication, MockBackend, make_server
from whitebox_client import WhiteboxClient

TOKEN = "unit-test-token"
backend = MockBackend()
app = BridgeApplication(backend, TOKEN)
server = make_server(app, "127.0.0.1", 0)
port = server.server_address[1]
thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
thread.start()
base = f"http://127.0.0.1:{port}"
checks = {}
try:
    # Unauthenticated request must fail.
    try:
        urllib.request.urlopen(base + "/health", timeout=2)
        checks["unauthenticated_rejected"] = False
    except urllib.error.HTTPError as exc:
        checks["unauthenticated_rejected"] = (exc.code == 401)

    cli = WhiteboxClient(base, TOKEN, timeout=2)
    health = cli.health(); checks["auth_health"] = bool(health["ok"])
    info = cli.model_info(); checks["model_info"] = info["mode"] == "mock"
    score = cli.score_sequences("state", [" action a", " action b"])
    checks["score_sequences"] = len(score["scores"]) == 2
    cap = cli.capture("active plan", 2, -1)
    vec = cap["vector"]
    checks["capture"] = len(vec) == backend.hidden_size
    patched = cli.patch_score("state", [" action a", " action b"], 2, vec, -1, "add", 0.5)
    checks["patch_score"] = len(patched["scores"]) == 2 and patched["backend"] == "mock" and len(patched["patch_vector_sha256"]) == 64

    # Invalid vector dimension and excessive scale must fail closed.
    try:
        cli.patch_score("state", [" action a"], 2, [0.1, 0.2], -1, "add", 1.0)
        checks["vector_dim_rejected"] = False
    except RuntimeError:
        checks["vector_dim_rejected"] = True
    try:
        cli.patch_score("state", [" action a"], 2, vec, -1, "add", 100.0)
        checks["scale_bound_rejected"] = False
    except RuntimeError:
        checks["scale_bound_rejected"] = True

    # Unknown endpoint must be rejected and there is no execution endpoint.
    req = urllib.request.Request(base + "/exec", method="POST", data=b"{}", headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=2)
        checks["no_arbitrary_exec"] = False
    except urllib.error.HTTPError as exc:
        checks["no_arbitrary_exec"] = (exc.code == 404)

    result = {
        "kind": "WHITEBOX_BRIDGE_MOCK_PROTOCOL_TEST",
        "scientific_result": "NOT_ASSESSED",
        "model_inference_executed": False,
        "gpu_model_workload_executed": False,
        "valid_seen_consumed": False,
        "valid_unseen_consumed": False,
        "checks": checks,
        "pass": all(checks.values()),
        "health_mode": health["mode"],
        "api_version": health["api_version"],
    }
    Path("results/engineering").mkdir(parents=True, exist_ok=True)
    Path("results/engineering/whitebox_bridge_mock_test.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["pass"] else 1)
finally:
    server.shutdown(); server.server_close(); thread.join(timeout=2)
