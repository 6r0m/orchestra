"""Run one agent in a pseudo-terminal and carry that terminal over this process's own pipes.

    python app/agents/ptyhost.py <cols> <rows> -- <argv...>

`launch.py` starts this process inside the agent's containment, so the agent — its child —
and everything the agent starts share that containment. Bytes arriving on stdin are the
terminal's keyboard; everything the terminal draws leaves on stdout. The exit status is
the agent's own.

On Windows the terminal is a ConPTY, which asks its terminal for win32-input-mode. Codex
reads Windows key events there and ignores a bare ESC byte, so a lone ESC arriving on
stdin is sent as the Esc key's down and up events.
"""
import os
import sys
import threading

WINDOWS = sys.platform.startswith("win")
# win32-input-mode: ESC [ Vk ; Sc ; Uc ; Kd ; Cs ; Rc _ — the Esc key pressed, then released.
WINDOWS_ESC = "\x1b[27;1;27;1;0;1_\x1b[27;1;27;0;0;1_"


def _stdin_chunks():
    stdin = sys.stdin.buffer.raw if hasattr(sys.stdin.buffer, "raw") else sys.stdin.buffer
    while True:
        data = stdin.read(65536)
        if not data:
            return
        yield data


def _out(data):
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def windows(argv, cols, rows):
    from winpty import PtyProcess
    pty = PtyProcess.spawn(argv, cwd=os.getcwd(), env=dict(os.environ), dimensions=(rows, cols))

    def keyboard():
        import codecs
        # A character split across two reads is decoded whole.
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        for data in _stdin_chunks():
            text = decoder.decode(data)
            if text:
                pty.write(WINDOWS_ESC if text == "\x1b" else text)

    threading.Thread(target=keyboard, daemon=True).start()
    while True:
        try:
            text = pty.read(65536)
        except EOFError:
            break
        if text:
            _out(text.encode("utf-8"))
    return pty.wait()


def posix(argv, cols, rows):
    import fcntl
    import struct
    import subprocess
    import termios
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def controlling_terminal():
        # A session of its own with the pty as its controlling terminal, as a real terminal gives.
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, preexec_fn=controlling_terminal)
    os.close(slave)

    def keyboard():
        for data in _stdin_chunks():
            os.write(master, data)

    threading.Thread(target=keyboard, daemon=True).start()
    import select
    while True:
        # A descendant can hold the pty open after the agent exits, so its exit also ends the relay.
        ready, _, _ = select.select([master], [], [], 0.2)
        if not ready:
            if proc.poll() is not None:
                break
            continue
        try:
            data = os.read(master, 65536)
        except OSError:
            break
        if not data:
            break
        _out(data)
    return proc.wait()


def main(args):
    if len(args) < 4 or args[2] != "--":
        sys.exit("usage: python app/agents/ptyhost.py <cols> <rows> -- <argv...>")
    cols, rows, argv = int(args[0]), int(args[1]), args[3:]
    rc = (windows if WINDOWS else posix)(argv, cols, rows)
    sys.stdout.flush()
    return rc if isinstance(rc, int) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
