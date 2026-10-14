#!/usr/bin/env python3
"""Laboratory store adapter: transactional dual-view publication.

Two modes share one entry point:

  --manifest M --samples S
      the original stdout report, produced by the native core;

  --manifest M --samples S --out-dir D --expect E [--gate G]
      a file publication.  A generation is named by the SHA-256 of its input
      object, its two views are built out of the way, and only then is the
      store pointer moved, under a commit lock that re-reads the pointer so
      that exactly one publication of a given predecessor can win.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'cohort-native'
HEX = re.compile(r'[a-f0-9]{64}\Z')
BUFFER = 1024 * 1024

EXIT_USAGE = 2
EXIT_SOURCE = 3
EXIT_RECORD = 4
EXIT_SAMPLE = 5
EXIT_IO = 6
EXIT_EXPECT = 7

VIEWS = ('release.jsonl', 'original.jsonl')


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------ input --

def read_manifest(path):
    """Source identifiers and paths, in manifest order."""
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise Failure(EXIT_SOURCE, 'cannot read the manifest (%s)' % error.strerror)
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise Failure(EXIT_USAGE, 'the manifest is not UTF-8')
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    if not lines or lines[0].rstrip('\r') != 'source\tpath':
        raise Failure(EXIT_USAGE, 'the manifest header is not "source<tab>path"')
    entries = []
    for line in lines[1:]:
        line = line.rstrip('\r')
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise Failure(EXIT_USAGE, 'a manifest row is not "source<tab>path"')
        entries.append((parts[0], parts[1]))
    if not entries:
        raise Failure(EXIT_USAGE, 'the manifest lists no source')
    seen = set()
    for source_id, _ in entries:
        if source_id in seen:
            raise Failure(EXIT_USAGE, 'duplicate source identifier %r' % source_id)
        seen.add(source_id)
    return entries


def parse_samples(text):
    if not text:
        raise Failure(EXIT_USAGE, 'no sample was requested')
    samples = []
    for item in text.split(','):
        if not item or any(ord(c) <= 32 or ord(c) >= 127 or c == ',' for c in item):
            raise Failure(EXIT_USAGE, 'invalid sample name %r' % item)
        if item in samples:
            raise Failure(EXIT_USAGE, 'duplicate sample %r' % item)
        samples.append(item)
    return samples


def digest_file(path, counter=None):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            chunk = stream.read(BUFFER)
            if not chunk:
                break
            digest.update(chunk)
            if counter is not None:
                counter[0] += chunk.count(b'\n')
                counter[1] = chunk[-1:]
    if counter is not None and counter[1] and counter[1] != b'\n':
        counter[0] += 1
    return digest.hexdigest()


def digest_and_rows(path):
    counter = [0, b'']
    digest = digest_file(path, counter)
    return digest, counter[0]


def input_payload(entries, manifest_path, samples):
    base = Path(manifest_path).parent
    sources = []
    for source_id, relative in entries:
        path = Path(relative)
        if not path.is_absolute():
            path = base / path
        try:
            digest = digest_file(path)
        except OSError as error:
            raise Failure(EXIT_SOURCE, 'cannot read source %r (%s)' % (source_id, error.strerror))
        sources.append({'source': source_id, 'sha256': digest})
    return {'sources': sources, 'samples': list(samples)}


def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def generation_of(payload):
    return hashlib.sha256(canonical(payload)).hexdigest()


# ------------------------------------------------------------------ store --

def read_current(out_dir):
    pointer = out_dir / 'CURRENT'
    try:
        if pointer.is_symlink() or not pointer.is_file():
            return 'NONE'
        raw = pointer.read_bytes()
    except OSError as error:
        raise Failure(EXIT_IO, 'cannot read store/CURRENT (%s)' % error.strerror)
    if len(raw) != 65 or raw[-1:] != b'\n':
        raise Failure(EXIT_IO, 'store/CURRENT is not a version pointer')
    generation = raw[:-1].decode('ascii', 'strict')
    if not HEX.fullmatch(generation):
        raise Failure(EXIT_IO, 'store/CURRENT is not a version pointer')
    return generation


def write_bytes_atomic(target, raw):
    folder = target.parent
    handle, temporary = tempfile.mkstemp(prefix='.' + target.name + '.', dir=str(folder))
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    fsync_dir(folder)


def fsync_dir(folder):
    try:
        descriptor = os.open(str(folder), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def verify_generation(out_dir, generation, expect_input=None):
    """Check a generation directory against its own manifest; None means good."""
    folder = out_dir / 'generations' / generation
    try:
        if folder.is_symlink() or not folder.is_dir():
            return 'missing generation directory'
        manifest_path = folder / 'manifest.json'
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return 'missing manifest'
        meta = json.loads(manifest_path.read_bytes())
        if not isinstance(meta, dict) or meta.get('generation') != generation:
            return 'manifest names another generation'
        payload = meta.get('input')
        if generation_of(payload) != generation:
            return 'input object does not hash to the generation'
        if expect_input is not None and canonical(payload) != canonical(expect_input):
            return 'input object differs from the caller input'
        files = meta.get('files')
        if not isinstance(files, dict) or set(files) != set(VIEWS):
            return 'manifest does not list exactly the two views'
        for name in VIEWS:
            view = folder / name
            if view.is_symlink() or not view.is_file():
                return 'missing view %s' % name
            entry = files[name]
            digest, rows = digest_and_rows(view)
            if entry.get('sha256') != digest:
                return 'view %s has another digest' % name
            if entry.get('rows') != rows:
                return 'view %s has another row count' % name
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return 'generation is not readable'
    return None


def build_generation(out_dir, generation, payload, manifest_path, samples):
    """Produce the two views and move them into place under generations/<gen>."""
    generations = out_dir / 'generations'
    target = generations / generation
    try:
        generations.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise Failure(EXIT_IO, 'cannot create the generation directory (%s)' % error.strerror)

    staging = Path(tempfile.mkdtemp(prefix='.staging-', dir=str(out_dir)))
    try:
        release = staging / 'release.jsonl'
        original = staging / 'original.jsonl'
        try:
            finished = subprocess.run(
                [str(NATIVE), '--manifest', str(manifest_path), '--samples', ','.join(samples),
                 '--release-out', str(release), '--original-out', str(original)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, restore_signals=False)
        except OSError as error:
            raise Failure(EXIT_IO, 'cannot run the release core (%s)' % error.strerror)
        if finished.returncode:
            note = finished.stderr.decode('utf-8', 'replace').strip().splitlines()
            message = note[-1] if note else 'the release core refused the input'
            code = finished.returncode if 2 <= finished.returncode <= 6 else EXIT_RECORD
            raise Failure(code, message)

        files = {}
        for name in VIEWS:
            digest, rows = digest_and_rows(staging / name)
            files[name] = {'sha256': digest, 'rows': rows}
        meta = {'generation': generation, 'input': payload, 'files': files}
        write_bytes_atomic(staging / 'manifest.json',
                           (json.dumps(meta, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8'))

        try:
            os.rename(staging, target)
        except OSError:
            fault = verify_generation(out_dir, generation, payload)
            if fault is None:
                return target                                  # somebody else won
            current = read_current(out_dir)
            if current == generation:
                raise Failure(EXIT_IO, 'the committed generation is unusable: %s' % fault)
            try:
                shutil.rmtree(target)
                os.rename(staging, target)
            except OSError as error:
                raise Failure(EXIT_IO, 'cannot install the generation (%s)' % error.strerror)
        fsync_dir(generations)
        return target
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def announce(gate_dir, generation):
    """Publish a complete readiness object, then wait without holding anything."""
    gate = Path(gate_dir)
    if not gate.is_dir():
        raise Failure(EXIT_IO, 'the gate directory does not exist')
    try:
        write_bytes_atomic(gate / 'ready',
                           (json.dumps({'generation': generation, 'stage': 'PREPARED'}) + '\n').encode('utf-8'))
        while not (gate / 'go').exists():
            time.sleep(0.01)
    except OSError as error:
        raise Failure(EXIT_IO, 'cannot use the gate (%s)' % error.strerror)


def commit(out_dir, generation, expect):
    """Re-decide the expected predecessor with the commit lock held."""
    lock_path = out_dir / '.commit.lock'
    descriptor = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        current = read_current(out_dir)
        if current != expect:
            raise Failure(EXIT_EXPECT, 'the store now holds %s, expected %s' % (current, expect))
        write_bytes_atomic(out_dir / 'CURRENT', (generation + '\n').encode('ascii'))
    except OSError as error:
        raise Failure(EXIT_IO, 'cannot commit (%s)' % error.strerror)
    finally:
        os.close(descriptor)


# ------------------------------------------------------------------- main --

def publish(args):
    expect = args.expect
    if expect is None:
        raise Failure(EXIT_USAGE, '--expect is required for a file publication')
    if expect != 'NONE' and not HEX.fullmatch(expect):
        raise Failure(EXIT_USAGE, '--expect must be NONE or a version identifier')

    samples = parse_samples(args.samples)
    entries = read_manifest(args.manifest)
    payload = input_payload(entries, args.manifest, samples)
    generation = generation_of(payload)

    out_dir = Path(args.out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise Failure(EXIT_IO, 'cannot create the store (%s)' % error.strerror)

    if read_current(out_dir) != expect:
        raise Failure(EXIT_EXPECT, 'the store does not hold the expected generation')

    if verify_generation(out_dir, generation, payload) is not None:
        build_generation(out_dir, generation, payload, args.manifest, samples)

    if args.gate is not None:
        announce(args.gate, generation)

    commit(out_dir, generation, expect)
    return 0


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--samples', required=True)
    parser.add_argument('--out-dir')
    parser.add_argument('--expect')
    parser.add_argument('--gate')
    args = parser.parse_args()

    if args.out_dir is None:
        if args.expect is not None or args.gate is not None:
            parser.error('--expect and --gate belong to a file publication')
        os.execv(str(NATIVE), [str(NATIVE), '--manifest', str(args.manifest),
                               '--samples', args.samples])
        raise SystemExit(EXIT_IO)                      # unreachable
    return publish(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Failure as failure:
        print('publication failed: ' + failure.message, file=sys.stderr)
        raise SystemExit(failure.code)
    except OSError as error:
        print('publication failed: ' + str(error), file=sys.stderr)
        raise SystemExit(EXIT_IO)
    except (ValueError, KeyError, TypeError) as error:
        print('publication failed: ' + str(error), file=sys.stderr)
        raise SystemExit(EXIT_USAGE)
