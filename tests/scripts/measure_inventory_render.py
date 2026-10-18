#!/usr/bin/env python3
"""Measure the actual committed inventory render on Linux/proc, including this monitor.

python3 tests/scripts/measure_inventory_render.py --ref HEAD --max-rss-mib 512 --max-seconds 60
Only lower limits are permitted. The private run_bounded interface also exercises actual harmless
allocation/process-group controls; it is not an alternate renderer or a public worker command.
"""
from __future__ import annotations

import time
STARTED = time.monotonic()
import argparse
import ctypes
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELF = "tests/scripts/measure_inventory_render.py"
GATE = "scripts/gate/spec_gate.py"
MAX_RSS = 512 * 1024 * 1024
MAX_SECONDS = 60.0
PROC = pathlib.Path("/proc")


def gaps(values: list[float]) -> dict:
    return {"count": len(values), "min": min(values) if values else None,
            "median": statistics.median(values) if values else None, "max": max(values) if values else None}


def rss(pid: int) -> int:
    return int((PROC / str(pid) / "statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def group_members(group: int) -> set[int]:
    members = set()
    for item in PROC.iterdir():
        if not item.name.isdecimal():
            continue
        try:
            if os.getpgid(int(item.name)) == group:
                members.add(int(item.name))
        except ProcessLookupError:
            pass
    return members


def run_bounded(argv: list[str], cwd: pathlib.Path, *, max_rss_bytes: int, max_seconds: float) -> dict:
    """Own, observe and synchronously reap one process group. All limits include the monitor.

    Discovery is independent of RSS sampling. Actual gaps are reported; neither short-lived
    undiscovered workers nor unsampled instantaneous aggregate peaks are claimed to be known.
    """
    started = time.monotonic()
    if (isinstance(max_rss_bytes, bool) or not isinstance(max_rss_bytes, int) or not 0 < max_rss_bytes <= MAX_RSS
            or isinstance(max_seconds, bool) or not math.isfinite(max_seconds) or not 0 < max_seconds <= MAX_SECONDS):
        raise ValueError("limits must be finite, positive and no greater than 512 MiB/60 seconds")
    report = {"ok": False, "reason": "observation_failure", "argv": argv, "cwd": str(cwd),
              "max_rss_bytes": max_rss_bytes, "max_seconds": max_seconds, "peak_rss_bytes": 0,
              "monitor_rss_bytes": 0, "peak_snapshot": {}, "sample_count": 0, "owned_group_gone": False}
    process = None
    stop = threading.Event()
    lock = threading.Lock()
    known: set[int] = set()
    discovered: set[int] = set()
    discovery_gaps: list[float] = []
    sample_gaps: list[float] = []
    discovery_errors: list[str] = []
    observer = None
    libc = None
    old_subreaper = ctypes.c_int()
    try:
        # Scope adopted grandchildren to this single owned group; never wait for unrelated children.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(37, ctypes.byref(old_subreaper), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), "cannot own adopted descendants")
        report["monitor_rss_bytes"] = rss(os.getpid())
        if report["monitor_rss_bytes"] > max_rss_bytes:
            report.update(reason="rss_limit", peak_rss_bytes=report["monitor_rss_bytes"])
            return report
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)
            group = process.pid
            known.add(group)
            discovered.add(group)
            report["process_group"] = group

            def discover() -> None:
                last = time.monotonic()
                while not stop.is_set():
                    try:
                        members = group_members(group)
                        now = time.monotonic()
                        with lock:
                            known.update(members)
                            discovered.update(members)
                            discovery_gaps.append(now - last)
                        last = now
                    except Exception as e:
                        discovery_errors.append(f"{type(e).__name__}: {e}")
                        return
                    stop.wait(.05)

            observer = threading.Thread(target=discover, name="inventory-rss-discovery")
            observer.start()
            last = time.monotonic()
            # Reserve terminal/reaping time inside the public deadline, including short refusal controls.
            work_deadline = started + max_seconds - min(.5, max_seconds * .25)
            while True:
                now = time.monotonic()
                sample_gaps.append(now - last)
                last = now
                with lock:
                    pids = set(known)
                sample = {os.getpid(): rss(os.getpid())}
                for pid in pids:
                    try:
                        sample[pid] = rss(pid)
                    except FileNotFoundError:
                        pass  # process already exited; retained discovery identity is reported
                total = sum(sample.values())
                report["sample_count"] += 1
                report["monitor_rss_bytes"] = max(report["monitor_rss_bytes"], sample[os.getpid()])
                if total > report["peak_rss_bytes"]:
                    report.update(peak_rss_bytes=total, peak_snapshot=sample)
                if total > max_rss_bytes:
                    report["reason"] = "rss_limit"
                    break
                if discovery_errors:
                    raise OSError(discovery_errors[0])
                if now >= work_deadline:
                    report["reason"] = "time_limit"
                    break
                if process.poll() is not None:
                    report["reason"] = "completed" if process.returncode == 0 else "worker_failed"
                    break
                stop.wait(.005)
            stop.set()
            observer.join(timeout=.2)
            if observer.is_alive():
                raise OSError("discovery thread did not stop")
            remaining = group_members(group)
            if process.poll() is not None and remaining and report["reason"] == "completed":
                report["reason"] = "unexpected_descendants"
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=max(.05, started + max_seconds - time.monotonic()))
            # A dying grandchild becomes ours via subreaper; reap only this group's descendants.
            until = started + max_seconds
            while True:
                try:
                    while os.waitpid(-group, os.WNOHANG)[0]:
                        pass
                except ChildProcessError:
                    pass
                if not group_members(group):
                    report["owned_group_gone"] = True
                    break
                if time.monotonic() >= until:
                    raise OSError("owned group not reaped before deadline")
                time.sleep(.002)
            report["worker_exit"] = process.returncode
            for name, stream in (("stdout", stdout), ("stderr", stderr)):
                stream.seek(0)
                raw = stream.read(65537)
                report[name] = raw[:65536].decode("utf-8", "replace")
                if len(raw) > 65536:
                    report["reason"] = "output_limit"
            report["kernel_child_peak_bytes"] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
            if report["kernel_child_peak_bytes"] > max_rss_bytes:
                report["reason"] = "rss_limit"
            report["ok"] = report["reason"] == "completed" and report["owned_group_gone"]
    except Exception as e:
        report.update(ok=False, reason="observation_failure", error=f"{type(e).__name__}: {e}")
    finally:
        stop.set()
        if observer is not None:
            observer.join(timeout=.2)
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Error-unwind must reap synchronously even if the advertised bound was exceeded; never admit it.
            try:
                process.wait(timeout=1)
                end = time.monotonic() + .5
                while True:
                    try:
                        while os.waitpid(-process.pid, os.WNOHANG)[0]:
                            pass
                    except ChildProcessError:
                        pass
                    if not group_members(process.pid):
                        report["owned_group_gone"] = True
                        break
                    if time.monotonic() >= end:
                        raise OSError("owned descendant cleanup failed")
                    time.sleep(.002)
            except Exception as e:
                report.update(ok=False, reason="cleanup_failure", cleanup_error=str(e))
        if libc is not None:
            libc.prctl(36, old_subreaper.value, 0, 0, 0)
        report["elapsed_seconds"] = time.monotonic() - started
        report["sample_gap_seconds"] = gaps(sample_gaps)
        report["discovery_gap_seconds"] = gaps(discovery_gaps)
        report["discovered_pids"] = sorted(discovered)
        report["observation_limits"] = "sampled aggregate only; discovery/sample gaps may hide transient peaks"
        if report["elapsed_seconds"] > max_seconds:
            report.update(ok=False, reason="time_limit" if report["reason"] == "completed" else report["reason"])
    return report


