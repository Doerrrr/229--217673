"""Fail closed on exact file duplication across the candidate/hidden boundary.

This preflight supports this task's local COPY instructions, not arbitrary
Dockerfiles. It is a packaging check, not an extra scored agent requirement.
"""
import argparse
import hashlib
import json
import shlex
import tempfile
from pathlib import Path


class BoundaryError(ValueError):
    pass


def files_under(path):
    if path.is_symlink():
        raise BoundaryError(f"symlink needs explicit boundary review: {path}")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise BoundaryError(f"missing COPY source/hidden directory: {path}")
    files = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise BoundaryError(f"symlink needs explicit boundary review: {item}")
        if item.is_file():
            files.append(item)
    return files


def copied_files(root):
    context = (root/"environment").resolve()
    if (context/".dockerignore").exists() or (context/"Dockerfile.dockerignore").exists():
        raise BoundaryError("Docker ignore rules need explicit boundary checker support")
    sources = set()
    for line in (context/"Dockerfile").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        instruction, arguments = parts[0], parts[1] if len(parts) > 1 else ""
        if instruction.upper() == "ADD":
            raise BoundaryError("ADD needs explicit boundary checker support")
        if instruction.upper() != "COPY":
            continue
        if arguments.lstrip().startswith("["):
            tokens = json.loads(arguments)
        else:
            tokens = shlex.split(arguments)
        if len(tokens) < 2 or any(not isinstance(token, str) for token in tokens):
            raise BoundaryError("invalid COPY instruction")
        if any(token.startswith("--") for token in tokens) or "\\" in arguments:
            raise BoundaryError("COPY flags/continuations need explicit boundary checker support")
        for source in tokens[:-1]:
            if any(char in source for char in "*?[]$") or source.startswith("/"):
                raise BoundaryError(f"unsupported COPY source: {source}")
            path = context/source
            if not path.resolve().is_relative_to(context):
                raise BoundaryError(f"COPY outside build context: {source}")
            sources.update(files_under(path))
    if not sources:
        raise BoundaryError("no candidate COPY files found")
    return sorted(sources)


def check_boundary(root):
    root = Path(root).resolve()
    candidates = copied_files(root)
    hidden = [path for folder in ("solution", "tests") for path in files_under(root/folder)]
    by_hash = {}
    for path in hidden:
        data = path.read_bytes()
        by_hash.setdefault(hashlib.sha256(data).hexdigest(), []).append(path)
    duplicates = []
    for path in candidates:
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        for other in by_hash.get(sha, ()):
            # Compare bytes too: a digest is evidence, not a substitute for content.
            if data == other.read_bytes():
                duplicates.append(dict(candidate=path.relative_to(root).as_posix(),
                                       hidden=other.relative_to(root).as_posix(), sha256=sha))
    if duplicates:
        raise BoundaryError("candidate/hidden exact duplicate files: " + json.dumps(duplicates))
    return dict(status="PASS", copied_files=len(candidates), hidden_files=len(hidden),
                exact_duplicates=0)


def selftest():
    with tempfile.TemporaryDirectory(prefix="ddi-boundary-") as directory:
        root = Path(directory)
        for name in ("environment/bin", "solution", "tests"):
            (root/name).mkdir(parents=True)
        (root/"environment/Dockerfile").write_text("FROM scratch\nCOPY bin/ /bin/\n", encoding="utf-8")
        launcher = b'#!/bin/bash\nexec python3 /opt/ddi-release/release.py "$@"\n'
        (root/"environment/bin/ddi-release").write_bytes(launcher)
        (root/"solution/ddi-release").write_bytes(launcher)
        try:
            check_boundary(root)
        except BoundaryError as error:
            if "exact duplicate files" not in str(error):
                raise
        else:
            raise AssertionError("duplicate launcher escaped boundary check")
        (root/"solution/ddi-release").unlink()
        (root/"tests/hidden-copy").write_bytes(launcher)
        try:
            check_boundary(root)
        except BoundaryError as error:
            if "exact duplicate files" not in str(error):
                raise
        else:
            raise AssertionError("duplicate test file escaped boundary check")
        (root/"tests/hidden-copy").write_bytes(b"distinct hidden test\n")
        check_boundary(root)
    return dict(duplicate_solution="REJECTED", duplicate_test="REJECTED", distinct_files="PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            print(json.dumps(selftest(), sort_keys=True))
        print(json.dumps(check_boundary(args.root), sort_keys=True))
    except (ValueError, OSError) as error:
        parser.exit(1, f"Boundary preflight failed: {error}\n")


if __name__ == "__main__":
    main()
