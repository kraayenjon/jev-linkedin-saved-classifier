"""Read-loop recovery, with Chrome faked. Run: uv run python tests/test_read.py"""

from contextlib import nullcontext
from unittest import mock

from jev_linkedin_saved import cli


def run(steps, visibility=("visible",)):
    """steps: per call, 'post' (reads one post), 'timeout', 'ctrl-c' or 'end'."""
    steps, seen = iter(steps), iter(visibility)

    def step(target, session, i, posts, order, still):
        kind = next(steps)
        if kind == "timeout":
            raise TimeoutError
        if kind == "ctrl-c":
            raise KeyboardInterrupt
        if kind == "end":
            return None
        posts[str(i)] = {"activity_urn": str(i)}
        order.append(str(i))
        return 0

    with mock.patch.object(cli, "attached", lambda t: nullcontext("S")), \
         mock.patch.object(cli, "read_step", step), \
         mock.patch.object(cli, "evaluate", lambda s, e: next(seen)), \
         mock.patch.object(cli.time, "sleep"):
        rows, stopped_early = cli.read_all("T", 50)
    return len(rows), stopped_early


assert run(["post", "post", "end"]) == (2, False)
# the tab was hidden once: wait for it, then carry on to the end
assert run(["post", "timeout", "post", "end"], visibility=("hidden", "hidden", "visible")) == (2, False)
# Chrome keeps timing out: keep what was read
assert run(["post", "timeout", "timeout", "timeout"], visibility=("visible",) * 3) == (1, True)
# Ctrl+C keeps what was read
assert run(["post", "post", "ctrl-c"]) == (2, True)
print("ok")
