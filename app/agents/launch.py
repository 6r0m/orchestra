"""Launch one agent process from an argv list, and leave nothing of it running.

No shell sits between us and the agent: the argv list is the command, the prompt
arrives on stdin from a file, and the exit status is the agent's own.

The agent's whole descendant tree is contained by a primitive native to the host,
because killing the direct child leaves its tool processes running:

- POSIX: the agent runs in a transient systemd user scope — a cgroup no descendant
  can leave, whatever it does to its own session — and one write to `cgroup.kill`
  ends every process in it. A stub inside the scope reports that it is there and
  starts the agent only when we answer, so an agent never runs outside a scope and
  never starts after our death. A small reaper process, started first, holds a pipe
  from us; when we die without a word the pipe closes and the reaper kills the
  scope — through its cgroup once the agent is running, so it needs no systemd for
  that. Where no scope can be made the agent is refused before it runs, and no
  systemd call on any path waits without a bound.
- Windows: the agent is created already inside a job object that kills every process
  in it when its last handle closes — one `CreateProcess` call, so no moment exists in
  which it lives outside the job. We hold that handle, so our death closes it. Ending
  the tree closes the job to newcomers, holds each process it lists, terminates the job
  and waits for each: until its termination finishes a process still holds the directory
  it worked in, which Windows will not remove. An end it cannot prove — a listed process
  it cannot open, one not ended within the grace — raises.

Whichever way the run ends — its exit, a timeout, a Stop raised by `on_tick`, or our
death — the tree is gone afterwards.
"""
import os
import select
import subprocess
import sys
import time
import uuid

WINDOWS = sys.platform.startswith("win")
# Between asking the tree to stop and killing it.
GRACE_SECONDS = 5
TICK_SECONDS = 1.0
# Waiting for systemd to create the agent's scope before the launch is refused, and for any
# one systemctl call: a hung user manager must not hang the worker.
SCOPE_SECONDS = 30.0
SYSTEMCTL_SECONDS = 10.0


class RoleTimeout(TimeoutError):
    """A role-run outlived its budget, and its process tree has been ended."""
    error_type = "timeout"


class ExecutorError(RuntimeError):
    """The agent could not be launched on this host."""
    error_type = "executor"


