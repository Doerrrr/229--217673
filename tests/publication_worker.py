"""Untrusted execution side of the publisher protocol; contains no expectations."""
import base64
import importlib
import json
import os
import sys
import threading
from pathlib import Path

protocol = os.fdopen(int(os.environ["PUBLICATION_PROTOCOL_FD"]), "w", buffering=1)
sys.path.insert(0, "/opt/ddi-curator")
module = importlib.import_module("publication")


def send(message):
    protocol.write(json.dumps(message) + "\n")


def encode(snapshot):
    if snapshot is None:
        return None
    result = dict(snapshot)
    result["artifacts"] = {k: base64.b64encode(v).decode("ascii") for k, v in snapshot["artifacts"].items()}
    return result


send({"kind": "ready"})
for line in sys.stdin:
    request = json.loads(line)
    try:
        root = Path(request["root"]) if request.get("pathlike") else request["root"]
        if request["op"] == "read":
            answer = encode(module.read_current(root))
        elif request["op"] == "threads":
            barrier = threading.Barrier(2)
            answers = []

            def race(item):
                data = {k: base64.b64decode(v) for k, v in item["artifacts"].items()}
                barrier.wait(timeout=5)
                try:
                    result = module.publish(root, item["id"], item["parent"], data)
                    answers.append({"id": item["id"], "ok": True, "answer": result})
                except BaseException as exc:
                    answers.append({"id": item["id"], "ok": False})

            threads = [threading.Thread(target=race, args=(item,)) for item in request["requests"]]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            if any(thread.is_alive() for thread in threads):
                raise RuntimeError("threaded publication did not finish")
            answer = answers
        else:
            payloads = {k: base64.b64decode(v) for k, v in request["artifacts"].items()}
            if request.get("bad_value"):
                payloads["report.json"] = "not bytes"
            before = dict(payloads)

            def hook(event, detail):
                send({"kind": "hook", "event": event, "detail": detail})
                if event == request.get("raise_at"):
                    raise RuntimeError("publication-probe-fault")
                if event == request.get("pause_at"):
                    if sys.stdin.readline().strip() != "continue":
                        raise RuntimeError("probe release missing")

            answer = module.publish(root, request["id"], request.get("parent"), payloads,
                                    123 if request.get("bad_hook") else hook if request.get("hooks") else None)
            if payloads != before:
                raise RuntimeError("caller mapping was mutated")
        send({"kind": "result", "ok": True, "answer": answer})
    except BaseException as exc:
        send({"kind": "result", "ok": False, "error": type(exc).__name__ + ": " + str(exc)})