def git(*args: str, data: bytes | None = None) -> bytes:
    r = subprocess.run(["git", *args], cwd=ROOT, input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git {args[0]} failed ({r.returncode}): {r.stderr.decode('utf-8', 'replace')[:1000]}")
    return r.stdout


def worker(ref: str) -> int:
    """All preflight, source reads and materialization run inside the observed owned group."""
    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    tree = git("rev-parse", f"{commit}^{{tree}}").decode().strip()
    spec = importlib.util.spec_from_file_location("inventory_gate", ROOT / GATE)
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    # Validate gate bytes before executing it; all imports from the trusted checkout are then pinned below.
    gate_bytes = git("show", f"{commit}:{GATE}")
    if (ROOT / GATE).is_symlink() or (ROOT / GATE).read_bytes() != gate_bytes:
        raise ValueError(f"trusted input differs from committed ref: {GATE}")
    spec.loader.exec_module(gate)
    entries = gate.head_entries(commit)
    if reason := gate.tree_refusal(entries):
        raise ValueError(reason)
    indexed = {p: (mode, oid) for mode, oid, p in entries}
    identities = {}
    for path in dict.fromkeys((SELF, GATE, *gate.RENDER_INPUTS)):
        local = ROOT / path
        if path not in indexed:
            if local.exists() or local.is_symlink():
                raise ValueError(f"trusted input differs from committed ref: {path}")
            identities[path] = None
            continue
        mode, oid = indexed[path]
        raw = git("cat-file", "blob", oid)
        expected_executable = mode == "100755"
        if (not local.is_file() or local.is_symlink() or local.read_bytes() != raw
                or bool(local.stat().st_mode & 0o100) != expected_executable):
            raise ValueError(f"trusted input differs from committed ref: {path}")
        identities[path] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "mode": mode}
    sizes = git("cat-file", "--batch-check=%(objectsize)", data=b"".join(oid.encode() + b"\n" for _, oid, _ in entries))
    source_bytes = sum(int(v) for v in sizes.splitlines())
    if len(sizes.splitlines()) != len(entries):
        raise ValueError("committed blob size enumeration is incomplete")
    base = gate.Tree(commit)
    docs = list(gate.GENERATED_DOCS)
    if any(base.raw(doc) is None for doc in docs):
        raise ValueError("committed generated document is missing")
    actual = {}
    refused = gate.render_refusals(entries, docs, {doc: base.raw(doc) for doc in docs}, evidence=actual)
    print(json.dumps({"ref": commit, "tree": tree, "repo": str(ROOT), "source_entries": len(entries),
                      "source_bytes": source_bytes, "trusted_inputs": identities, "renderer_exit": actual.get("exit"),
                      "renderer_argv": actual.get("argv"), "renderer_cwd": actual.get("cwd"), "refusals": refused}))
    return 1 if refused else 0


