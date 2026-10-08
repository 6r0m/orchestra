"""Choosing a port for a process the suite is about to start, to be handed to it through a policy file.

The stack's own tests, the stale-settings sweep and the acceptance each start real processes that have
to be told where to listen, so the choice belongs to none of those concerns and lives at this root.
What the choice promises, and what it deliberately does not, is `port_for_another_process`'s own to
say: it picks a port free at that moment and lets it go again.
"""
import socket


def port_for_another_process(used):
    """A port another process will bind, told its number through a policy: free now, then let go, so
    something else may take it first. Never one in `used`, the policy's ports so far, which it then joins.
    A socket this process holds binds port 0 instead."""
    for _ in range(10):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if port not in used:
            used.add(port)
            return port
    raise OSError("no free port apart from %s" % sorted(used))
