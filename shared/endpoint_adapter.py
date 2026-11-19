"""STAND-IN adapter: lets Roshan's PolicyWorker call the stand-in HTTP endpoint.

Standard library only, no torch: this runs inside the control loop's policy worker.

    import endpoint_adapter
    worker = PolicyWorker(factory=endpoint_adapter.make_policy)

The factory takes no arguments (PolicyWorker calls it inside the child process),
so the address and timeout come from environment variables:
    STANDIN_POLICY_URL      default http://127.0.0.1:8765
    STANDIN_POLICY_TIMEOUT  default 5 (seconds; the last of up to three tries, see post())
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8765"
# Longer than the supervisor's 3 s policy budget on purpose: the supervisor should be the one
# that records `policy_timeout`. This timeout only stops the worker from waiting forever.
DEFAULT_TIMEOUT_SECONDS = 5.0
# How long the first tries of one request may take before a new connection is tried (see post()).
# The last try gets the long timeout above, so a request that keeps failing is still recorded
# by the supervisor as `policy_timeout` at 3 s.
FIRST_TRIES_SECONDS = (1.0, 1.0)


class EndpointPolicy:
    """Same reset(request)/predict(request) shape as ScriptedPolicy, but the work is a POST."""

    def __init__(self, url=None, timeout=None):
        self.url = (url or os.environ.get("STANDIN_POLICY_URL", DEFAULT_URL)).rstrip("/")
        self.timeout = float(timeout or os.environ.get("STANDIN_POLICY_TIMEOUT",
                                                       DEFAULT_TIMEOUT_SECONDS))
        # An empty ProxyHandler means "talk to the server directly". Without it urllib
        # would use a system HTTP proxy if one is configured, even for 127.0.0.1.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def reset(self, request):
        return self.post("/reset", request)

    def predict(self, request):
        return self.post("/predict", request)

    def post(self, path, request):
        """Send the envelope unchanged, return the reply envelope unchanged.

        Raises on a timeout, a refused connection or a non-200 answer. It never invents a
        reply: inside PolicyWorker an exception becomes a `policy_error`, not a noop.
        """
        http_request = urllib.request.Request(
            self.url + path, data=json.dumps(request).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        # Up to three tries, each on a new connection; the first two give up after 1 s. Why: on 2026-11-18 a request sometimes never reached the server's policy
        # code (its log had no line for it) although the call before it took under 0.1 s.
        # A retry is written to stderr (it ends up in the run's bridge.log) so it can be counted.
        limits = FIRST_TRIES_SECONDS + (self.timeout,)
        for attempt, seconds in enumerate(limits, start=1):
            try:
                with self.opener.open(http_request, timeout=seconds) as http_reply:
                    return json.loads(http_reply.read())
            except urllib.error.HTTPError as error:
                # e.g. 422 when the server rejected the request. Keep the server's message.
                detail = error.read().decode("utf-8", "replace")
                raise RuntimeError(f"Endpoint {path} answered HTTP {error.code}: {detail}") from error
            except OSError as error:            # no connection or no answer within `seconds`
                print(f"endpoint_adapter: try {attempt} of {path} decision {request.get('decision_id')} "
                      f"failed after {seconds} s: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
                if attempt == len(limits):
                    raise


def make_policy():
    """Module-level factory for PolicyWorker(factory=...). It must be importable by name
    because the spawned worker process receives it by pickling."""
    return EndpointPolicy()
