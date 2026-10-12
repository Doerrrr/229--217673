"""Trusted expectations and deterministic multiprocess publication probes."""
from __future__ import annotations
import base64
import hashlib
import json
import os
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

NAMES = ("drugs_clean.csv", "interaction_delta.csv", "interactions_clean.csv", "report.json")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def drop_privileges():
    if os.getuid() == 0:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)


def writable(path):
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o777)


def payloads(label):
    # The parent retains the expected bytes; no expected digest/score enters the worker.
    token = os.urandom(13).hex()
    return {name: (f"{name}:{label}:{token}\n").encode() for name in NAMES}


def request(root, ident, parent, data, **options):
    return {"op": "publish", "root": str(root), "id": ident, "parent": parent,
            "artifacts": {k: base64.b64encode(v).decode("ascii") for k, v in data.items()}, **options}


class Worker:
    def __init__(self):
        source = Path(__file__).with_name("publication_worker.py").read_text(encoding="utf-8")
        read_fd, write_fd = os.pipe()
        env = dict(os.environ, PUBLICATION_PROTOCOL_FD=str(write_fd))
        self.process = subprocess.Popen([sys.executable, "-c", source], stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        env=env, pass_fds=(write_fd,), preexec_fn=drop_privileges,
                                        start_new_session=True)
        os.close(write_fd)
        self.fd, self.buffer = read_fd, b""
        self.events = []
        try:
            require(self.receive()["kind"] == "ready", "candidate module did not initialize")
        except BaseException:
            self.close()
            raise

    def receive(self, timeout=12):
        until = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = until - time.monotonic()
            if remaining <= 0 or not select.select([self.fd], [], [], max(0, remaining))[0]:
                raise AssertionError("publisher worker did not respond")
            chunk = os.read(self.fd, 65536)
            require(chunk, "publisher worker exited without protocol response")
            self.buffer += chunk
            require(len(self.buffer) < 4_000_000, "oversized publisher protocol")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def send(self, message):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()

    def release(self):
        self.process.stdin.write(b"continue\n")
        self.process.stdin.flush()

    def result(self):
        while True:
            value = self.receive()
            if value["kind"] == "hook":
                self.events.append(value)
            else:
                return value

    def call(self, message):
        self.events = []
        self.send(message)
        return self.result()

    def pause(self, message):
        self.events = []
        self.send(message)
        while True:
            value = self.receive()
            require(value["kind"] == "hook", "writer did not reach public pause hook")
            self.events.append(value)
            if value["event"] == message["pause_at"]:
                return

    def kill(self):
        if self.process.poll() is None:
            # Kill the complete worker session, not other task or host processes.
            import signal
            os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=5)

    def close(self):
        self.kill()
        self.process.stdin.close()
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def ok(worker, message):
    result = worker.call(message)
    require(result.get("ok") is True, f"publication failed: {result}")
    require(result["answer"] == message["id"], "publish returned wrong ID")


def snapshot(root, ident, parent, data):
    require((root / "CURRENT").read_bytes() == (ident + "\n").encode(), "wrong CURRENT bytes")
    folder = root / "releases" / ident
    manifest = json.loads((folder / "manifest.json").read_bytes())
    require(set(manifest) == {"version", "release_id", "parent", "sha256"}, "wrong manifest fields")
    require(type(manifest["version"]) is int and manifest["version"] == 1, "wrong manifest version")
    require(manifest["release_id"] == ident and manifest["parent"] == parent, "wrong manifest identity")
    require(manifest["sha256"] == {name: hashlib.sha256(data[name]).hexdigest() for name in NAMES}, "wrong manifest hashes")
    for name, value in data.items():
        require((folder / name).read_bytes() == value, "mixed or altered generation")


def assert_reader(worker, root, ident, parent, data):
    reply = worker.call({"op": "read", "root": str(root), "pathlike": True})
    expected = {"release_id": ident, "parent": parent,
                "artifacts": {k: base64.b64encode(v).decode("ascii") for k, v in data.items()}}
    require(reply.get("ok") and reply["answer"] == expected, "read_current returned a mixed/wrong snapshot")


def clean(root):
    require(not (root / ".staging").exists() or not list((root / ".staging").iterdir()), "stale staging remains")
    require(not list(root.glob(".current-*")), "stale pointer remains")


def committed_bytes(root):
    names = {"CURRENT": (root / "CURRENT").read_bytes()} if (root / "CURRENT").exists() else {}
    ident = names.get("CURRENT", b"").decode().strip()
    seen = set()
    while ident:
        require(ident not in seen, "cycle in verifier fixture")
        seen.add(ident)
        folder = root / "releases" / ident
        for path in folder.iterdir():
            if path.is_file():
                names[str(path.relative_to(root))] = path.read_bytes()
        ident = json.loads((folder / "manifest.json").read_bytes())["parent"]
    return names


