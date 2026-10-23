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
import contextlib
import ctypes
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import resource
import signal
import selectors
import stat
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


def process_table() -> dict[int, tuple[int, int]]:
    """PID -> (kernel start ticks, PPID); names may contain spaces or parentheses."""
    result = {}
    for path in PROC.iterdir():
        if not path.name.isdecimal():
            continue
        try:
            raw = (path / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            result[int(path.name)] = (int(fields[19]), int(fields[1]))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


class OwnedFamily:
    """A fresh single-threaded caller exclusively owns children created in this interval.

    Subreaper adoption retains double-fork/setsid descendants. PIDfds and kernel start ticks
    prevent a recycled PID from becoming a signal target. Existing unrelated children cause
    refusal before launching anything; no process-group membership authorizes a kill or wait.
    """
    def __init__(self):
        if threading.current_thread() is not threading.main_thread() or threading.active_count() != 1:
            raise OSError("child ownership requires an exclusive main-thread caller")
        if any(ppid == os.getpid() for _start, ppid in process_table().values()):
            raise OSError("existing children prevent exclusive descendant ownership")
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise OSError("safe descendant ownership requires Linux PIDfds")
        self.owned: dict[int, tuple[int, int]] = {}
        self.lock = threading.RLock()

    def discover(self) -> dict[int, int]:
        with self.lock:
            table = process_table()
            admitted = {pid for pid, (start, _fd) in self.owned.items() if table.get(pid, (None,))[0] == start}
            while True:
                new = {pid for pid, (_start, parent) in table.items()
                       if parent == os.getpid() or parent in admitted} - admitted
                if not new:
                    break
                for pid in new:
                    start = table[pid][0]
                    try:
                        fd = os.pidfd_open(pid)
                        # Recheck the actual kernel identity after opening its stable signal handle.
                        current = process_table().get(pid)
                        if current is None or current[0] != start:
                            os.close(fd)
                            continue
                        previous = self.owned.get(pid)
                        if previous is not None:
                            os.close(previous[1])
                        self.owned[pid] = (start, fd)
                    except ProcessLookupError:
                        continue
                admitted.update(new)
            return {pid: start for pid, (start, _fd) in self.owned.items() if table.get(pid, (None,))[0] == start}

    def snapshot(self) -> dict[int, int]:
        with self.lock:
            return {pid: start for pid, (start, _fd) in self.owned.items()}

    def sample(self) -> dict[int, int]:
        result = {os.getpid(): rss(os.getpid())}
        for pid, start in self.snapshot().items():
            try:
                raw = (PROC / str(pid) / "stat").read_text()
                if int(raw[raw.rfind(")") + 2:].split()[19]) != start:
                    continue
                value = rss(pid)
                raw = (PROC / str(pid) / "stat").read_text()
                if int(raw[raw.rfind(")") + 2:].split()[19]) == start:
                    result[pid] = value
            except (FileNotFoundError, ProcessLookupError):
                pass
        return result

    def terminate_and_reap(self, process: subprocess.Popen, deadline: float) -> None:
        while True:
            live = self.discover()
            with self.lock:
                for pid in live:
                    try:
                        signal.pidfd_send_signal(self.owned[pid][1], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            process.poll()  # retain Popen's actual root exit status before reaping adopted children
            for pid in self.snapshot():
                if pid == process.pid:
                    continue
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            if not self.discover():
                process.wait(timeout=max(.01, deadline - time.monotonic()))
                return
            if time.monotonic() >= deadline:
                raise OSError("owned descendants not reaped before cleanup deadline")
            time.sleep(.002)

    def close(self) -> None:
        with self.lock:
            for _start, fd in self.owned.values():
                os.close(fd)
            self.owned.clear()


def run_bounded(argv: list[str], cwd: pathlib.Path, *, max_rss_bytes: int, max_seconds: float) -> dict:
    """Observe/reap actual descendants, including new sessions; report sampling uncertainty honestly."""
    started = time.monotonic()
    if (isinstance(max_rss_bytes, bool) or not isinstance(max_rss_bytes, int) or not 0 < max_rss_bytes <= MAX_RSS
            or isinstance(max_seconds, bool) or not math.isfinite(max_seconds) or not 0 < max_seconds <= MAX_SECONDS):
        raise ValueError("limits must be finite, positive and no greater than 512 MiB/60 seconds")
    report = {"ok": False, "reason": "observation_failure", "argv": argv, "cwd": str(cwd),
              "max_rss_bytes": max_rss_bytes, "max_seconds": max_seconds, "peak_rss_bytes": 0,
              "monitor_rss_bytes": 0, "peak_snapshot": {}, "sample_count": 0,
              "owned_group_gone": False, "owned_family_gone": False}
    process = family = observer = libc = None
    stop = threading.Event()
    discovery_gaps: list[float] = []
    sample_gaps: list[float] = []
    errors: list[str] = []
    old_subreaper = ctypes.c_int()

    def record_sample():
        sample = family.sample() if family is not None else {os.getpid(): rss(os.getpid())}
        total = sum(sample.values())
        report["sample_count"] += 1
        report["monitor_rss_bytes"] = max(report["monitor_rss_bytes"], sample[os.getpid()])
        if total > report["peak_rss_bytes"]:
            report.update(peak_rss_bytes=total, peak_snapshot=sample)
        return total

    try:
        family = OwnedFamily()
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(37, ctypes.byref(old_subreaper), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), "cannot own adopted descendants")
        if record_sample() > max_rss_bytes:
            report["reason"] = "rss_limit"
            return report
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)
            report["process_group"] = process.pid
            family.discover()

            def discover():
                last = time.monotonic()
                while not stop.is_set():
                    try:
                        family.discover()
                        now = time.monotonic()
                        discovery_gaps.append(now - last)
                        last = now
                    except Exception as e:
                        errors.append(f"{type(e).__name__}: {e}")
                        return
                    stop.wait(.05)

            observer = threading.Thread(target=discover, name="inventory-rss-discovery")
            observer.start()
            last = time.monotonic()
            work_deadline = started + max_seconds - min(.5, max_seconds * .25)
            while True:
                now = time.monotonic()
                sample_gaps.append(now - last)
                last = now
                total = record_sample()
                if total > max_rss_bytes:
                    report["reason"] = "rss_limit"
                    break
                if errors:
                    raise OSError(errors[0])
                if now >= work_deadline:
                    report["reason"] = "time_limit"
                    break
                if process.poll() is not None:
                    # A root can exit between discovery ticks. Adopt/observe its stable escaped family BEFORE admission.
                    remaining = family.discover()
                    total = record_sample()
                    if total > max_rss_bytes:
                        report["reason"] = "rss_limit"
                    elif process.returncode != 0:
                        report["reason"] = "worker_failed"
                    else:
                        report["reason"] = "unexpected_descendants" if remaining else "completed"
                    break
                stop.wait(.005)
            stop.set()
            observer.join(timeout=.2)
            if observer.is_alive():
                raise OSError("discovery thread did not stop")
            family.terminate_and_reap(process, started + max_seconds)
            report["owned_family_gone"] = True
            report["owned_group_gone"] = not group_members(process.pid)
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
            report["ok"] = report["reason"] == "completed" and report["owned_family_gone"]
    except Exception as e:
        report.update(ok=False, reason="observation_failure", error=f"{type(e).__name__}: {e}")
    finally:
        stop.set()
        if observer is not None:
            observer.join(timeout=.2)
        if process is not None and family is not None:
            try:
                # Error-unwind remains synchronous even when already late; lateness never admits success.
                family.terminate_and_reap(process, time.monotonic() + 1)
                report["owned_family_gone"] = True
                report["owned_group_gone"] = not group_members(process.pid)
            except Exception as e:
                report.update(ok=False, reason="cleanup_failure", cleanup_error=str(e))
        if family is not None:
            report["discovered_process_identities"] = family.snapshot()
            report["discovered_pids"] = sorted(family.snapshot())
            family.close()
        if libc is not None:
            libc.prctl(36, old_subreaper.value, 0, 0, 0)
        report["elapsed_seconds"] = time.monotonic() - started
        report["sample_gap_seconds"] = gaps(sample_gaps)
        report["discovery_gap_seconds"] = gaps(discovery_gaps)
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


