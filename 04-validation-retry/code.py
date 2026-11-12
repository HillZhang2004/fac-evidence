"""Offline retry-consistency research screen; unmodified fac source, synthetic data.

AI-assisted experimental code. This is not a new execution or validation framework.
Run using an existing Python 3.12 environment with fac's pinned dependencies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

import jsonschema
import yaml

HERE = Path(__file__).resolve().parent
SPRINT = HERE.parent
PROJECT = SPRINT.parent.parent
PINS = {"master": "2a099e6e97db390fa578a33edf9f66d61aec5818",
        "fac-tests": "a1e597a95662c764507b7c58b10bf20a7fdbec89"}


def dump(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def source_hashes(folder):
    return {str(p.relative_to(folder)): sha(p.read_bytes())
            for p in sorted(folder.rglob("*")) if p.is_file()}


def prepare_source(name):
    destination = HERE / "vendor" / name
    manifest_path = destination.parent / f"{name}-manifest.json"
    if not destination.exists():
        destination.mkdir(parents=True)
        if name == "master":
            result = subprocess.run(["git", "archive", PINS[name]],
                                    cwd="<ORIGINAL_LOCAL_FAC>", capture_output=True, check=True)
            with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
                archive.extractall(destination, filter="data")
            origin = "read-only git archive from original local clone"
        else:
            old = PROJECT / "fac-diagnostics/handoff-review-2026-11-04"
            manifest = json.loads((old / "fac-tests-source-manifest.json").read_text())
            assert manifest["commit"] == PINS[name]
            for relative, digest in manifest["files_sha256"].items():
                source = old / "fac-tests-source" / relative
                assert sha(source.read_bytes()) == digest, relative
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            origin = "read-only copy of previously Git-blob-audited export; SHA256 checked"
        dump(manifest_path, {"commit": PINS[name], "origin": origin,
                             "files_sha256": source_hashes(destination)})
    manifest = json.loads(manifest_path.read_text())
    assert manifest["commit"] == PINS[name]
    assert source_hashes(destination) == manifest["files_sha256"]
    return destination


PRODUCER = '''from pathlib import Path
with Path("producer.calls").open("a") as f: f.write("generated\\n")
Path("record.json").write_text('{"count": 1}\\n')
'''

GATE = '''from pathlib import Path
import json
import jsonschema
schema = json.loads(Path("schema.json").read_text())
data = json.loads(Path("record.json").read_text())
jsonschema.validate(data, schema)
Path("validated.txt").write_text("validated\\n")
'''

GUARD = '''from pathlib import Path
import socket
def blocked(*args, **kwargs):
    with Path("network-blocks.jsonl").open("a") as f:
        f.write('{"event":"blocked"}\\n')
    raise RuntimeError("This offline experiment denies network access")
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked
'''

SCHEMAS = {
    "valid": {"type": "object", "required": ["count"],
              "properties": {"count": {"type": "integer"}}},
    "invalid-type": {"type": "not_a_json_schema_type"},
    "unresolved-local-ref": {"$ref": "#/definitions/not_present"},
    "invalid-utf8": {"type": "object", "required": ["count"],
                     "properties": {"count": {"type": "integer"}}},
}


def independent_acceptance(work):
    result = {"accepted": False, "schema_well_formed": None,
              "producer_exists": (work / "record.json").exists(),
              "consumer_exists": (work / "consumer.txt").exists()}
    try:
        schema = json.loads((work / "schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        result["schema_well_formed"] = True
        producer = json.loads((work / "record.json").read_text())
        # Separate validation of actual saved producer and consumer bytes.
        jsonschema.validate(producer, schema)
        if (work / "consumer.txt").exists():
            consumer = json.loads((work / "consumer.txt").read_text())
            jsonschema.validate(consumer, schema)
            result["accepted"] = producer == consumer == {"count": 1}
    except Exception as error:
        result["error_type"] = type(error).__name__
        if isinstance(error, jsonschema.SchemaError):
            result["schema_well_formed"] = False
    return result


def snapshot(work):
    keep = ["record.json", "consumer.txt", "validated.txt", "producer.calls",
            ".record.json.facjson", ".consumer.txt.facjson", ".validated.txt.facjson",
            ".record.json.buildlog", ".consumer.txt.buildlog", ".buildlog"]
    return {name: {"sha256": sha((work/name).read_bytes()),
                   "bytes": (work/name).stat().st_size,
                   "text": (work/name).read_text(errors="replace")}
            for name in keep if (work/name).is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", choices=PINS, required=True)
    parser.add_argument("--case", choices=SCHEMAS, required=True)
    parser.add_argument("--policy", choices=["native", "validation-dependency"], default="native")
    args = parser.parse_args()
    source = prepare_source(args.revision)
    source_before = source_hashes(source)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    run = HERE / "a-runs" / f"{run_id}-{args.revision}-{args.case}-{args.policy}"
    work = run / "work"
    work.mkdir(parents=True)
    (work / ".tmp").mkdir()
    guard = run / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD)
    producer = PRODUCER
    if args.case == "invalid-utf8":
        producer = PRODUCER.replace("Path(\"record.json\").write_text('{\"count\": 1}\\n')",
                                    "Path(\"record.json\").write_bytes(bytes([255, 10]))")
        assert "write_bytes" in producer
    (work / "produce.py").write_text(producer)
    (work / "gate.py").write_text(GATE)
    dump(work / "schema.json", SCHEMAS[args.case])
    py = shlex.quote(sys.executable)
    cfg = {"record.json": {"cmd": f"{py} -B produce.py", "schema_file": "schema.json"}}
    if args.policy == "validation-dependency":
        cfg["schema.json"] = {}  # Existing source-only target, required by fac's configuration contract.
        cfg["validated.txt"] = {"cmd": f"{py} -B gate.py",
                                "dependencies": ["record.json", "schema.json"]}
    cfg["consumer.txt"] = {
        "cmd": f"{py} -B -c " + shlex.quote(
            "from pathlib import Path; Path('consumer.txt').write_bytes(Path('record.json').read_bytes())"),
        "dependencies": ["validated.txt"] if args.policy == "validation-dependency" else ["record.json"],
    }
    (work / "fac.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    env = {"PATH": os.environ.get("PATH", os.defpath),
           "PYTHONPATH": os.pathsep.join([str(guard), str(source)]),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
           "TMPDIR": str(work/".tmp"), "TZ": "UTC", "LC_ALL": "C"}
    subprocess.run(["git", "-c", "init.templateDir=", "init", "-q"], cwd=work,
                   env=env, check=True, capture_output=True)
    origin = subprocess.run([sys.executable, "-B", "-c",
        "import importlib.util; print(importlib.util.find_spec('fac.__main__').origin)"],
        cwd=work, env=env, capture_output=True, text=True, check=True)
    assert Path(origin.stdout.strip()).resolve() == source / "fac/__main__.py"
    command = [sys.executable, "-B", "-m", "fac", "--no-auto_commit", "--max_workers", "1",
               "--debug.halt_on_error", "--print_context_states", "consumer.txt"]
    dump(run / "protocol.json", {"revision": args.revision, "commit": PINS[args.revision],
        "case": args.case, "policy": args.policy, "argv": command, "cwd": str(work),
        "environment": env, "source_origin": origin.stdout.strip(),
        "runner_sha256": sha(Path(__file__).read_bytes()),
        "synthetic_fixture": True, "provider_calls": 0, "python": sys.version})
    observations = []
    for attempt in [1, 2]:
        started = time.monotonic()
        result = subprocess.run(command, cwd=work, env=env,
                                capture_output=True, timeout=60)
        duration = time.monotonic()-started
        target = run / f"attempt-{attempt}"
        target.mkdir()
        (target / "stdout.txt").write_bytes(result.stdout)
        (target / "stderr.txt").write_bytes(result.stderr)
        (target / "returncode.txt").write_text(str(result.returncode)+"\n")
        independent = independent_acceptance(work)
        saved = snapshot(work)
        dump(target / "snapshot.json", saved)
        try: states = json.loads(result.stdout)
        except ValueError: states = None
        row = {"attempt": attempt, "returncode": result.returncode,
               "wall_seconds": duration, "states": states,
               "independent": independent,
               "producer_calls": len((work/"producer.calls").read_text().splitlines())
                   if (work/"producer.calls").exists() else 0,
               "metadata_exists": (work/".record.json.facjson").exists(),
               "validation_marker_exists": (work/"validated.txt").exists(),
               "false_acceptance_under_application_contract": result.returncode == 0 and not independent["accepted"]}
        dump(target / "observed.json", row)
        observations.append(row)
    assert source_before == source_hashes(source), "Experiment modified upstream source"
    assert not list(work.rglob("network-blocks.jsonl")), "Unexpected network attempt"
    assert not list((work/".git/refs").rglob("*")) or not any(
        p.is_file() for p in (work/".git/refs").rglob("*")), "Unexpected commit/ref"
    summary = {"run": str(run.relative_to(HERE)), "revision": args.revision,
               "commit": PINS[args.revision], "case": args.case, "policy": args.policy,
               "source_unchanged": True, "network_attempts": 0, "observations": observations}
    dump(run / "summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
