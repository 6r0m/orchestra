"""How the suite runs, for both scripts and for `python -m tests`.

    python -m tests [what python -m unittest takes]     one process, as `python -m unittest` runs it
    python -m tests --parallel [test names]             each test class of the names — or of the whole
                                                        suite — in a process of its own, AT_ONCE at a time

A process watches for an exit that does not come: once its tests have finished, the interpreter has
EXIT_SECONDS to exit, and past that every thread's stack is written to its output. A parallel run bounds
each class besides: one still running at CLASS_SECONDS has had its threads dumped a little before, and
then its process tree is ended and it fails the run. A run that ran no tests, or fewer than it found,
fails too; and however it ends, no class of it is left running.

Every class leaves the run through one end, whether it finished, hung or the run was interrupted, so
nothing it started outlives it. On Windows each class is born into a job of its own, the agents'
launcher's (`app.agents.launch`), so every process it starts is in it, one whose parent has gone
included; its end returns only once each of those has ended, and a class whose end is not proved fails.
A POSIX class is its own process group, which one signal ends.
"""
import faulthandler
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
EXIT_SECONDS = 60
# The longest one class may run: the slowest takes under a minute.
CLASS_SECONDS = 600
# How long before its end a class still running dumps every thread — where it hangs.
DUMP_BEFORE = 15
# Quick, and few enough that the tests bounding their own time keep their margin.
AT_ONCE = min(os.cpu_count() or 1, 8)
# Set for a class of a parallel run: when it dumps its threads, in seconds from its start.
DUMP_AT = "TESTS_DUMP_AT"
FAILED_LOAD = "unittest.loader._FailedTest."
# How long an ended process tree may take to go before the run stops waiting on it.
END_SECONDS = 30


def main(argv):
    # What a child printed reaches this console whole, whatever its encoding cannot show.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    if argv[:1] == ["--parallel"]:
        return parallel(argv[1:])
    return serial(argv)


def serial(argv):
    """One process, as `python -m unittest argv` runs it."""
    if os.environ.get(DUMP_AT):
        faulthandler.dump_traceback_later(float(os.environ[DUMP_AT]))
    program = unittest.main(module=None, argv=["python -m tests"] + argv, exit=False)
    faulthandler.dump_traceback_later(EXIT_SECONDS)
    if not program.result.testsRun:
        print("no tests ran", file=sys.stderr)
        return 5
    return 0 if program.result.wasSuccessful() else 1


def parallel(names, start=None, top=PKG, at_once=AT_ONCE, limit=CLASS_SECONDS, dump_before=DUMP_BEFORE,
             out=None):
    """Each class the names hold — or discovery finds under `start` — in a process of its own, at most
    `at_once` at a time, each printed whole when it ends. 0 only when every class passed and ran every
    test it holds; 130 when interrupted."""
    flags = [name for name in names if name.startswith("-")]
    if flags:
        print("a parallel run takes test names only, not %s" % " ".join(flags), file=sys.stderr)
        return 5
    try:
        found = classes(names, start or os.path.join(top, "tests"), top)
    except LookupError as exc:
        print(exc.args[0], file=sys.stderr)
        return 5
    out = out or os.path.join(PKG, "tmp", "tests", "windows" if os.name == "nt" else "posix")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    env = child_env(top, limit - dump_before)
    pending, running, results, began = list(found), {}, [], time.monotonic()
    handlers = interrupted_by_signals()
    try:
        while pending or running:
            while pending and len(running) < at_once:
                name, count = pending.pop(0)
                log = open(os.path.join(out, name + ".log"), "w+b")
                child, tree = start_class([sys.executable, "-m", "tests", name], env, log)
                running[name] = (child, tree, log, count, time.monotonic())
            time.sleep(0.1)
            for name, (child, tree, log, count, started) in list(running.items()):
                seconds = time.monotonic() - started
                hung = child.poll() is None and seconds >= limit
                if child.poll() is None and not hung:
                    continue
                # What a finished class left running ends with it, as a hung one's does.
                unended = end(child, tree)
                del running[name]
                results.append(finished(name, count, child.returncode, log, seconds, hung, unended))
    except KeyboardInterrupt:
        ending = len(running)
        unended = end_all(running)
        print("\ninterrupted: ended the %d classes still running" % ending if not unended else
              "\ninterrupted: %d classes were still running, and the end of %d of them was not proved"
              % (ending, len(unended)), file=sys.stderr)
        return 130
    finally:
        # However else this run ends, no class of it goes on running, detached from its terminal.
        end_all(running)
        restore(handlers)
    return summary(results, time.monotonic() - began)