class DeliveryDeadline(Exception):
    pass


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise DeliveryDeadline("whole command deadline exceeded")
    return value


@contextlib.contextmanager
def deadline_guard(deadline: float):
    """One timer covers serialization, filesystem delivery and terminal output as well as observation."""
    if (threading.current_thread() is not threading.main_thread() or any(signal.getitimer(signal.ITIMER_REAL))
            or signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, set())):
        raise DeliveryDeadline("exclusive unblocked main-thread deadline unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_signal, _frame):
        raise DeliveryDeadline("whole command deadline exceeded")
    try:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining(deadline))
        yield
        remaining(deadline)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def write_bounded(fd: int, raw: bytes, deadline: float):
    previous = os.get_blocking(fd)
    selector = selectors.DefaultSelector()
    try:
        os.set_blocking(fd, False)
        sent = 0
        while sent < len(raw):
            remaining(deadline)
            try:
                sent += os.write(fd, raw[sent:])
            except BlockingIOError:
                if not selector.get_map():
                    selector.register(fd, selectors.EVENT_WRITE)
                if not selector.select(remaining(deadline)):
                    raise DeliveryDeadline("verdict delivery deadline exceeded")
        remaining(deadline)
    finally:
        selector.close()
        os.set_blocking(fd, previous)


