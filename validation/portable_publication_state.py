"""Sequential reference state checks only; locks/directory fsync are NOT tested."""
import hashlib
import importlib.util
import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reference", ROOT / "solution/oracle_publication.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
# Explicitly limited emulation for author diagnostics, never used by the verifier.
sys.modules["fcntl"] = types.SimpleNamespace(LOCK_EX=1, LOCK_UN=2, flock=lambda *_: None)
publisher.sync_directory = lambda _: None
data = {name: (name + "\n").encode() for name in publisher.NAMES}
results = []
for phase in ("after_stage_file", "after_seal", "after_switch"):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "store"
        publisher.publish(root, "base", None, data)
        following = {name: b"new-" + value for name, value in data.items()}

        def fail(event, detail):
            if event == phase:
                raise RuntimeError("probe-fault")

        try:
            publisher.publish(root, "next", "base", following, fail)
            raise AssertionError("callback failure was swallowed")
        except RuntimeError as exc:
            assert str(exc) == "probe-fault"
        want = "next" if phase == "after_switch" else "base"
        assert publisher.read_current(root)["release_id"] == want
        assert publisher.publish(root, "next", "base", following) == "next"
        assert publisher.read_current(root)["artifacts"] == following
        pointer = (root / "CURRENT").read_bytes()
        assert publisher.publish(root, "base", None, data) == "base"
        assert (root / "CURRENT").read_bytes() == pointer
        try:
            publisher.publish(root, "base", None, following)
            raise AssertionError("reused sealed ID with changed bytes")
        except publisher.PublicationError:
            pass
        assert not list((root / ".staging").iterdir())
        results.append({"phase": phase, "exception_retry_ancestor_identity": "PASS"})
print(json.dumps({"scope": "sequential reference state only; no Linux locks, process crash or directory fsync",
                  "checks": results}, indent=2))