def lower_limit(value: str, ceiling: float) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= ceiling:
        raise argparse.ArgumentTypeError(f"limit must be finite and within (0, {ceiling}]")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--max-rss-mib", type=lambda s: lower_limit(s, 512), default=512)
    parser.add_argument("--max-seconds", type=lambda s: lower_limit(s, 60), default=60)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    remaining = args.max_seconds - (time.monotonic() - STARTED)
    if remaining <= 0:
        report = {"ok": False, "reason": "time_limit"}
    else:
        report = run_bounded([sys.executable, "-I", "-B", str(pathlib.Path(__file__).resolve()), "--worker", args.ref],
                             ROOT, max_rss_bytes=int(args.max_rss_mib * 1024 * 1024), max_seconds=remaining)
    report.update(kind="committed-inventory-render", command_limit_seconds=args.max_seconds,
                  whole_command_elapsed_seconds=time.monotonic() - STARTED)
    if report.get("stdout"):
        try:
            report["worker"] = json.loads(report["stdout"])
            if report.get("ok") and report["worker"]["renderer_exit"] != 0:
                raise ValueError("renderer did not accept committed documents")
        except (ValueError, KeyError) as e:
            report.update(ok=False, reason="invalid_worker_result", error=str(e))
    elif report.get("ok"):
        report.update(ok=False, reason="invalid_worker_result", error="worker produced no verdict")
    if report["whole_command_elapsed_seconds"] > args.max_seconds:
        report.update(ok=False, reason="time_limit")
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        try:
            raise SystemExit(worker(sys.argv[2]))
        except Exception as e:
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            raise SystemExit(1)
    raise SystemExit(main())
