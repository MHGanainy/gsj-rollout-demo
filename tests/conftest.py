"""Shared fakes for the demo's suite (library CP-96)."""
import io
import subprocess
import time


class FakePull:
    """A fake for bootstrap.py's `popen` seam: docker's stdout lines delivered
    live to the drainer, a delay before the process exits, its stderr text
    and its return code — so ensure_image's heartbeat, phase tally and
    verdict can be exercised without a daemon."""

    def __init__(self, cmd, returncode=0, lines=(), stderr="", delay=0.0):
        self.args, self._final, self._deadline = cmd, returncode, time.monotonic() + delay
        self.returncode = None
        self.stdout = iter(list(lines))
        self.stderr = io.StringIO(stderr)

    def wait(self, timeout=None):
        remaining = self._deadline - time.monotonic()
        if timeout is not None and remaining > timeout:
            time.sleep(timeout)
            raise subprocess.TimeoutExpired(self.args, timeout)
        if remaining > 0:
            time.sleep(remaining)
        self.returncode = self._final
        return self.returncode
