"""Immutable local-filesystem generations with compare-and-swap publication."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

NAMES = ("drugs_clean.csv", "interaction_delta.csv", "interactions_clean.csv", "report.json")
ID = re.compile(r"[a-z][a-z0-9_-]{0,39}", re.ASCII)


class PublicationError(ValueError):
    pass


def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None


def root_path(root):
    if not isinstance(root, (str, Path)) or (isinstance(root, str) and not root):
        raise PublicationError("root must be a nonempty string or Path")
    return Path(root).resolve()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_file(path, data):
    with path.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def current_id(root):
    try:
        value = (root / "CURRENT").read_bytes()
    except FileNotFoundError:
        return None
    try:
        result = value.decode("ascii")
    except UnicodeError as exc:
        raise PublicationError("invalid CURRENT encoding") from exc
    if not result.endswith("\n") or not valid_id(result[:-1]):
        raise PublicationError("invalid CURRENT")
    return result[:-1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicationError("duplicate manifest key")
        result[key] = value
    return result


def load_generation(root, release_id):
    folder = root / "releases" / release_id
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"),
                              object_pairs_hook=unique_object)
        if (not isinstance(manifest, dict)
                or set(manifest) != {"version", "release_id", "parent", "sha256"}
                or type(manifest["version"]) is not int or manifest["version"] != 1
                or manifest["release_id"] != release_id
                or (manifest["parent"] is not None and not valid_id(manifest["parent"]))
                or not isinstance(manifest["sha256"], dict)
                or set(manifest["sha256"]) != set(NAMES)):
            raise PublicationError("invalid generation manifest")
        payloads = {name: (folder / name).read_bytes() for name in NAMES}
        for name, payload in payloads.items():
            if manifest["sha256"][name] != hashlib.sha256(payload).hexdigest():
                raise PublicationError("generation checksum mismatch")
        return manifest, payloads
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"unreadable generation {release_id}") from exc


def read_current(root):
    root = root_path(root)
    release_id = current_id(root)  # Capture precisely once, without a writer lock.
    if release_id is None:
        return None
    manifest, payloads = load_generation(root, release_id)
    return {"release_id": release_id, "parent": manifest["parent"], "artifacts": payloads}


def current_chain(root, head):
    seen = set()
    cursor = head
    while cursor is not None:
        if cursor in seen:
            raise PublicationError("cycle in committed chain")
        seen.add(cursor)
        manifest, _ = load_generation(root, cursor)
        cursor = manifest["parent"]
    return seen


def clean_private(root):
    staging = root / ".staging"
    if staging.exists():
        for path in staging.iterdir():
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
    for path in root.glob(".current-*"):
        path.unlink()


def publish(root, release_id, expected_parent, artifacts, hook=None):
    import fcntl
    root = root_path(root)
    if not valid_id(release_id) or (expected_parent is not None and not valid_id(expected_parent)):
        raise PublicationError("invalid release or parent ID")
    if (not isinstance(artifacts, dict) or set(artifacts) != set(NAMES)
            or any(type(value) is not bytes for value in artifacts.values())):
        raise PublicationError("artifacts must be the four named byte strings")
    if hook is not None and not callable(hook):
        raise PublicationError("hook must be callable")
    # Freeze the caller's mapping before callbacks can change it.
    payloads = dict(artifacts)
    manifest = {"version": 1, "release_id": release_id, "parent": expected_parent,
                "sha256": {name: hashlib.sha256(payloads[name]).hexdigest() for name in NAMES}}

    def notify(event, **detail):
        if hook is not None:
            hook(event, {"release_id": release_id, **detail})

    root.mkdir(parents=True, exist_ok=True)
    # Each call opens a distinct file description; flock covers threads and processes.
    # The pathname/inode remains stable across every attempt.
    with (root / ".writer.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            head = current_id(root)
            committed = current_chain(root, head)
            destination = root / "releases" / release_id
            exists = destination.exists()
            if exists:
                old_manifest, old_payloads = load_generation(root, release_id)
                if old_manifest != manifest or old_payloads != payloads:
                    raise PublicationError("sealed release ID has a different request identity")
            if release_id in committed:
                clean_private(root)
                return release_id  # Never replace CURRENT on an ancestor retry.
            if head != expected_parent:
                raise PublicationError("expected parent does not match CURRENT")
            clean_private(root)
            releases = root / "releases"
            releases.mkdir(exist_ok=True)
            staging = root / ".staging"
            staging.mkdir(exist_ok=True)
            sync_directory(root)
            stage = None
            pointer = None
            try:
                if not exists:
                    stage = Path(tempfile.mkdtemp(prefix="generation-", dir=staging))
                    for name in NAMES:
                        write_file(stage / name, payloads[name])
                        notify("after_stage_file", name=name)
                    write_file(stage / "manifest.json",
                               (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"))
                    sync_directory(stage)
                    os.rename(stage, destination)
                    stage = None
                    sync_directory(releases)
                    sync_directory(staging)
                notify("after_seal")
                fd, name = tempfile.mkstemp(prefix=".current-", dir=root)
                pointer = Path(name)
                with os.fdopen(fd, "wb") as stream:
                    stream.write((release_id + "\n").encode("ascii"))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(pointer, root / "CURRENT")
                pointer = None
                sync_directory(root)
                notify("after_switch")
                return release_id
            finally:
                if stage is not None and stage.exists():
                    shutil.rmtree(stage)
                if pointer is not None and pointer.exists():
                    pointer.unlink()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