def child_env(top, dump_at):
    """A class process's environment. The checkout is found as `python -m tests` finds it, never through
    PYTHONPATH, which every process the class starts would inherit — the agents' launched-by-path files
    among them, which must import nothing of ours; only a folder of stand-ins is added."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", **{DUMP_AT: str(max(1, dump_at))})
    if os.path.normcase(os.path.abspath(top)) != os.path.normcase(PKG):
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [top, os.environ.get("PYTHONPATH")]))
    return env


def classes(names, start, top):
    """[(unittest name, how many tests it holds)], most tests first. A class is the unit; a name narrower
    than a class is its own entry, and a module that does not load is one, which fails when it runs. A
    name that holds no test at all is a LookupError."""
    if top not in sys.path:
        sys.path.insert(0, top)
    loader = unittest.TestLoader()
    found, seen = {}, set()
    for name in names or [None]:
        if name is None:
            suite = loader.discover(start, pattern="test_*.py", top_level_dir=top)
        else:
            name = dotted(name, top)
            try:
                suite = loader.loadTestsFromName(name)
            except Exception:                       # noqa: BLE001 - its own process says why it does not load
                found.setdefault(name, 1)
                continue
            if not any(True for _ in flatten(suite)):
                raise LookupError("no tests in %s" % name)
        for test in flatten(suite):
            if test.id() in seen:
                continue
            seen.add(test.id())
            if test.id().startswith(FAILED_LOAD):
                # Named, the name itself: unittest keeps only its last part, and would name another module.
                entry = name or test.id()[len(FAILED_LOAD):]
            else:
                entry = test.id().rsplit(".", 1)[0]
                if name and name.startswith(entry + "."):
                    entry = name
            found[entry] = found.get(entry, 0) + 1
    if not found:
        raise LookupError("no tests found")
    return sorted(found.items(), key=lambda item: -item[1])


def dotted(name, top):
    """A test file's path as the module name unittest would give it; any other name as it is."""
    path = os.path.abspath(name)
    if name.lower().endswith(".py") and os.path.isfile(path):
        relative = os.path.relpath(path, top)
        if not relative.startswith(os.pardir):
            return relative[:-3].replace(os.sep, ".").replace("/", ".")
    return name


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def finished(name, count, code, log, seconds, hung, unended=None):
    """One line for a class that passed; its whole output, once, for one that did not. `unended` is why the
    end of what it left running was not proved, which fails it."""
    log.seek(0)
    text = log.read().decode("utf-8", "replace")
    log.close()
    ran = re.findall(r"^Ran (\d+) tests? in ", text, re.MULTILINE)
    ran = int(ran[-1]) if ran else 0
    if hung:
        verdict = "HUNG — ended after %d s" % seconds
    elif code != 0:
        verdict = "FAILED"
    elif ran != count:
        verdict = "FAILED — ran %d of its %d tests" % (ran, count)
    else:
        verdict = "ok"
    if unended:
        said = "its processes were not proved ended: %s" % unended
        verdict = "FAILED — " + said if verdict == "ok" else verdict + "; " + said
    print("%7.1f s  %s — %s" % (seconds, name, verdict), flush=True)
    if verdict != "ok":
        print(text.rstrip() + "\n" + "-" * 70, flush=True)
    return {"name": name, "ok": verdict == "ok", "seconds": seconds, "tests": ran}


def summary(results, wall):
    slowest = max(results, key=lambda result: result["seconds"])
    print("\n%d classes, %d tests: %.1f s wall, %.1f s summed; slowest %s, %.1f s"
          % (len(results), sum(result["tests"] for result in results), wall,
             sum(result["seconds"] for result in results), slowest["name"], slowest["seconds"]))
    failed = [result["name"] for result in results if not result["ok"]]
    print("FAILED: %s" % ", ".join(failed) if failed else "OK", flush=True)
    return 1 if failed else 0


def start_class(argv, env, log):
    """A class's process, writing to `log`, and the job its whole tree is born into — None off Windows.

    It is in a group of its own either way, so no terminal's interrupt reaches it: the run ends what it
    runs, once."""
    if os.name == "nt":
        # Only here, so a class's own process and a POSIX run import nothing of the checkout's.
        from app.agents import launch
        tree = launch._WindowsTree()
        return tree.start(argv, PKG, subprocess.DEVNULL, log, log, env,
                          flags=subprocess.CREATE_NEW_PROCESS_GROUP), tree
    return subprocess.Popen(argv, cwd=PKG, env=env, stdin=subprocess.DEVNULL, stdout=log,
                            stderr=subprocess.STDOUT, start_new_session=True), None


def end(child, tree=None):
    """End a class's process tree, and wait for it — never for good. None once its end is proved; else why
    not, for the class to fail on."""
    try:
        end_tree(child, tree)
        child.wait(END_SECONDS)
    except (OSError, TimeoutError, subprocess.TimeoutExpired) as exc:
        return "process %d, within %d s: %s" % (child.pid, END_SECONDS, exc)
    return None


def end_all(running):
    """End every class still running; the names of those whose end was not proved, each said."""
    unended = []
    for name, (child, tree, log, _, _) in running.items():
        why = end(child, tree)
        if why:
            print("  %s: its processes were not proved ended: %s" % (name, why), file=sys.stderr, flush=True)
            unended.append(name)
        log.close()
    running.clear()
    return unended


def end_tree(child, tree=None):
    """End a process and every process it started.

    Through the job it was born into, when it has one: this returns once each process of the job has
    ended, and raises when that is not proved within END_SECONDS. A process with no job is ended by
    walking its tree on Windows, which misses any whose parent has gone, and by its group elsewhere."""
    if tree is not None:
        try:
            tree.kill(grace=END_SECONDS)
        finally:
            tree.close()
    elif os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def on_main_thread():
    return threading.current_thread() is threading.main_thread()


def interrupted_by_signals():
    """An interrupt — and a termination, a hang-up or a Ctrl+Break where the host has them — ends the run
    one way, once: the first ignores every later one, so nothing cuts short the ending of the classes still
    running; `uv run` passes a terminal's interrupt on twice. Returns the handlers to put back."""
    if not on_main_thread():
        return {}
    numbers = [signal.SIGINT] + [getattr(signal, name) for name in
                                 (("SIGBREAK",) if os.name == "nt" else ("SIGTERM", "SIGHUP"))
                                 if hasattr(signal, name)]
    kept = {number: signal.getsignal(number) for number in numbers}

    def interrupt(number, frame):
        for each in numbers:
            signal.signal(each, signal.SIG_IGN)
        raise KeyboardInterrupt
    for number in numbers:
        signal.signal(number, interrupt)
    return kept


def restore(handlers):
    for number, handler in handlers.items():
        signal.signal(number, handler)