def unchanged(root, previous):
    for name, value in previous.items():
        require((root / name).read_bytes() == value, f"committed bytes changed: {name}")


def check_publication_snapshots():
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        os.chmod(base, 0o755)
        root = base / "new" / "deep" / "store"
        with Worker() as writer, Worker() as reader:
            answer = reader.call({"op": "read", "root": str(root)})
            require(answer.get("ok") and answer["answer"] is None and not root.exists(), "read created an absent store")
            writable(base / "new")
            data = payloads("first")
            ok(writer, request(root, "first", None, data, hooks=True, pathlike=True))
            snapshot(root, "first", None, data)
            assert_reader(reader, root, "first", None, data)
            expected_events = [("after_stage_file", {"release_id": "first", "name": name}) for name in NAMES]
            expected_events += [("after_seal", {"release_id": "first"}), ("after_switch", {"release_id": "first"})]
            require([(v["event"], v["detail"]) for v in writer.events] == expected_events, "incorrect public hook order/details")
            old = committed_bytes(root)
            following = payloads("following")
            writer.pause(request(root, "following", "first", following, hooks=True, pause_at="after_stage_file"))
            assert_reader(reader, root, "first", None, data)
            # Every staged artifact pauses once; readers remain independent of writer lock.
            for _ in range(4):
                writer.release()
                value = writer.receive()
                if value["kind"] == "hook" and value["event"] == "after_stage_file":
                    assert_reader(reader, root, "first", None, data)
                else:
                    require(value["event"] == "after_seal", "unexpected staging callback")
                    break
            result = writer.result()
            require(result.get("ok"), "staged publication did not finish")
            for name, value in old.items():
                if name != "CURRENT":
                    require((root / name).read_bytes() == value, "old generation mutated")
            snapshot(root, "following", "first", following)
            assert_reader(reader, root, "following", "first", following)
            clean(root)


def check_publication_cas():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        os.chmod(root, 0o777)
        with Worker() as setup, Worker() as first, Worker() as second, Worker() as reader:
            initial = payloads("base")
            ok(setup, request(root, "base", None, initial))
            lock_inode = (root / ".writer.lock").stat().st_ino
            first_data, second_data = payloads("winner"), payloads("loser")
            first.pause(request(root, "winner", "base", first_data, hooks=True, pause_at="after_seal"))
            # The second worker was ready before the first starts; its request competes
            # for precisely the same parent. No timing-based sleep is used.
            second.send(request(root / ".", "loser", "base", second_data))
            assert_reader(reader, root, "base", None, initial)
            first.release()
            require(first.result().get("ok"), "winning writer failed")
            require(second.result().get("ok") is False, "both writers committed against the same parent")
            snapshot(root, "winner", "base", first_data)
            require((root / ".writer.lock").stat().st_ino == lock_inode, "writer lock inode replaced")
            require(not (root / "releases" / "loser").exists(), "CAS loser sealed a new generation")
            clean(root)
            for index in range(4):
                parent = (root / "CURRENT").read_text().strip()
                candidates = [request(root, f"t{index}_{name}", parent, payloads(name)) for name in ("a", "b")]
                reply = setup.call({"op": "threads", "root": str(root), "requests": candidates})
                require(reply.get("ok"), "threaded publication failed to complete")
                successful = [value for value in reply["answer"] if value["ok"]]
                require(len(successful) == 1, "thread writers did not serialize one CAS winner")
                winner = next(value for value in candidates if value["id"] == successful[0]["id"])
                snapshot(root, winner["id"], parent, {k: base64.b64decode(v) for k, v in winner["artifacts"].items()})


def check_publication_identity():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        os.chmod(root, 0o777)
        with Worker() as worker:
            a, b = payloads("a"), payloads("b")
            ok(worker, request(root, "a", None, a))
            ok(worker, request(root, "b", "a", b))
            before = committed_bytes(root)
            ok(worker, request(root, "a", None, a, hooks=True, raise_at="after_seal"))
            require(not worker.events, "committed retry invoked a callback")
            unchanged(root, before)
            for message in (request(root, "a", None, payloads("different")), request(root, "a", "b", a)):
                require(worker.call(message).get("ok") is False, "sealed ID reuse accepted")
                unchanged(root, before)
            orphan = payloads("orphan")
            reply = worker.call(request(root, "orphan", "b", orphan, hooks=True, raise_at="after_seal"))
            require(reply.get("ok") is False, "hook exception swallowed")
            unchanged(root, before)
            require(worker.call(request(root, "orphan", "b", payloads("changed"))).get("ok") is False, "orphan identity overwritten")
            c = payloads("c")
            ok(worker, request(root, "c", "b", c))
            before = committed_bytes(root)
            require(worker.call(request(root, "orphan", "b", orphan)).get("ok") is False, "stale orphan promoted")
            unchanged(root, before)


