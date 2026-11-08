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
import errno
import ctypes
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import resource
import signal
import select
import selectors
import socket
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
# A failed release must leave stable ownership reachable, and cannot admit more work.
RETAINED_OWNERSHIP = None


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
            result[int(path.name)] = process_identity(int(path.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


@contextlib.contextmanager
def defer_deadline(*also: signal.Signals):
    """Do not lose a returned kernel resource to the deadline before its owner is registered. The cleanup also
    defers SIGINT, so a second Ctrl-C is raised after the kill pass, receipt, restore and notices (#1700 pass 32 R1).
    A Ctrl-C or the deadline that lands before the cleanup's block takes effect is not deferred; run_bounded then
    runs the cleanup again under the block, up to twice (one held Ctrl-C and the one-shot deadline), and raises the
    held Ctrl-C after it (#1700 pass 35 R1 F3, pass 36 R1 F1, F2, pass 37 R1 F1). A further Ctrl-C there is held too,
    as is one raised while a handled deadline is recorded (pass 38 R1 F1, R3 F1). The three attempts are written out
    in a row, with no loop, so no handler runs between them (pass 39 R1 F1). One case is not handled, and it skips
    the cleanup with no notice: a third signal, Ctrl-C or the deadline, landing as an attempt starts once two
    attempts were already stopped that way (the held Ctrl-C is then raised, or the deadline recorded)."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    interrupted = False
    try:
        # Blocking inside the try: a handler that runs just after the block takes effect raises here, and the
        # finally still restores the mask, so a caller that retries starts from the original mask (pass 36 R1 F2).
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM, *also})
        yield previous
    except KeyboardInterrupt:
        interrupted = True                             # a Ctrl-C raised by the body is never replaced by the deadline
        raise
    finally:
        # A deadline that expired meanwhile goes through first, while the caller can still catch DeliveryDeadline;
        # a Ctrl-C held back with it follows and is not replaced (Python runs SIGINT's handler before SIGALRM's).
        # When the body itself raised KeyboardInterrupt, the deadline is dropped in its favour (#1700 pass 34 R1 F1).
        # A Ctrl-C that the first restore itself raises counts the same, so the second restore, which runs the
        # deadline still pending behind it, does not replace it either (#1700 pass 35 R1 F1).
        try:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous | (set(also) - {signal.SIGALRM}))
            except DeliveryDeadline:
                if not interrupted:
                    raise
            except KeyboardInterrupt:
                interrupted = True
                raise
        finally:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            except DeliveryDeadline:
                if not interrupted:
                    raise


def process_start(pid: int) -> int:
    return process_identity(pid)[0]


def process_identity(pid: int) -> tuple[int, int]:
    # Linux comm permits arbitrary non-NUL bytes, including invalid UTF-8 and parentheses.
    # Only the PID prefix and fixed numeric fields after its final ')' have identity meaning.
    try:
        raw = (PROC / str(pid) / "stat").read_bytes()
        if int(raw[:raw.index(b" (")]) != pid:
            raise ValueError("PID disagreement")
        fields = raw[raw.rfind(b")") + 2:].split()
        start, parent = int(fields[19]), int(fields[1])
        if start < 0 or parent < 0:
            raise ValueError("negative process identity")
        return start, parent
    except (ValueError, IndexError) as e:
        raise OSError(f"invalid process identity for {pid}") from e


RECEIPT = "CREATED-BY"


def boot_id() -> str:
    return (PROC / "sys/kernel/random/boot_id").read_text().strip()


# A root this monitor created, held with its parent by descriptor; receipts and removal never use its path.
# The receipt is attribution evidence only, never proof that every descendant is gone.
class ScratchRoot:
    def __init__(self, path: str):
        self.path, self.name, self.fd = path, os.path.basename(path), None
        self.parent_fd = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY)
        try:
            self.fd = os.open(self.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.parent_fd)
            st = os.fstat(self.fd)
            if st.st_uid != os.geteuid() or st.st_mode & 0o077:
                raise OSError("scratch root is not private")
            self.identity = (st.st_dev, st.st_ino)
        except BaseException:
            self.close()
            raise

    def check(self) -> None:
        st = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
        if (st.st_dev, st.st_ino) != self.identity:
            raise OSError("scratch root is no longer the directory this monitor created")

    def close(self) -> None:
        for fd in (self.fd, self.parent_fd):
            if fd is not None:
                os.close(fd)
        self.fd = self.parent_fd = None


def append_receipt(root: ScratchRoot, entry: dict) -> None:
    """One durable JSON line per ownership event, so a root left by a killed monitor still says whose it is."""
    # Never wait for a FIFO reader or follow a final symlink (QUAL1 R4 F2), as regular_output does.
    fd = os.open(RECEIPT, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root.fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("the scratch receipt must be a regular file")
        os.write(fd, (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def own_children() -> list[dict]:
    """Live direct children of this monitor, by PID and kernel start ticks."""
    me = os.getpid()
    return [{"pid": pid, "start_ticks": start} for pid, (start, parent) in sorted(process_table().items()) if parent == me]


SIGNALLED = "signalled, not reaped by the deadline"


def outcome_key(child: dict) -> tuple[int, int]:
    """The key every cleanup outcome is recorded and read under. A PID names a process only together with its start
    ticks, so an outcome recorded for an earlier holder of a PID is never read for a later one (closure20)."""
    return child["pid"], child["start_ticks"]


def owned_children(parents: list[dict], table: dict[int, tuple[int, int]]) -> list[dict]:
    """The direct children in `table`, one process-table read taken before `parents` were signalled, of each of
    `parents` whose start ticks in `table` are still its listed ones, by PID and start ticks. A PID that `table`
    shows as another process contributes nothing, and a listed child that started before its parent is left out:
    an earlier holder of the parent's PID was its parent."""
    listed = []
    for parent in parents:
        if table.get(parent["pid"], (None,))[0] != parent["start_ticks"]:
            continue
        for pid, (start, ppid) in sorted(table.items()):
            if ppid == parent["pid"] and start >= parent["start_ticks"]:
                listed.append({"pid": pid, "start_ticks": start})
    return listed


def kill_descendants(signalled: list[dict], table: dict[int, tuple[int, int]], deadline: float, outcomes: dict) -> list[dict]:
    """Signal, one generation at a time, the descendants in `table` of `signalled` (children this pass identified and
    signalled). A process is examined only once its parent was itself identified and signalled, so an intermediate
    PID that fails its identity check, or whose signal is refused, prunes its whole subtree (QUAL4 R1, review 14 P1).
    A process already examined, by PID and start ticks, is not examined again. Returns those reaped, as
    kill_unregistered does."""
    reaped, level = [], signalled
    while level:
        listed = [child for child in owned_children(level, table) if outcome_key(child) not in outcomes]
        reaped += kill_unregistered(listed, deadline, outcomes)
        level = [child for child in listed if outcomes.get(outcome_key(child)) == SIGNALLED]
    return reaped


def kill_unregistered(children: list[dict], deadline: float, outcomes: dict | None = None) -> list[dict]:
    """SIGKILL and reap direct children Popen forked but never returned (QUAL1 R1 F2), and signal the descendants
    listed with them; a descendant is reaped here only once it is this monitor's child. Each is signalled through a
    PIDfd opened first and then checked against its listed start ticks, so a recycled PID is never a target; a
    child that vanished, changed identity or is not reaped by the deadline is left for the caller's relist. The
    signal is sent whatever the time; only the reap waits on the deadline. Why each child was not reaped is
    recorded in `outcomes` by PID and start ticks (QUAL3 R3 F3, closure20)."""
    killed = []
    outcomes = {} if outcomes is None else outcomes
    for child in children:
        pid, key = child["pid"], outcome_key(child)
        try:
            fd = os.pidfd_open(pid)
        except OSError:
            outcomes[key] = "identity unverified"
            continue
        try:
            # A start time that cannot be read is an unverified identity, not a refused signal (QUAL4 R1 F2).
            try:
                same = process_start(pid) == child["start_ticks"]
            except (OSError, ValueError):
                same = False
            if not same:
                outcomes[key] = "identity unverified"
                continue
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except (OSError, ValueError):
                outcomes[key] = "signal refused"
                continue
        finally:
            os.close(fd)
        outcomes[key] = SIGNALLED
        while time.monotonic() < deadline:
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    killed.append(child)
                    break
            except ChildProcessError:
                break
            time.sleep(.005)
    return killed


STALLED = "not examined: the pass before it reaped nothing"


def unproven_reasons(remaining: list[dict], outcomes: dict, stalled: bool = False) -> dict[int, str]:
    """Why each remaining child was not proven killed, by PID for the notices and receipt, looked up by PID and start
    ticks, so a child is never named with the outcome of an earlier holder of its PID (closure20). A child with no
    outcome was never examined: because the passes stopped after one that reaped nothing when `stalled`, otherwise
    because the deadline passed (closure21 item 5)."""
    unexamined = STALLED if stalled else "not examined before the deadline"
    return {child["pid"]: outcomes.get(outcome_key(child), unexamined) for child in remaining}


def clear_directory(dir_fd: int, deadline: float, keep: str | None = None) -> bool:
    """Remove a directory's contents through descriptors without following links; False once out of time."""
    with os.scandir(dir_fd) as listing:
        for entry in listing:
            if time.monotonic() >= deadline:
                return False
            if entry.name == keep:
                continue
            if entry.is_dir(follow_symlinks=False):
                child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
                try:
                    if not clear_directory(child, deadline):
                        return False
                finally:
                    os.close(child)
                os.rmdir(entry.name, dir_fd=dir_fd)
            else:
                os.unlink(entry.name, dir_fd=dir_fd)
    return True


# The name is checked against the held identity before clearing, before the receipt (removed last) and before
# rmdir through the parent's descriptor. Not excluded: a swap inside that last check-to-rmdir system call gap.
def remove_scratch(root: ScratchRoot, deadline: float) -> bool:
    """Remove exactly the root this monitor created, within the deadline; False if time ran out first."""
    root.check()
    if not clear_directory(root.fd, deadline, keep=RECEIPT) or time.monotonic() >= deadline:
        return False
    root.check()
    with contextlib.suppress(FileNotFoundError):
        os.unlink(RECEIPT, dir_fd=root.fd)
    try:
        root.check()
    except OSError:
        append_receipt(root, {"event": "removal_aborted"})
        raise
    try:
        os.rmdir(root.name, dir_fd=root.parent_fd)
    except OSError as e:
        # A kept root keeps its attribution (QUAL1 R4 F3). The rmdir error is what propagates.
        with contextlib.suppress(OSError):
            append_receipt(root, {"event": "removal_failed", "error": f"{type(e).__name__}: {e}"})
        raise
    return True


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
        if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
            raise OSError("custom child-reaping handlers prevent exclusive ownership")
        self.owned: dict[int, tuple[int | None, int]] = {}
        self.lock = threading.RLock()

    def admit_root(self, process: subprocess.Popen):
        # Caller defers the deadline across actual spawn/return and this immediate admission.
        fd = os.pidfd_open(process.pid)
        self.owned[process.pid] = (None, fd)
        self.owned[process.pid] = (process_start(process.pid), fd)

    def discover(self, *, stopped: threading.Event | None = None) -> dict[int, int]:
        with self.lock:
            table = process_table()
            # A collector can return after its measurement ended. Its old exclusive
            # interval does not authorize admission of a caller's subsequent children.
            if stopped is not None and stopped.is_set():
                return {}
            return self.admit_table(table)

    def admit_table(self, table: dict[int, tuple[int, int]]) -> dict[int, int]:
        """Only verified parentage and stable PIDfds authorize admission, never a bare PID or session."""
        with selectors.DefaultSelector() as selector:
            for pid, (_start, fd) in self.owned.items():
                selector.register(fd, selectors.EVENT_READ, pid)
            stopped = {key.data for key, _events in selector.select(0)}
        admitted = {pid for pid, (start, _fd) in self.owned.items()
                    if pid not in stopped and table.get(pid, (None,))[0] == start}
        # An already stopped PIDfd still owns this exact unreaped identity; do not replace it.
        considered = {pid for pid, (start, _fd) in self.owned.items()
                      if table.get(pid, (None,))[0] == start}
        errors = []
        while True:
            new = {pid for pid, (_start, parent) in table.items()
                   if parent == os.getpid() or parent in admitted} - considered
            if not new:
                break
            considered.update(new)
            for pid in new:
                start = table[pid][0]
                try:
                    with defer_deadline():
                        fd = os.pidfd_open(pid)
                        registered = False
                        try:
                            current, parent = process_identity(pid)
                            if current != start:
                                continue
                            if parent != os.getpid():
                                if parent not in admitted or process_start(parent) != self.owned[parent][0]:
                                    continue
                            previous = self.owned.get(pid)
                            self.owned[pid] = (start, fd)
                            registered = True
                            admitted.add(pid)
                            if previous is not None:
                                os.close(previous[1])
                        finally:
                            if not registered:
                                os.close(fd)
                except (ProcessLookupError, FileNotFoundError):
                    pass
                except (OSError, ValueError, IndexError) as e:
                    errors.append(str(e))
        if errors:
            raise OSError("owned process identity unavailable: " + errors[0])
        return {pid: start for pid, (start, _fd) in self.owned.items() if table.get(pid, (None,))[0] == start}

    def recover(self) -> dict[int, int]:
        """Independent raw directory/stat path for cleanup when the normal collector fails.

        Exclusive preflight and subreaper adoption establish ownership of new direct children.
        Stable unreadable entries leave uncertainty, but do not prevent admitting other verified
        descendants. No assumption about unavailable /proc children files is necessary.
        """
        with self.lock:
            table = {}
            errors = []
            try:
                with os.scandir(PROC) as entries:
                    for entry in entries:
                        if not entry.name.isdecimal():
                            continue
                        pid = int(entry.name)
                        try:
                            table[pid] = process_identity(pid)
                        except (FileNotFoundError, ProcessLookupError):
                            pass
                        except (OSError, ValueError, IndexError) as e:
                            errors.append(str(e))
            except OSError as e:
                errors.append(str(e))
            result = self.admit_table(table)
            if errors:
                raise OSError("independent process observation incomplete: " + errors[0])
            return result

    def cleanup_discover(self) -> dict[int, int]:
        try:
            return self.discover()
        except (OSError, ValueError, IndexError):
            return self.recover()

    def snapshot(self) -> dict[int, int]:
        with self.lock:
            return {pid: start for pid, (start, _fd) in self.owned.items()}

    def sample(self) -> dict[int, int]:
        result = {os.getpid(): rss(os.getpid())}
        for pid, start in self.snapshot().items():
            try:
                if process_start(pid) != start:
                    continue
                value = rss(pid)
                if process_start(pid) == start:
                    result[pid] = value
            except (FileNotFoundError, ProcessLookupError):
                pass
        return result

    def known_live(self) -> bool:
        with selectors.DefaultSelector() as selector:
            for _start, fd in self.owned.values():
                selector.register(fd, selectors.EVENT_READ)
            return len(selector.select(0)) != len(self.owned)

    def signal_known(self):
        # Stable handles are sufficient authority even if EVERY subsequent observation fails.
        for _start, fd in list(self.owned.values()):
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def terminate_and_reap(self, process: subprocess.Popen, deadline: float) -> bool:
        while True:
            # Known stable handles and the exclusively owned unreaped root do not depend on
            # successful observation. Stop them BEFORE any parser/collector can fail again.
            self.signal_known()
            if process.poll() is None:
                process.kill()
            try:
                self.cleanup_discover()
            except Exception:
                pass  # Neither failed view can revoke known ownership or certify an unknown family.
            self.signal_known()
            # If PIDfd acquisition itself failed, Popen still owns this unreaped child.
            # Exclusive caller/default SIGCHLD prevents another waiter from recycling its PID.
            if process.poll() is None:
                process.kill()
            process.poll()
            for pid in self.snapshot():
                if pid == process.pid:
                    continue
                try:
                    os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    pass
            if not self.known_live():
                process.wait(timeout=max(.01, deadline - time.monotonic()))
                try:
                    # Killing a known parent may adopt previously unseen escaped descendants.
                    # Discover again before certifying completion, even if the first scan failed.
                    if not self.cleanup_discover():
                        return True
                except Exception:
                    if not self.known_live():
                        # Known owners are stopped; two unavailable views never certify the whole family.
                        return False
            if time.monotonic() >= deadline:
                raise OSError("owned descendants not reaped before cleanup deadline")
            time.sleep(.002)

    def close(self) -> None:
        with self.lock:
            errors = []
            for pid, (_start, fd) in list(self.owned.items()):
                try:
                    with selectors.DefaultSelector() as selector:
                        selector.register(fd, selectors.EVENT_READ)
                        if not selector.select(0):
                            raise OSError("cannot release live known descendant ownership")
                    os.close(fd)
                except OSError as e:
                    errors.append(str(e))
                else:
                    del self.owned[pid]
            if errors:
                raise OSError("owned descriptor release failed: " + "; ".join(errors))



NOTICE_CUT = b" [notice cut]\n"
NOTICE_FINISH_SECONDS = 0.25   # all notices together may wait this long for a slow reader after a part write


def write_notice(line: str, finish_by: float | None = None) -> None:
    """Write one cleanup notice to stderr without ever blocking. A stream with no descriptor (a test's StringIO, or
    an object with no fileno at all) is printed to, since it cannot block. Otherwise the line goes to the descriptor
    (fd 2 when sys.stderr is None) with writes that never block and never change its flags (write_now) as one ASCII line: its text is escaped with unicode_escape,
    so a line feed, a carriage return, a backslash or a non-UTF-8 byte in a path can neither split the line nor
    turn into another path's name; a line over PIPE_BUF bytes is cut to PIPE_BUF and ends in NOTICE_CUT, so a pipe
    takes it whole or not at all and a cut path is never read as a whole one; a cut falls between whole escapes, so
    the kept text still decodes with unicode_escape; and the descriptor's blocking flag is never changed. When the descriptor takes only part of the line (a stream socket whose buffer just filled),
    the rest is written as the descriptor becomes writable, until finish_by (monotonic; NOTICE_FINISH_SECONDS from
    now when not given), so the line still arrives whole. Raises OSError (BlockingIOError when the pipe is full, EBADF
    when it is closed, EIO when the rest could not be written by finish_by: a reader that does not drain, or a
    regular file at its size limit; the fragment then stays unmarked, and later stderr text can join its line) or
    ValueError. write_notices drops the notice on any of them and writes no further notice after EIO."""
    stream = sys.stderr
    try:
        fd = 2 if stream is None else stream.fileno()
    except (AttributeError, OSError, ValueError):
        print(line, end="", file=stream)
        return
    text = line.removesuffix("\n")
    data = text.encode("unicode_escape") + b"\n"      # ASCII, one line, every byte escaped
    if len(data) > select.PIPE_BUF:                    # a pipe write of at most PIPE_BUF bytes is whole or nothing
        room, kept = select.PIPE_BUF - len(NOTICE_CUT), bytearray()
        for ch in text:                                # whole escapes only, so the kept text still decodes
            piece = ch.encode("unicode_escape")
            if len(kept) + len(piece) > room:
                break
            kept += piece
        data = bytes(kept) + NOTICE_CUT                # marked, so a cut path is never read as a whole one
    sent = write_now(fd, data)
    if sent != len(data):                              # a stream socket, or a regular file at its size limit
        if finish_by is None:
            finish_by = time.monotonic() + NOTICE_FINISH_SECONDS
        if sent + finish_notice(fd, data[sent:], finish_by) != len(data):
            raise OSError(errno.EIO, "notice written in part")


# Character devices whose path names no fixed file: reopening /dev/tty or /dev/ptmx through /proc reaches a different
# terminal than the one stderr holds (#1700 pass 36 R1 F3).
REOPEN_ELSEWHERE = frozenset({os.makedev(5, 0), os.makedev(5, 2)})


def write_now(fd: int, data: bytes) -> int:
    """One write that never blocks and never changes the descriptor's flags. Its open file description is shared
    with every process that holds the same stderr, so toggling O_NONBLOCK there could leave another writer
    non-blocking (#1700 pass 33 R1 F2, pass 34 R1 F2). A pipe or a character device (a terminal) is written through a
    private non-blocking description of the same file, a socket with MSG_DONTWAIT on a duplicate, and a regular file,
    which never waits for a reader, directly. A pipe or terminal this process cannot reopen (one another user
    created, as after su or sudo -u, no /proc, or /dev/tty after setsid, ENXIO) falls back to toggled_write, so the
    notice still arrives (#1700 pass 35 R1 F4, pass 36 R1 F3); so does /dev/ptmx or /dev/tty, whose reopen opens a new
    pty or the current controlling terminal rather than the file stderr holds. Raises OSError (BlockingIOError when
    full)."""
    st = os.fstat(fd)
    if stat.S_ISCHR(st.st_mode) and st.st_rdev in REOPEN_ELSEWHERE:
        return toggled_write(fd, data)
    if stat.S_ISFIFO(st.st_mode) or stat.S_ISCHR(st.st_mode):
        try:
            own = os.open(f"/proc/self/fd/{fd}", os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY)
        except OSError:
            return toggled_write(fd, data)
        try:
            return os.write(own, data)
        finally:
            os.close(own)
    if stat.S_ISSOCK(st.st_mode):
        with socket.socket(fileno=os.dup(fd)) as s:
            return s.send(data, socket.MSG_DONTWAIT)
    return os.write(fd, data)


def toggled_write(fd: int, data: bytes) -> int:
    """The fallback when write_now cannot reopen a pipe or terminal: one write with O_NONBLOCK set on the shared
    description for that call only and cleared before returning, as before FIX22. Another process writing the same
    stderr in that instant can see it non-blocking; that is the one case where a notice touches the flags. Its
    callers run with SIGINT and SIGALRM blocked, so nothing interrupts it between setting and clearing the flag."""
    if not os.get_blocking(fd):
        return os.write(fd, data)
    os.set_blocking(fd, False)
    try:
        return os.write(fd, data)
    finally:
        os.set_blocking(fd, True)


def finish_notice(fd: int, rest: bytes, finish_by: float) -> int:
    """Write the rest of a part-written notice, one write_now at a time, waiting for the descriptor to become writable
    until finish_by (monotonic), and return how many bytes of rest were written. Stops early on any error other than
    BlockingIOError (EFBIG or ENOSPC at a size limit, EPIPE, EBADF) and on a write of 0 bytes."""
    written = 0
    while written < len(rest):
        left = finish_by - time.monotonic()
        if left <= 0:
            break
        try:
            _, ready, _ = select.select([], [fd], [], left)
        except (OSError, ValueError):
            break
        if not ready:
            break
        try:
            n = write_now(fd, rest[written:])
        except BlockingIOError:
            continue
        except OSError:
            break
        if n <= 0:
            break
        written += n
    return written


def write_notices(notices: list[str]) -> None:
    """Write each cleanup notice with write_notice, dropping one that cannot be written. All of them share one
    NOTICE_FINISH_SECONDS budget for finishing part writes, so a slow reader adds at most that to the cleanup. After
    a part write that could not be finished (EIO) no further notice is written (#1700 pass 27 R1 F1)."""
    finish_by = time.monotonic() + NOTICE_FINISH_SECONDS
    for notice in notices:
        try:
            write_notice(f"measure_inventory_render: {notice}\n", finish_by)
        except OSError as e:
            if e.errno == errno.EIO:
                return
        except ValueError:
            pass

def run_bounded(argv: list[str], cwd: pathlib.Path, *, max_rss_bytes: int, max_seconds: float) -> dict:
    """Observe/reap actual descendants, including new sessions; report sampling uncertainty honestly."""
    global RETAINED_OWNERSHIP
    started = time.monotonic()
    if (isinstance(max_rss_bytes, bool) or not isinstance(max_rss_bytes, int) or not 0 < max_rss_bytes <= MAX_RSS
            or isinstance(max_seconds, bool) or not math.isfinite(max_seconds) or not 0 < max_seconds <= MAX_SECONDS):
        raise ValueError("limits must be finite, positive and no greater than 512 MiB/60 seconds")
    report = {"ok": False, "reason": "observation_failure", "argv": argv, "cwd": str(cwd),
              "max_rss_bytes": max_rss_bytes, "max_seconds": max_seconds, "peak_rss_bytes": 0,
              "monitor_rss_bytes": 0, "peak_snapshot": {}, "sample_count": 0,
              "owned_group_gone": False, "owned_family_gone": False,
              "scratch_root": None, "scratch_root_removed": False}
    process = family = observer = libc = scratch = pending_interrupt = None
    spawn_pending = reaped = cleanup_started = False
    stop = threading.Event()
    discovery_gaps: list[float] = []
    sample_gaps: list[float] = []
    errors: list[str] = []
    old_subreaper = ctypes.c_int()
    subreaper_acquired = False

    def record_sample():
        sample = family.sample() if family is not None else {os.getpid(): rss(os.getpid())}
        total = sum(sample.values())
        report["sample_count"] += 1
        report["monitor_rss_bytes"] = max(report["monitor_rss_bytes"], sample[os.getpid()])
        if total > report["peak_rss_bytes"]:
            report.update(peak_rss_bytes=total, peak_snapshot=sample)
        return total

    try:
        if RETAINED_OWNERSHIP is not None:
            raise OSError("unresolved prior owned-family resources prevent another measurement")
        kernel_peak_before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024
        family = OwnedFamily()
        with defer_deadline():
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.prctl(37, ctypes.byref(old_subreaper), 0, 0, 0):
                raise OSError(ctypes.get_errno(), "cannot read prior child ownership state")
            if libc.prctl(36, 1, 0, 0, 0):
                raise OSError(ctypes.get_errno(), "cannot own adopted descendants")
            subreaper_acquired = True
        if record_sample() > max_rss_bytes:
            report["reason"] = "rss_limit"
            return report
        # Every temp file the worker family makes lands under a root this monitor creates and removes after the
        # family is reaped, whatever the outcome; a worker killed on a limit cannot clean up after itself.
        with defer_deadline():
            path = tempfile.mkdtemp(prefix=f"measure-render-{os.getpid()}-")
            report["scratch_root"] = path
            scratch = ScratchRoot(path)
        append_receipt(scratch, {"event": "created", "monitor_pid": os.getpid(), "monitor_start_ticks": process_start(os.getpid()),
                                 "boot_id": boot_id(), "argv": argv, "cwd": str(cwd), "created_unix": time.time()})
        child_env = {**os.environ, "TMPDIR": scratch.path}
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            with defer_deadline() as child_mask:
                # Acquisition is atomic with respect to the deadline. The child inherits the caller's ORIGINAL mask.
                # From here until `process` is bound, a child may exist that nothing has registered yet.
                spawn_pending = True
                try:
                    process = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True,
                                               env=child_env, preexec_fn=lambda: signal.pthread_sigmask(signal.SIG_SETMASK, child_mask))
                except (OSError, subprocess.SubprocessError):
                    spawn_pending = False   # Popen reaps a child whose exec failed before it raises
                    raise
                spawn_pending = False
                family.admit_root(process)
                report["process_group"] = process.pid
            append_receipt(scratch, {"event": "worker", "worker_pid": process.pid,
                                     "worker_start_ticks": process_start(process.pid), "process_group": process.pid})
            family.discover()

            def discover():
                last = time.monotonic()
                while not stop.is_set():
                    try:
                        family.discover(stopped=stop)
                        now = time.monotonic()
                        discovery_gaps.append(now - last)
                        last = now
                    except Exception as e:
                        errors.append(f"{type(e).__name__}: {e}")
                        return
                    stop.wait(.05)

            observer = threading.Thread(target=discover, name="inventory-rss-discovery", daemon=True)
            with defer_deadline(signal.SIGINT):
                # The thread inherits this mask, so the kernel sends the deadline and Ctrl-C to the main thread,
                # which defers them in the cleanup; a signal the observer took would still raise there (pass 32 R1).
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
            if errors:
                raise OSError(errors[0])
            with defer_deadline():
                complete_cleanup = family.terminate_and_reap(process, started + max_seconds)
            if not complete_cleanup:
                raise OSError("discovery unavailable after known child cleanup")
            reaped = not family.known_live()
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
            report["kernel_child_peak_before_bytes"] = kernel_peak_before
            report["kernel_child_peak_scope"] = ("invocation-owned children; zero prior child usage"
                                                  if kernel_peak_before == 0 else
                                                  "process-lifetime cumulative; diagnostic only")
            if kernel_peak_before == 0 and report["kernel_child_peak_bytes"] > max_rss_bytes:
                report["reason"] = "rss_limit"
            report["ok"] = report["reason"] == "completed" and report["owned_family_gone"]
    except Exception as e:
        report.update(ok=False, reason="observation_failure", error=f"{type(e).__name__}: {e}")
    finally:
        # The cleanup runs under defer_deadline(SIGINT). A Ctrl-C or the deadline handled before that block takes
        # effect (the first statements here, while the first Ctrl-C is still propagating) would otherwise skip all of
        # it: the kill pass, the scratch removal, the subreaper restore and the notices. Each attempt marks it started
        # once the block is in effect; a signal that lands before that runs it again, now under the block, and a held
        # Ctrl-C is raised after it. Every Ctrl-C is held and the first is raised after the cleanup. The attempts are
        # written out in a row, not as a loop, because a handler can run at a loop's back-jump, outside every try;
        # between them the only call, recording a handled deadline, sits in its own try (#1700 pass 35 R1 F3, pass 36
        # R1 F1, F2, pass 37 R1 F1, pass 38 R1 F1, R3 F1, F2, pass 39 R1 F1; the one limit left is in defer_deadline's
        # docstring). Defining cleanup makes no call, so no handler runs between entering this finally and the first
        # try.
        def cleanup():                         # one attempt, run under the block
            global RETAINED_OWNERSHIP
            nonlocal reaped
            cleanup_errors = []
            notices: list[str] = []
            def cleanup_failure(e):
                cleanup_errors.append(f"{type(e).__name__}: {e}")
                report.update(ok=False, reason="cleanup_failure", owned_family_gone=False,
                              cleanup_error="; ".join(cleanup_errors))
            try:
                stop.set()
                if observer is not None:
                    observer.join(timeout=1)
                    if observer.is_alive():
                        raise OSError("discovery thread did not stop during cleanup")
                if errors:
                    report.update(ok=False, reason="observation_failure", error=errors[0])
            except Exception as e:
                cleanup_failure(e)
            observer_live = observer is not None and observer.is_alive()
            try:
                if process is not None and family is not None:
                    if observer_live:
                        # Do not block on its lock or release authority it can still extend.
                        family.signal_known()
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=1)
                        raise OSError("active discovery retains unresolved descendant ownership")
                    # Final unwind cannot abandon an owner when observation or the timer failed.
                    report["owned_family_gone"] = family.terminate_and_reap(process, time.monotonic() + 1)
                    report["known_owned_reaped"] = not family.known_live()
                    reaped = report["owned_family_gone"] and report["known_owned_reaped"]
                    report["owned_group_gone"] = not group_members(process.pid)
                    if not report["owned_family_gone"]:
                        report.update(ok=False, reason="cleanup_observation_failure")
            except Exception as e:
                cleanup_failure(e)
            try:
                if family is not None and not observer_live:
                    report["discovered_process_identities"] = family.snapshot()
                    report["discovered_pids"] = sorted(family.snapshot())
            except Exception as e:
                cleanup_failure(e)
            finally:
                try:
                    if family is not None:
                        for attempt in range(0 if observer_live else 2):
                            try:
                                family.close()
                                break
                            except Exception as e:
                                cleanup_failure(e)
                                if attempt == 0 and process is not None:
                                    try:
                                        family.terminate_and_reap(process, time.monotonic() + 1)
                                    except Exception as e:
                                        cleanup_failure(e)
                        if family.owned or observer_live:
                            RETAINED_OWNERSHIP = (family, process, observer)
                            report.update(ok=False, retained_ownership=True, owned_family_gone=False,
                                          retained_observer_alive=observer_live,
                                          retained_owned_pids=sorted(family.owned))
                finally:
                    # The scratch root is removed only when nothing this monitor started can still write to it,
                    # and only within the command's own deadline. Its outcome never rewrites the family verdict.
                    retained = None
                    if scratch is None and report["scratch_root"] is not None:
                        retained = "root_not_held"
                    elif scratch is not None:
                        try:
                            if process is None and spawn_pending:
                                # As subreaper, whatever Popen forked is still a child here; none: it never forked.
                                retained = "spawn_children_unknown"
                                children = own_children()
                                report["scratch_root_unregistered_children"] = children
                                # A killed child's own descendants are adopted by this subreaper and appear on
                                # the relist with readable start ticks: the same identity-checked PIDfd kill
                                # reaps them, pass after pass, until the relist is empty, a pass kills nothing
                                # (no child left could be identified, signalled and reaped) or the deadline
                                # passes (QUAL2 R1 F1). The first pass runs even after the deadline, so a child
                                # it can identify is always signalled; the deadline bounds only reaping and
                                # further passes (QUAL3 R1 F1). Each pass then signals, a generation at a time,
                                # the descendants listed in a process-table read taken before that pass, starting
                                # from the children it identified and signalled; each goes through its own
                                # identity-checked PIDfd, and only once its parent was identified and signalled,
                                # so a listed descendant is not left alive unexamined when it would be adopted
                                # only after the deadline (QUAL4 R1). A child or intermediate not signalled
                                # (identity unverified, signal refused) prunes its subtree (review 14 P1).
                                # Limits: a descendant forked after that read is not listed, and one not adopted
                                # in time stays named "not examined before the deadline", or, when the passes
                                # stopped after one that reaped nothing, STALLED (closure21 item 5). That read is optional:
                                # if it fails, the pass still signals the children already listed, then the
                                # failure propagates as a failed relist does (review 14 P2).
                                killed, remaining, outcomes, first, stalled = [], children, {}, True, False
                                while remaining and (first or time.monotonic() < started + max_seconds):
                                    first = False
                                    try:
                                        table, table_error = process_table(), None
                                    except Exception as e:
                                        table, table_error = None, e
                                    reaped_now = kill_unregistered(remaining, started + max_seconds, outcomes)
                                    killed += reaped_now
                                    if table_error is not None:
                                        raise table_error
                                    signalled = [child for child in remaining if outcomes.get(outcome_key(child)) == SIGNALLED]
                                    descendants_reaped = kill_descendants(signalled, table, started + max_seconds, outcomes)
                                    reaped_now += descendants_reaped
                                    killed += descendants_reaped
                                    remaining = own_children()
                                    if not reaped_now:
                                        stalled = True
                                        break
                                report["scratch_root_unregistered_killed"] = killed
                                retained = None
                                notices += [f"killed unregistered child {child['pid']}" for child in killed]
                                if remaining:
                                    retained = "spawn_not_registered"
                                    report["scratch_root_unregistered_remaining"] = remaining
                                    reasons = unproven_reasons(remaining, outcomes, stalled)
                                    # Named before the receipt is written: the worker owns the root and can make
                                    # that write fail, which must not also silence stderr (QUAL3 R1 F2).
                                    notices += [f"child {pid} not proven killed: {why}" for pid, why in reasons.items()]
                                    append_receipt(scratch, {"event": "unregistered_spawn", "children": children,
                                                             "killed": killed, "remaining": remaining,
                                                             "reasons": {str(pid): why for pid, why in reasons.items()}})
                            elif process is not None and (not reaped or observer_live or report.get("retained_ownership")):
                                retained = "family_not_proven_reaped"
                            if retained is None:
                                if remove_scratch(scratch, started + max_seconds - min(.2, max_seconds * .1)):
                                    report["scratch_root_removed"] = True
                                else:
                                    retained = "removal_deadline"
                        except Exception as e:
                            retained = retained or "removal_failed"
                            report["scratch_root_error"] = f"{type(e).__name__}: {e}"
                        finally:
                            scratch.close()
                    if retained:
                        report.update(ok=False, scratch_root_retained=True, scratch_root_retained_reason=retained)
                        if process is None and spawn_pending:
                            # The exception that interrupted the spawn propagates and no report prints.
                            error = report.get("scratch_root_error")
                            notices.append(f"retained {report['scratch_root']} ({retained})" + (f": {error}" if error else ""))
                        if report["reason"] == "completed":
                            report["reason"] = "scratch_cleanup_incomplete"
                    if libc is not None and subreaper_acquired:
                        try:
                            if libc.prctl(36, old_subreaper.value, 0, 0, 0):
                                raise OSError("cannot restore prior child ownership state")
                        except Exception as e:
                            cleanup_failure(e)
                    # Notices go out last, after the receipt, removal and subreaper restore, and a stderr that
                    # cannot be written never replaces the interrupt that is propagating (QUAL2 R1 F2). With stderr
                    # closed at startup sys.stderr is None, and print(file=None) would write to stdout, the report's
                    # channel, so they go to fd 2 itself, where a closed fd is only an OSError (#1700 pass 22 R1 F1).
                    # SIGALRM and SIGINT are blocked here, so a write to a full stderr pipe would wait past the deadline: each
                    # notice is written to the descriptor without blocking, and one that does not fit is dropped
                    # (#1700 pass 23 R1 F1). A part write is finished within one shared NOTICE_FINISH_SECONDS
                    # budget; one left in part stops the notices, so every later one is dropped (pass 28). That
                    # budget starts here, not at the deadline: the cleanup above can already end past the deadline (an
                    # interrupt after it), and finishing adds up to 0.25 s after that (passes 29 and 30).
                    write_notices(notices)
        try:
            with defer_deadline(signal.SIGINT):
                cleanup_started = True
                cleanup()
        except DeliveryDeadline as e:
            try:                                   # a Ctrl-C while the deadline is recorded is held as well
                report.update(ok=False, reason="time_limit", error=str(e))
            except KeyboardInterrupt as held:
                if cleanup_started:
                    raise
                pending_interrupt = pending_interrupt or held
        except KeyboardInterrupt as e:
            if cleanup_started:
                raise
            pending_interrupt = pending_interrupt or e
        if not cleanup_started:
            try:
                with defer_deadline(signal.SIGINT):
                    cleanup_started = True
                    cleanup()
            except DeliveryDeadline as e:
                try:                                   # a Ctrl-C while the deadline is recorded is held as well
                    report.update(ok=False, reason="time_limit", error=str(e))
                except KeyboardInterrupt as held:
                    if cleanup_started:
                        raise
                    pending_interrupt = pending_interrupt or held
            except KeyboardInterrupt as e:
                if cleanup_started:
                    raise
                pending_interrupt = pending_interrupt or e
        if not cleanup_started:
            try:
                with defer_deadline(signal.SIGINT):
                    cleanup_started = True
                    cleanup()
            except DeliveryDeadline as e:
                try:                                   # a Ctrl-C while the deadline is recorded is held as well
                    report.update(ok=False, reason="time_limit", error=str(e))
                except KeyboardInterrupt as held:
                    if cleanup_started:
                        raise
                    pending_interrupt = pending_interrupt or held
            except KeyboardInterrupt as e:
                if cleanup_started:
                    raise
                pending_interrupt = pending_interrupt or e
        if pending_interrupt is not None:
            raise pending_interrupt
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
        # Ignoring SIGALRM discards one still pending behind a deferred mask (a Ctrl-C that lands as a deferred
        # section's exit starts leaves it so), so restoring the default action cannot kill the process later
        # (#1700 pass 35 R1 F2).
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
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
    return _main(argv, time.monotonic())


