#!/usr/bin/env python3
"""STAND-IN policy endpoint for local Team D testing. Not Team C's endpoint.

Speaks Roshan's EVAL-01 protocol v1 (scripts/control_loop/protocol.py) over HTTP:
    GET  /health   -> {"status": "ok", "policy": ..., "protocol_version": 1, "source": "standin"}
    GET  /stats    -> how often each glue rule fired since the server started
    POST /reset    -> request envelope in, response envelope out
    POST /predict  -> request envelope in, response envelope out

Run from the repository root:  python standin_infer/server.py --policy scripted
"""

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]      # the repository root (team-c/)
sys.path.insert(0, str(ROOT / "scripts"))       # for control_loop (Roshan's code)
sys.path.insert(0, str(ROOT))                   # for bar_policy (Team B's code)
from control_loop.protocol import (DECISION, VERSION, PolicyError, ProtocolError,
                                   response, validate_request, validate_response)
from control_loop.scripted_policy import ScriptedPolicy

HOST = "127.0.0.1"                              # local only, never 0.0.0.0
DEFAULT_PORT = 8765
DEFAULT_CHECKPOINT = ROOT.parent / "shared" / "ckpt" / "b03-h1" / "h1_best.pt"
DEFAULT_MAP = "Great Divide V1"                 # the map of both the checkpoint's data and Roshan's fixture
log = logging.getLogger("standin_infer")


def order_to_action(order, request, fired):
    """Glue rules 1-4 of shared/CONTRACT.md: one decoded model order -> one protocol action.

    `order` is what bar_policy.training.predict_orders returns for one row (or None).
    `request` is the validated request. `fired` is a Counter of the rules that changed something.
    """
    def fire(rule, detail):
        fired[rule] += 1
        log.info("glue %s: decision %s: %s", rule, request["decision_id"], detail)

    # Rule 1: the model had no order (no own units in the observation) -> explicit noop.
    if order is None:
        fire("rule1_none_to_noop", "model returned None")
        return {"kind": "noop"}

    # Rule 2: the protocol takes one recipient, the model gives a list.
    # Keep the first id that is an observed unit owned by team_id (the same test validate_response uses).
    owned = {unit["id"]: unit for unit in request["observation"]["units"]
             if unit["teamID"] == request["team_id"]}
    unit_id = next((uid for uid in order["unit_ids"] if uid in owned), None)
    if unit_id is None:
        fire("rule2_no_owned_recipient_to_noop", f"dropped {order['unit_ids']}")
        return {"kind": "noop"}
    dropped = [uid for uid in order["unit_ids"] if uid != unit_id]
    if dropped:
        fire("rule2_dropped_recipients", f"kept {unit_id}, dropped {dropped}")

    # Rule 3: the model leaves height (y) as None. Use the recipient's observed height instead.
    params = list(order["params"])
    if None in params:
        height = owned[unit_id]["position"][1]
        params = [height if value is None else value for value in params]
        fire("rule3_none_y_to_unit_height", f"y = {height}")

    # Rule 4: command_id, unit_id and options must be real ints. Everything else passes through.
    ids = (order["command_id"], unit_id, order["options"])
    if any(type(value) is not int for value in ids):
        fire("rule4_cast_to_int", f"{ids}")
    return {"kind": "order", "unit_id": int(unit_id), "command_id": int(order["command_id"]),
            "params": params, "options": int(order["options"])}


class NoopPolicy:
    """Always answers noop. response() fills in {"kind": "noop"} when no action is given."""

    def reset(self, request):
        return response(request)

    def predict(self, request):
        return response(request)


class ModelPolicy:
    """Team B's B03 H=1 checkpoint behind the protocol. The glue rules live in order_to_action."""

    def __init__(self, checkpoint, map_name, fired):
        # torch is imported here, not at the top, so scripted and noop run without it.
        from bar_policy.training import load_checkpoint, predict_orders
        self.encoder, self.decoder, self.feature_spec, self.action_spec, _ = load_checkpoint(
            str(checkpoint), device="cpu")
        self.predict_orders = predict_orders
        self.map_name = map_name
        self.fired = fired

    def reset(self, request):
        return response(request)    # H=1: the model keeps no history, so there is nothing to clear

    def predict(self, request):
        # A bare observation is a valid "row" for predict_orders. One row in, one order out.
        order = self.predict_orders(self.encoder, self.decoder, self.feature_spec, self.action_spec,
                                    [request["observation"]], map_name=self.map_name)[0]
        return response(request, order_to_action(order, request, self.fired))