def check_publication_recovery():
    for phase in ("after_stage_file", "after_seal", "after_switch"):
        for terminate in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                os.chmod(root, 0o777)
                initial, following = payloads("old"), payloads("new")
                with Worker() as worker:
                    ok(worker, request(root, "old", None, initial))
                    before = committed_bytes(root)
                    attempt = request(root, "new", "old", following, hooks=True,
                                      **({"pause_at": phase} if terminate else {"raise_at": phase}))
                    if terminate:
                        worker.pause(attempt)
                        worker.kill()
                    else:
                        response = worker.call(attempt)
                        require(not response.get("ok") and "publication-probe-fault" in response.get("error", ""), "callback exception was hidden")
                    if phase != "after_switch":
                        unchanged(root, before)
                    else:
                        snapshot(root, "new", "old", following)
                with Worker() as retry:
                    ok(retry, request(root, "new", "old", following, hooks=True))
                    snapshot(root, "new", "old", following)
                    if phase == "after_stage_file":
                        require(sum(v["event"] == "after_stage_file" for v in retry.events) == 4, "partial staging treated as sealed")
                    if phase == "after_seal":
                        require([v["event"] for v in retry.events] == ["after_seal", "after_switch"], "sealed orphan was restaged")
                    if phase == "after_switch":
                        require(not retry.events, "committed crash retry repeated work")
                    clean(root)
                    third = payloads("third")
                    ok(retry, request(root, "third", "new", third))
                    advanced = committed_bytes(root)
                    ok(retry, request(root, "new", "old", following))
                    unchanged(root, advanced)


def check_publication_boundaries():
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        os.chmod(base, 0o777)
        with Worker() as worker:
            data = payloads("invalid")
            bad = [request(base / "absent", ident, None, data) for ident in ("", "NONE", "../x", "a/b", "a" * 41, "药物")]
            bad += [request(base / "absent", "valid", parent, data) for parent in ("NONE", "../x", 1, False)]
            bad += [request(base / "absent", "valid", None, {k: v for k, v in data.items() if k != "report.json"}),
                    request(base / "absent", "valid", None, data, bad_value=True),
                    request(base / "absent", "valid", None, data, bad_hook=True)]
            for message in bad:
                require(worker.call(message).get("ok") is False, "bad publisher arguments accepted")
                require(not (base / "absent").exists(), "validation failure created store")
            root = base / "store"
            ok(worker, request(root, "base", None, data, pathlike=True))
            (root / "do-not-delete.txt").write_bytes(b"unrelated\n")
            before = committed_bytes(root)
            # A committed ancestor must be verified even when the tip payload is intact.
            next_data = payloads("next")
            ok(worker, request(root, "next", "base", next_data))
            tip = (root / "CURRENT").read_bytes()
            damaged = root / "releases" / "base" / "drugs_clean.csv"
            damaged.write_bytes(b"corrupted\n")
            corrupted = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != ".writer.lock"}
            require(worker.call(request(root, "third", "next", payloads("third"))).get("ok") is False, "corrupt ancestor was silently accepted")
            unchanged(root, corrupted)
            require((root / "CURRENT").read_bytes() == tip, "corrupt-chain rejection changed tip")
            require((root / "do-not-delete.txt").read_bytes() == b"unrelated\n", "unrelated store file deleted")
            damaged.write_bytes(data["drugs_clean.csv"])
            # Corrupt captured tip must also make the lock-free reader fail.
            manifest_file = root / "releases" / "next" / "manifest.json"
            original = manifest_file.read_bytes()
            manifest = json.loads(original)
            manifest["version"] = True
            manifest_file.write_text(json.dumps(manifest))
            require(worker.call({"op": "read", "root": str(root)}).get("ok") is False, "invalid manifest accepted by reader")
            manifest_file.write_bytes(original)
            # Detect malformed ancestry rather than trusting only a tip checksum.
            for parent in ("next", "missing"):
                manifest = json.loads(original)
                manifest["parent"] = parent
                manifest_file.write_text(json.dumps(manifest))
                invalid_state = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file() and p.name != ".writer.lock"}
                require(worker.call(request(root, "third", "next", payloads("third"))).get("ok") is False, "invalid parent chain accepted")
                unchanged(root, invalid_state)
            manifest_file.write_bytes(original)
            # Successful no-work retry also cleans crash leftovers without touching unrelated files.
            writable(root / ".staging" / "stale")
            (root / ".staging" / "stale" / "partial").write_bytes(b"partial")
            (root / ".current-stale").write_bytes(b"partial")
            ok(worker, request(root, "base", None, data))
            clean(root)
            snapshot(root, "next", "base", next_data)