def _main(argv: list[str] | None, started: float) -> int:
    # No-output preparse establishes the same lowered bound even for --help/error delivery.
    probe = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    probe.add_argument("--max-seconds", type=lambda s: lower_limit(s, 60), default=60)
    try:
        preliminary, _unknown = probe.parse_known_args(argv)
        seconds = preliminary.max_seconds
    except (argparse.ArgumentError, ValueError):
        seconds = MAX_SECONDS
    deadline = started + seconds
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
            report.update(elapsed_before_emission_seconds=time.monotonic() - started,
                          terminal_delivery="same whole deadline; exit status is authoritative after bounded final output")
            raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
            if args.output and report["reason"] != "unsupported_output":
                regular_output(args.output, raw, deadline)
            write_bounded(sys.stdout.fileno(), raw, deadline)
            remaining(deadline)
            return 0 if report["ok"] else 1
    except DeliveryDeadline as e:
        # A deadline handled after the cleanup, while a Ctrl-C is propagating (at run_bounded's last calls, or as the
        # timer is stopped), does not turn that Ctrl-C into a plain failure: the run still ends as a Ctrl-C (#1700
        # pass 39 R1 F2). Otherwise, as below, a partial/late final verdict cannot be retracted.
        if isinstance(e.__context__, KeyboardInterrupt):
            raise e.__context__
        return 1
    except (OSError, ValueError):
        # A partial/late final verdict cannot be retracted. Never append contradictory JSON or return success.
        return 1

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        try:
            raise SystemExit(worker(sys.argv[2]))
        except Exception as e:
            print(f"{type(e).__name__}: {e}", file=sys.stderr)
            raise SystemExit(1)
    raise SystemExit(_main(None, STARTED))