def build_policy(name, fired, checkpoint=DEFAULT_CHECKPOINT, map_name=DEFAULT_MAP):
    if name == "scripted":
        return ScriptedPolicy()     # Roshan's policy, unchanged
    if name == "noop":
        return NoopPolicy()
    if name == "model":
        return ModelPolicy(checkpoint, map_name, fired)
    raise ValueError(f"Unknown policy: {name}")


def error_reply(request, message):
    """Same shape as examples/control_loop/error_response.json: echo the identifiers, status error."""
    reply = {key: request[key] for key in DECISION}
    reply.update(op=request["op"], status="error", error=message)
    return reply


class Handler(BaseHTTPRequestHandler):
    # The server object carries the shared state: policy, policy_name, sleep_ms, fired, lock.

    def send_json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        log.debug("%s %s", self.address_string(), format % args)   # one line per request, off by default

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "policy": self.server.policy_name,
                                 "protocol_version": VERSION, "source": "standin"})
        elif self.path == "/stats":
            self.send_json(200, {"source": "standin", "policy": self.server.policy_name,
                                 "glue_rules_fired": dict(self.server.fired)})
        else:
            self.send_json(404, {"error": f"Unknown path {self.path}"})

    def do_POST(self):
        if self.path not in ("/reset", "/predict"):
            self.send_json(404, {"error": f"Unknown path {self.path}"})
            return
        op = self.path[1:]
        # Step 1: read and validate the request. Anything wrong here is the caller's fault -> 422.
        try:
            length = int(self.headers.get("Content-Length", 0))
            request = validate_request(json.loads(self.rfile.read(length)))
            if request["op"] != op:
                raise ProtocolError(f"op {request['op']!r} was sent to /{op}")
        except ValueError as error:     # ProtocolError and bad JSON are both ValueErrors
            log.warning("422 on /%s: %s", op, error)
            self.send_json(422, {"error": str(error)})
            return
        # Step 2: run the policy and check our own reply. Anything wrong here is our fault ->
        # an explicit status "error" reply (glue rule 5). It is never turned into a noop.
        try:
            with self.server.lock:      # one decision at a time: the policies keep state
                if op == "predict" and self.server.sleep_ms:
                    time.sleep(self.server.sleep_ms / 1000)
                reply = self.server.policy.reset(request) if op == "reset" \
                    else self.server.policy.predict(request)
            validate_response(request, reply)
        except PolicyError:
            pass    # the policy itself returned a well-formed status "error" reply: send it as is
        except Exception as error:
            log.warning("policy error on /%s decision %s: %s", op, request["decision_id"], error)
            reply = error_reply(request, f"{type(error).__name__}: {error}")
        self.send_json(200, reply)


def make_server(policy, policy_name, port=DEFAULT_PORT, sleep_ms=0, fired=None):
    """Build the HTTP server without starting it. port=0 asks the OS for a free port (tests)."""
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.daemon_threads = True    # a request stuck in --sleep-ms must not block shutdown
    server.policy = policy
    server.policy_name = policy_name
    server.sleep_ms = sleep_ms
    server.fired = fired if fired is not None else Counter()
    server.lock = threading.Lock()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", choices=("scripted", "model", "noop"), required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--sleep-ms", type=int, default=0,
                        help="artificial delay added to every predict (to test timeouts)")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--map-name", default=DEFAULT_MAP)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    fired = Counter()
    policy = build_policy(args.policy, fired, args.checkpoint, args.map_name)
    server = make_server(policy, args.policy, args.port, args.sleep_ms, fired)
    log.info("STAND-IN endpoint: policy=%s on http://%s:%s (Ctrl+C stops it)",
             args.policy, HOST, server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