def regular_output(path: pathlib.Path, raw: bytes, deadline: float):
    # Never wait for a FIFO reader, follow a final symlink, or truncate an unsupported endpoint.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("optional output must be a regular file")
        os.ftruncate(fd, 0)
        write_bounded(fd, raw, deadline)
        os.fsync(fd)
        remaining(deadline)
    finally:
        os.close(fd)


class BoundedParser(argparse.ArgumentParser):
    def __init__(self, *, deadline, **kwargs):
        self.deadline = deadline
        super().__init__(**kwargs)

    def _print_message(self, message, file=None):
        if message:
            write_bounded((file if file is not None else sys.stderr).fileno(), message.encode("utf-8"), self.deadline)


def main(argv: list[str] | None = None) -> int:
    # No-output preparse establishes the same lowered bound even for --help/error delivery.
    probe = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    probe.add_argument("--max-seconds", type=lambda s: lower_limit(s, 60), default=60)
    try:
        preliminary, _unknown = probe.parse_known_args(argv)
        seconds = preliminary.max_seconds
    except (argparse.ArgumentError, ValueError):
        seconds = MAX_SECONDS
    deadline = STARTED + seconds
    try:
        with deadline_guard(deadline):
            parser = BoundedParser(deadline=deadline, description=__doc__)
            parser.add_argument("--ref", default="HEAD")
            parser.add_argument("--max-rss-mib", type=lambda s: lower_limit(s, 512), default=512)
            parser.add_argument("--max-seconds", type=lambda s: lower_limit(s, 60), default=60)
            parser.add_argument("--output", type=pathlib.Path)
            args = parser.parse_args(argv)
            # Unsupported outputs refuse before work. All supported output I/O stays under this same timer.
            if args.output and (args.output.exists() or args.output.is_symlink()) and not stat.S_ISREG(args.output.lstat().st_mode):
                report = {"ok": False, "reason": "unsupported_output", "error": "optional output must be a regular file"}
            else:
                report = run_bounded([sys.executable, "-I", "-B", str(pathlib.Path(__file__).resolve()), "--worker", args.ref],
                                     ROOT, max_rss_bytes=int(args.max_rss_mib * 1024 * 1024), max_seconds=remaining(deadline))
            report.update(kind="committed-inventory-render", command_limit_seconds=args.max_seconds)
            if report.get("stdout"):
                try:
                    report["worker"] = json.loads(report["stdout"])
                    if report.get("ok") and report["worker"]["renderer_exit"] != 0:
                        raise ValueError("renderer did not accept committed documents")
                except (ValueError, KeyError) as e:
                    report.update(ok=False, reason="invalid_worker_result", error=str(e))
            elif report.get("ok"):
                report.update(ok=False, reason="invalid_worker_result", error="worker produced no verdict")
            report.update(elapsed_before_emission_seconds=time.monotonic() - STARTED,
                          terminal_delivery="same whole deadline; exit status is authoritative after bounded final output")
            raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            if args.output and report["reason"] != "unsupported_output":
                regular_output(args.output, raw, deadline)
            write_bounded(sys.stdout.fileno(), raw, deadline)
            remaining(deadline)
            return 0 if report["ok"] else 1
    except (DeliveryDeadline, OSError, ValueError):
        # A partial/late final verdict cannot be retracted. Never append contradictory JSON or return success.
        return 1

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        try:
            raise SystemExit(worker(sys.argv[2]))
        except Exception as e:
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            raise SystemExit(1)
    raise SystemExit(main())
