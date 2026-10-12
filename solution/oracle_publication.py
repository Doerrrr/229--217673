"""Immutable generations, serialized writers, and a single atomic pointer."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


FILENAMES = (
    "drugs_clean.csv",
    "interaction_delta.csv",
    "interactions_clean.csv",
    "report.json",
)
_ID = re.compile(r"[a-z][a-z0-9_-]{0,39}", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _check_id(value):
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("invalid release ID")


def _root_path(root):
    if not isinstance(root, (str, Path)) or (isinstance(root, str) and not root):
        raise ValueError("root must be a nonempty string or pathlib.Path")
    return Path(root).resolve()


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _make_root(root):
    missing = []
    cursor = root
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    for directory in reversed(missing):
        directory.mkdir(exist_ok=True)
        _fsync_dir(directory.parent)
        _fsync_dir(directory)
    if not root.is_dir():
        raise ValueError("store root is not a directory")


@contextmanager
def _writer_lock(root):
    # Separate open file descriptions serialize threads as well as processes.
    import fcntl

    with (root / ".writer.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.flush()
            os.fsync(handle.fileno())
            _fsync_dir(root)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _current_id(root):
    # Read CURRENT once; the captured sealed directory remains immutable.
    try:
        payload = (root / "CURRENT").read_bytes()
    except FileNotFoundError:
        return None
    if not payload.endswith(b"\n"):
        raise ValueError("invalid CURRENT pointer")
    release_id = payload[:-1].decode("ascii")
    _check_id(release_id)
    if payload != (release_id + "\n").encode("ascii"):
        raise ValueError("invalid CURRENT pointer")
    return release_id


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _load_release(root, release_id):
    folder = root / "releases" / release_id
    manifest = json.loads(
        (folder / "manifest.json").read_bytes().decode("utf-8"),
        object_pairs_hook=_unique_object,
    )
    if not isinstance(manifest, dict) or set(manifest) != {
        "version", "release_id", "parent", "sha256"
    }:
        raise ValueError("invalid manifest fields")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("invalid manifest version")
    if manifest["release_id"] != release_id:
        raise ValueError("manifest release ID does not match its directory")
    parent = manifest["parent"]
    if parent is not None:
        _check_id(parent)
    hashes = manifest["sha256"]
    if not isinstance(hashes, dict) or set(hashes) != set(FILENAMES):
        raise ValueError("invalid manifest hash fields")
    artifacts = {}
    for name in FILENAMES:
        digest = hashes[name]
        if not isinstance(digest, str) or _HASH.fullmatch(digest) is None:
            raise ValueError("invalid manifest digest")
        payload = (folder / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("artifact hash mismatch: " + name)
        artifacts[name] = payload
    return {"release_id": release_id, "parent": parent, "artifacts": artifacts}


def _current_chain(root):
    current = _current_id(root)
    chain = {}
    cursor = current
    while cursor is not None:
        if cursor in chain:
            raise ValueError("cycle in current release chain")
        generation = _load_release(root, cursor)
        chain[cursor] = generation
        cursor = generation["parent"]
    return current, chain


def _remove_private(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _clean_private(root):
    staging = root / ".staging"
    staging.mkdir(exist_ok=True)
    for child in staging.iterdir():
        _remove_private(child)
    for child in root.iterdir():
        if child.name.startswith(".current-"):
            _remove_private(child)
    _fsync_dir(staging)
    _fsync_dir(root)
    return staging


def _write_file(path, payload):
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def publish(root, release_id, expected_parent, artifacts, hook=None):
    """Publish a generation with compare-and-swap and exact-request retries."""
    root = _root_path(root)
    _check_id(release_id)
    if expected_parent is not None:
        _check_id(expected_parent)
    if not isinstance(artifacts, dict) or set(artifacts) != set(FILENAMES):
        raise ValueError("artifacts must contain exactly the four payloads")
    if any(not isinstance(value, bytes) for value in artifacts.values()):
        raise TypeError("artifact values must be bytes")
    if hook is not None and not callable(hook):
        raise TypeError("hook must be callable or None")
    payloads = dict(artifacts)

    _make_root(root)
    with _writer_lock(root):
        current, chain = _current_chain(root)
        destination = root / "releases" / release_id
        sealed = chain.get(release_id)
        if sealed is None and destination.exists():
            sealed = _load_release(root, release_id)
        if sealed is not None:
            if sealed["parent"] != expected_parent or sealed["artifacts"] != payloads:
                raise ValueError("sealed ID already belongs to a different request")
            if release_id in chain:
                _clean_private(root)
                return release_id
        if current != expected_parent:
            raise ValueError("expected parent does not match CURRENT")

        staging = _clean_private(root)
        releases = root / "releases"
        releases.mkdir(exist_ok=True)
        _fsync_dir(root)
        if sealed is None:
            stage = Path(tempfile.mkdtemp(prefix=release_id + "-", dir=staging))
            for name in FILENAMES:
                _write_file(stage / name, payloads[name])
                if hook is not None:
                    hook("after_stage_file", {"release_id": release_id, "name": name})
            manifest = {
                "version": 1,
                "release_id": release_id,
                "parent": expected_parent,
                "sha256": {
                    name: hashlib.sha256(payloads[name]).hexdigest()
                    for name in FILENAMES
                },
            }
            manifest_bytes = (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8")
            _write_file(stage / "manifest.json", manifest_bytes)
            _fsync_dir(stage)
            os.rename(stage, destination)
            _fsync_dir(releases)
            _fsync_dir(staging)
        if hook is not None:
            hook("after_seal", {"release_id": release_id})

        fd, temporary = tempfile.mkstemp(prefix=".current-", dir=root)
        with os.fdopen(fd, "wb") as handle:
            handle.write((release_id + "\n").encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, root / "CURRENT")
        _fsync_dir(root)
        if hook is not None:
            hook("after_switch", {"release_id": release_id})
        return release_id


def read_current(root):
    """Read a captured generation without creating a store or taking a lock."""
    root = _root_path(root)
    release_id = _current_id(root)
    if release_id is None:
        return None
    return _load_release(root, release_id)