def run(argv, cwd, stdin_path, stdout_path, stderr_path, timeout, env=None, on_tick=None):
    """Run `argv` to completion and return its exit status.

    `on_tick` is called about once a second while the agent runs; whatever it
    raises ends the tree and propagates. Raises RoleTimeout after `timeout` seconds.
    """
    tree = _Tree()
    with open(stdin_path, "rb") as stdin, open(stdout_path, "wb") as stdout, \
            open(stderr_path, "wb") as stderr:
        proc = tree.start(argv, cwd, stdin, stdout, stderr, env)
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    rc = proc.wait(timeout=TICK_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if on_tick is not None:
                    on_tick()
                if time.monotonic() >= deadline:
                    tree.stop(proc)
                    raise RoleTimeout("role-run did not finish within %ds" % timeout)
        except BaseException:
            # The tree's handle goes whatever its end says; an end it cannot prove is raised.
            try:
                tree.stop(proc)
            finally:
                tree.close()
            raise
    # The agent is done; anything it left behind goes with it.
    try:
        tree.kill()
    finally:
        tree.close()
    return rc


class _PosixTree:
    # Runs inside the scope, before the agent: reports the cgroup it is in, then waits
    # for the owner's go. A write to an owner already dead fails, and so does the read,
    # so an agent never starts once the owner is gone.
    STUB = ("import os, sys\n"
            "ready, go, unit = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]\n"
            "with open('/proc/self/cgroup', encoding='utf-8') as fh:\n"
            "    cgroup = [l[3:] for l in fh.read().splitlines() if l.startswith('0::')]\n"
            "if not cgroup or unit not in cgroup[0]:\n"
            "    sys.exit(125)\n"
            "os.write(ready, ('in %s\\n' % cgroup[0]).encode('utf-8'))\n"
            "os.close(ready)\n"
            "if os.read(go, 3) != b'go\\n':\n"
            "    sys.exit(125)\n"
            "os.close(go)\n"
            "os.execvp(sys.argv[4], sys.argv[4:])\n")
    # Reads until the owner speaks or dies; only an end without `done` kills. The scope's
    # cgroup, once the owner has passed it on, is killed directly; before that the scope
    # is killed by the name it was given before it existed, through a bounded systemctl.
    REAPER = ("import os, subprocess, sys\n"
              "said = sys.stdin.buffer.read().decode('utf-8', 'replace').splitlines()\n"
              "if 'done' not in said:\n"
              "    cgroups = [line[len('cgroup '):] for line in said if line.startswith('cgroup ')]\n"
              "    try:\n"
              "        with open(os.path.join(cgroups[0], 'cgroup.kill'), 'w') as fh:\n"
              "            fh.write('1')\n"
              "    except (IndexError, OSError):\n"
              "        try:\n"
              "            subprocess.run(['systemctl', '--user', 'kill', '--kill-who=all',\n"
              "                            '--signal=SIGKILL', sys.argv[1] + '.scope'],\n"
              "                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
              "                           timeout=float(sys.argv[2]))\n"
              "        except (OSError, subprocess.SubprocessError):\n"
              "            pass\n")

    def __init__(self):
        self.pgid = None
        self.unit = None
        self.cgroup = None
        self.reaper = None

    def start(self, argv, cwd, stdin, stdout, stderr, env):
        self.unit = "orch-%s" % uuid.uuid4().hex[:12]
        self.reaper = subprocess.Popen([sys.executable, "-c", self.REAPER, self.unit,
                                        str(SYSTEMCTL_SECONDS)],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
        ready_read, ready_write = os.pipe()
        go_read, go_write = os.pipe()
        try:
            try:
                # systemd-run execs the stub and the stub execs the agent, so the exit
                # status, stdio and working directory stay the agent's own.
                proc = subprocess.Popen(
                    ["systemd-run", "--user", "--scope", "--quiet", "--unit=" + self.unit,
                     sys.executable, "-c", self.STUB, str(ready_write), str(go_read), self.unit]
                    + list(argv),
                    cwd=cwd, stdin=stdin, stdout=stdout, stderr=stderr, env=env,
                    start_new_session=True, pass_fds=(ready_write, go_read))
            finally:
                os.close(ready_write)
                os.close(go_read)
        except BaseException:
            os.close(ready_read)
            os.close(go_write)
            self.close()
            raise
        self.pgid = proc.pid
        cgroup = _await_scope(ready_read, proc)
        os.close(ready_read)
        if cgroup is None:
            # Closing the go pipe stops a stub that comes up late; the kill ends one already up
            # and systemd-run's own process group, whatever state systemd is in.
            os.close(go_write)
            self.kill()
            try:
                proc.wait(timeout=GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            self.close()
            raise ExecutorError("no systemd user scope could hold the agent on this host, so it was "
                                "refused before it ran (systemd-run exited %s; its message is in the "
                                "role's .err log)" % proc.returncode)
        self.cgroup = "/sys/fs/cgroup" + cgroup
        # The reaper learns the cgroup before the agent starts, so from then on killing the
        # tree after our death needs no systemd.
        self._tell(("cgroup %s\n" % self.cgroup).encode("utf-8"))
        try:
            os.write(go_write, b"go\n")
        finally:
            os.close(go_write)
        return proc

    def _tell(self, line):
        try:
            self.reaper.stdin.write(line)
            self.reaper.stdin.flush()
        except OSError:
            pass

    def _pids(self):
        try:
            with open(os.path.join(self.cgroup, "cgroup.procs"), encoding="utf-8") as fh:
                return [int(line) for line in fh.read().split()]
        except OSError:
            return []

    def _signal(self, signum):
        # Every process in the scope, not only the process group we started.
        pids = self._pids() if self.cgroup else []
        for pid in pids:
            try:
                os.kill(pid, signum)
            except OSError:
                pass
        if not pids:
            try:
                os.killpg(self.pgid, signum)
            except OSError:
                pass

    def stop(self, proc):
        import signal
        self._signal(signal.SIGTERM)
        try:
            proc.wait(timeout=GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        self.kill()

    def kill(self):
        import signal
        if self.cgroup:
            try:
                with open(os.path.join(self.cgroup, "cgroup.kill"), "w", encoding="utf-8") as fh:
                    fh.write("1")
                return
            except OSError:
                pass                                     # the scope is already gone
        try:
            subprocess.run(["systemctl", "--user", "kill", "--kill-who=all", "--signal=SIGKILL",
                            self.unit + ".scope"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=SYSTEMCTL_SECONDS)
        except (OSError, subprocess.SubprocessError):
            pass
        self._signal(signal.SIGKILL)

    def close(self):
        """Release the reaper without letting it kill a scope whose name is done with."""
        if self.reaper is None:
            return
        self._tell(b"done\n")
        try:
            self.reaper.stdin.close()
        except OSError:
            pass
        try:
            self.reaper.wait(timeout=SYSTEMCTL_SECONDS + GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.reaper.kill()
            self.reaper.wait()
        self.reaper = None


def _await_scope(fd, proc):
    """The cgroup the stub reports from inside the agent's scope, or None if it never does."""
    deadline = time.monotonic() + SCOPE_SECONDS
    received = b""
    while b"\n" not in received:
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        readable, _, _ = select.select([fd], [], [], min(left, 0.5))
        if not readable:
            if proc.poll() is not None:
                return None                              # systemd-run gave up without a scope
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            return None
        received += chunk
    line = received.split(b"\n", 1)[0].decode("utf-8", "replace")
    return line[len("in "):] if line.startswith("in /") else None


class _WindowsProcess:
    """The part of `subprocess.Popen` a tree's owner uses, for a process created by `CreateProcessW`."""

    def __init__(self, kernel32, handle, pid, stdin, stdout, stderr):
        self.kernel32, self._handle, self.pid = kernel32, handle, pid
        self.stdin, self.stdout, self.stderr = stdin, stdout, stderr
        self.returncode = None

    def poll(self):
        return self.wait(timeout=0) if self.returncode is None else self.returncode

    def wait(self, timeout=None):
        if self.returncode is not None:
            return self.returncode
        millis = 0xFFFFFFFF if timeout is None else int(timeout * 1000)
        if self.kernel32.WaitForSingleObject(self._handle, millis) != 0:
            if timeout == 0:
                return None
            raise subprocess.TimeoutExpired("agent", timeout)
        import ctypes
        code = ctypes.c_ulong()
        self.kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code))
        self.returncode = code.value
        return self.returncode

    def kill(self):
        if self.returncode is None:
            self.kernel32.TerminateProcess(self._handle, 1)

    def __del__(self):
        try:
            self.kernel32.CloseHandle(self._handle)
        except Exception:                           # noqa: BLE001 - interpreter teardown
            pass


class _WindowsTree:
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008
    JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    SYNCHRONIZE = 0x00100000
    ERROR_MORE_DATA = 234
    WAIT_OBJECT_0 = 0
    WAIT_FAILED = 0xFFFFFFFF
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    CREATE_UNICODE_ENVIRONMENT = 0x00000400
    STARTF_USESTDHANDLES = 0x00000100
    PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
    PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
        self.kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                                          wintypes.LPVOID, wintypes.DWORD)
        self.kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        self.kernel32.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                                            wintypes.DWORD, wintypes.LPDWORD)
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self.kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        self.kernel32.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(ctypes.c_ulong))
        self.kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        self.kernel32.InitializeProcThreadAttributeList.argtypes = (
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t))
        self.kernel32.UpdateProcThreadAttribute.argtypes = (
            wintypes.LPVOID, wintypes.DWORD, ctypes.c_size_t, wintypes.LPVOID, ctypes.c_size_t,
            wintypes.LPVOID, ctypes.POINTER(ctypes.c_size_t))
        self.kernel32.DeleteProcThreadAttributeList.argtypes = (wintypes.LPVOID,)
        self.job = None

    def _check(self, ok, what):
        if not ok:
            raise OSError(self.ctypes.get_last_error(), "%s failed" % what)

    def _job(self):
        job = self.kernel32.CreateJobObjectW(None, None)
        self._check(job, "CreateJobObjectW")
        if not self._limit(job):
            self.kernel32.CloseHandle(job)
            self._check(False, "SetInformationJobObject")
        return job

    def _limit(self, job, closed=False):
        """Set the job's limits: kill on close always, and — once `closed` — no process may join it any more.
        True when set."""
        ctypes = self.ctypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                        ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", ctypes.c_uint32),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", ctypes.c_uint32),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", ctypes.c_uint32),
                        ("SchedulingClass", ctypes.c_uint32)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits),
                        ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if closed:
            # A process that would join is refused at its creation, before it runs (ERROR_NOT_ENOUGH_QUOTA).
            limits.BasicLimitInformation.LimitFlags |= self.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            limits.BasicLimitInformation.ActiveProcessLimit = 0
        return bool(self.kernel32.SetInformationJobObject(job, self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                          ctypes.byref(limits), ctypes.sizeof(limits)))

    def _stdio(self, value, reading, owned):
        """The child's inheritable handle for one stream, and the parent's end of a pipe or None."""
        import msvcrt
        if value == subprocess.PIPE:
            read_fd, write_fd = os.pipe()
            child_fd, parent_fd = (read_fd, write_fd) if reading else (write_fd, read_fd)
            os.set_inheritable(child_fd, True)
            owned.append(child_fd)
            return msvcrt.get_osfhandle(child_fd), os.fdopen(parent_fd, "wb" if reading else "rb")
        if value is None or value == subprocess.DEVNULL:
            fd = os.open(os.devnull, os.O_RDONLY if reading else os.O_WRONLY)
        else:
            fd = os.dup(value.fileno() if hasattr(value, "fileno") else value)
        os.set_inheritable(fd, True)
        owned.append(fd)
        return msvcrt.get_osfhandle(fd), None

    def start(self, argv, cwd, stdin, stdout, stderr, env):
        ctypes = self.ctypes
        from ctypes import wintypes

        class StartupInfo(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                        ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                        ("lpReserved2", wintypes.LPVOID), ("hStdInput", wintypes.HANDLE),
                        ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

        class StartupInfoEx(ctypes.Structure):
            _fields_ = [("StartupInfo", StartupInfo), ("lpAttributeList", wintypes.LPVOID)]

        class ProcessInformation(ctypes.Structure):
            _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                        ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

        self.job = self._job()
        owned, parents = [], []
        attributes = None
        created = False
        try:
            handles = []
            for value, reading in ((stdin, True), (stdout, False), (stderr, False)):
                handle, parent = self._stdio(value, reading, owned)
                handles.append(handle)
                parents.append(parent)
            size = ctypes.c_size_t(0)
            self.kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            attributes = ctypes.create_string_buffer(size.value)
            self._check(self.kernel32.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size)),
                        "InitializeProcThreadAttributeList")
            # The agent is born inside the job: nothing it starts can ever be outside it.
            jobs = (wintypes.HANDLE * 1)(self.job)
            self._check(self.kernel32.UpdateProcThreadAttribute(
                attributes, 0, self.PROC_THREAD_ATTRIBUTE_JOB_LIST, jobs, ctypes.sizeof(jobs), None, None),
                "UpdateProcThreadAttribute(job list)")
            # It inherits its three streams and no other handle of ours.
            inherited = (wintypes.HANDLE * len(set(handles)))(*sorted(set(handles)))
            self._check(self.kernel32.UpdateProcThreadAttribute(
                attributes, 0, self.PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited, ctypes.sizeof(inherited),
                None, None), "UpdateProcThreadAttribute(handle list)")
            info = StartupInfoEx()
            info.StartupInfo.cb = ctypes.sizeof(info)
            info.StartupInfo.dwFlags = self.STARTF_USESTDHANDLES
            info.StartupInfo.hStdInput, info.StartupInfo.hStdOutput, info.StartupInfo.hStdError = handles
            info.lpAttributeList = ctypes.cast(attributes, wintypes.LPVOID)
            block = None
            if env is not None:
                block = ctypes.create_unicode_buffer(
                    "".join("%s=%s\0" % (key, value) for key, value in env.items()) + "\0")
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(argv)))
            process = ProcessInformation()
            self.kernel32.CreateProcessW.argtypes = (
                wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID, wintypes.LPVOID, wintypes.BOOL,
                wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR, wintypes.LPVOID, wintypes.LPVOID)
            ok = self.kernel32.CreateProcessW(
                None, command, None, None, True,
                self.EXTENDED_STARTUPINFO_PRESENT | self.CREATE_UNICODE_ENVIRONMENT,
                ctypes.cast(block, wintypes.LPVOID) if block is not None else None, cwd,
                ctypes.byref(info), ctypes.byref(process))
            if not ok:
                raise OSError(ctypes.get_last_error(), "CreateProcessW failed for %s" % argv[0])
            created = True
        finally:
            if not created:
                # Nothing was started: our pipe ends and the job go with the attempt.
                for parent in parents:
                    if parent is not None:
                        parent.close()
                self.close()
            if attributes is not None:
                self.kernel32.DeleteProcThreadAttributeList(attributes)
            for fd in owned:
                os.close(fd)
        self.kernel32.CloseHandle(process.hThread)
        return _WindowsProcess(self.kernel32, process.hProcess, process.dwProcessId, *parents)

    def stop(self, proc):
        # A console process gets no signal it must handle; the job ends the tree.
        self.kill()
        try:
            proc.wait(timeout=GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass

    def kill(self):
        """End every process of the tree and return once each has ended — or raise, when that is not
        proved within GRACE_SECONDS, so nothing goes on as though the tree were gone."""
        if not self.job:
            return
        # Termination only begins the end: a process has its exit code while it still holds its handles —
        # the directory it worked in among them, which Windows then refuses to remove — and the job drops
        # every process from its own list the moment it is terminated, so none can be found afterwards
        # (measured). The job is closed to newcomers first; each process it lists then — running, or
        # ending by itself, which it lists until its handles are released — is held, and waited for once
        # the job is terminated.
        held = {}
        try:
            try:
                self._check(self._limit(self.job, closed=True), "SetInformationJobObject")
                self._hold(held)
            finally:
                terminated = self.kernel32.TerminateJobObject(self.job, 1)
            self._check(terminated, "TerminateJobObject")
            self._wait(held, time.monotonic() + GRACE_SECONDS)
        finally:
            for handle in held.values():
                self.kernel32.CloseHandle(handle)

    def _hold(self, held):
        """Take hold of each process the job lists, by id, to wait on. One that cannot be opened needs no
        wait only when the job no longer lists it — it has ended, and closed to newcomers, the job takes no
        other under its id; otherwise its end cannot be proved."""
        for pid in self._pids():
            if pid in held:
                continue
            handle = self.kernel32.OpenProcess(self.SYNCHRONIZE, False, pid)
            if handle:
                held[pid] = handle
                continue
            error = self.ctypes.get_last_error()
            if pid in self._pids():
                raise OSError(error, "OpenProcess failed for process %d, still in the agent's job" % pid)

    def _pids(self):
        """The processes in the job now, by id."""
        ctypes = self.ctypes
        from ctypes import wintypes
        room = 64
        while True:
            class IdList(ctypes.Structure):
                _fields_ = [("assigned", wintypes.DWORD), ("listed", wintypes.DWORD),
                            ("ids", ctypes.c_size_t * room)]
            ids = IdList()
            if self.kernel32.QueryInformationJobObject(self.job, self.JOB_OBJECT_BASIC_PROCESS_ID_LIST,
                                                       ctypes.byref(ids), ctypes.sizeof(ids), None):
                return list(ids.ids[:ids.listed])
            self._check(ctypes.get_last_error() == self.ERROR_MORE_DATA, "QueryInformationJobObject")
            room = max(room * 2, ids.assigned)

    def _wait(self, held, deadline):
        """Each held process ended by `deadline`; TimeoutError naming one that has not."""
        for pid, handle in held.items():
            waited = self.kernel32.WaitForSingleObject(handle, int(max(0.0, deadline - time.monotonic()) * 1000))
            self._check(waited != self.WAIT_FAILED, "WaitForSingleObject")
            if waited != self.WAIT_OBJECT_0:
                raise TimeoutError("the agent's process tree did not end within %ds of its kill: process %d is "
                                   "still there" % (GRACE_SECONDS, pid))

    def close(self):
        if self.job:
            # Kill-on-close: this also ends anything still inside.
            self.kernel32.CloseHandle(self.job)
            self.job = None


_Tree = _WindowsTree if WINDOWS else _PosixTree
