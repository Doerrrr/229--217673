"""Non-scoring controls for fixed-identity child reads and unchanged parent IDs."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('identity_reader', args.tests / 'output_reader.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    # This author control runs in its own root Docker process. It never changes
    # the host identity, and restores only the literal initial Docker IDs.
    def identity():
        return os.geteuid(), os.getegid(), os.getgroups()
    assert identity() == (0, 0, [0]), 'author Docker must start with root UID/GID/group 0'
    root = Path(tempfile.mkdtemp(prefix='eb032-reader-identities-', dir='/tmp'))
    root.chmod(0o755)
    ordinary = root / 'ordinary.jsonl'
    ordinary.write_bytes(b'{"id":"x"}\r\n')
    os.chown(ordinary, 10001, 10001)
    records = []

    def record(name):
        records.append(dict(case=name, status='PASS'))

    def read(name, path, expected):
        before = identity()
        started = time.monotonic()
        assert reader.rows_from(path) == expected, name
        assert identity() == before, (name, 'identity not restored')
        assert time.monotonic() - started < 1.0, (name, 'reader blocked')
        record(name)

    read('ordinary_crlf', ordinary, [dict(id='x')])
    ordinary.chmod(0)
    read('candidate_owned_mode_000', ordinary, [dict(id='x')])
    assert stat.S_IMODE(ordinary.stat().st_mode) == 0
    ordinary.chmod(0o600)
    readable = root / 'readable-link'
    readable.symlink_to(ordinary)
    read('readable_symlink', readable, [dict(id='x')])
    private = root / 'private.jsonl'
    private.write_bytes(b'{"private":true}\n')
    private.chmod(0o600)
    hidden = root / 'private-link'
    hidden.symlink_to(private)
    read('private_symlink_denied', hidden, [])
    fifo = root / 'answer.fifo'
    os.mkfifo(fifo)
    os.chown(fifo, 10001, 10001)
    read('fifo_returns_without_writer', fifo, [])
    read('directory_is_not_output', root, [])
    read('missing_output', root / 'missing', [])
    malformed = root / 'malformed.jsonl'
    malformed.write_bytes(b'{\n')
    os.chown(malformed, 10001, 10001)
    read('malformed_json', malformed, [])
    recursive = root / 'recursive.jsonl'
    recursive.write_bytes(b'[' * 10000 + b']' * 10000)
    os.chown(recursive, 10001, 10001)
    read('recursive_json', recursive, [])

    # Rejected environments must not open files, fork, or change any IDs.
    cases = [
        ('negative_uid', -1, 0, [0]), ('oversized_uid', 65536, 0, [0]),
        ('negative_gid', 0, -1, [0]), ('oversized_gid', 0, 65536, [0]),
        ('negative_supplementary_gid', 0, 0, [0, -1]),
        ('oversized_supplementary_gid', 0, 0, [0, 65536]),
    ]
    for name, fake_uid, fake_gid, fake_groups in cases:
        with patch.object(reader.os, 'geteuid', return_value=fake_uid), \
             patch.object(reader.os, 'getegid', return_value=fake_gid), \
             patch.object(reader.os, 'getgroups', return_value=fake_groups), \
             patch.object(reader.os, 'seteuid') as set_uid, \
             patch.object(reader.os, 'setegid') as set_gid, \
             patch.object(reader.os, 'setgroups') as set_groups, \
             patch.object(reader.os, 'fork') as fork, \
             patch.object(reader.os, 'open') as open_file:
            try:
                reader.rows_from(ordinary)
            except RuntimeError as error:
                assert '0..65535' in str(error)
            else:
                raise AssertionError('unsupported identity accepted: ' + name)
            for mocked in (set_uid, set_gid, set_groups, open_file, fork):
                mocked.assert_not_called()
        assert identity() == (0, 0, [0])
        record(name + '_rejected_before_mutation')

    os.setegid(65535)
    os.setgroups([0, 65535])
    try:
        read('maximum_gid_and_groups_restore_exactly', ordinary, [dict(id='x')])
    finally:
        os.setegid(0)
        os.setgroups([0])
    os.setgroups([])
    try:
        read('empty_supplementary_groups_restore_exactly', ordinary, [dict(id='x')])
    finally:
        os.setgroups([0])
    nonroot = root / 'nonroot.jsonl'
    nonroot.write_bytes(b'{"id":"max-uid"}\n')
    os.chown(nonroot, 65535, 65535)
    nonroot.chmod(0o600)
    os.setgroups([])
    os.setegid(65535)
    os.seteuid(65535)
    try:
        read('maximum_nonroot_uid_without_identity_change', nonroot, [dict(id='max-uid')])
    finally:
        os.seteuid(0)
        os.setegid(0)
        os.setgroups([0])

    original_reader = reader._candidate_bytes
    ordinary.chmod(0)
    def fail_fchmod(path):
        with patch.object(reader.os, 'fchmod', side_effect=OSError('author fchmod failure')):
            return original_reader(path)
    with patch.object(reader, '_candidate_bytes', side_effect=fail_fchmod):
        try:
            reader.rows_from(ordinary)
        except RuntimeError as error:
            assert 'author fchmod failure' in str(error)
        else:
            raise AssertionError('cleanup failure was hidden')
    assert identity() == (0, 0, [0])
    ordinary.chmod(0o600)
    record('child_fchmod_failure_parent_identity_unchanged')

    real_close = os.close
    def close_then_fail(descriptor):
        real_close(descriptor)
        raise OSError('author close failure')
    def fail_close(path):
        with patch.object(reader.os, 'close', side_effect=close_then_fail):
            return original_reader(path)
    with patch.object(reader, '_candidate_bytes', side_effect=fail_close):
        try:
            reader.rows_from(ordinary)
        except RuntimeError as error:
            assert 'author close failure' in str(error)
        else:
            raise AssertionError('close failure was hidden')
    assert identity() == (0, 0, [0])
    record('child_close_failure_parent_identity_unchanged')
    def fail_read(path):
        with patch.object(reader.os, 'fdopen', side_effect=OSError('author read failure')):
            return original_reader(path)
    with patch.object(reader, '_candidate_bytes', side_effect=fail_read):
        read('child_read_failure_parent_identity_unchanged', ordinary, [])

    parent_pid = os.getpid()
    def inspect_child(path):
        assert os.getpid() != parent_pid, 'candidate file read in parent'
        assert identity() == (10001, 10001, []), 'worker identity differs from fixed candidate IDs'
        return original_reader(path)
    with patch.object(reader, '_candidate_bytes', side_effect=inspect_child), \
         patch.object(reader.os, 'seteuid', side_effect=AssertionError('effective UID changes forbidden')), \
         patch.object(reader.os, 'setegid', side_effect=AssertionError('effective GID changes forbidden')):
        read('read_occurs_in_fixed_identity_child_only', ordinary, [dict(id='x')])

    large = root / 'large.jsonl'
    expected = dict(value='x' * (2 * 1024 * 1024))
    large.write_text(json.dumps(expected) + '\n')
    os.chown(large, 10001, 10001)
    read('pipe_transfers_more_than_its_buffer_without_truncation', large, [expected])

    def abrupt_exit(path):
        os._exit(7)
    with patch.object(reader, '_candidate_bytes', side_effect=abrupt_exit):
        try:
            reader.rows_from(ordinary)
        except RuntimeError as error:
            assert 'abnormal child exit' in str(error)
        else:
            raise AssertionError('child exit was treated as candidate output')
    assert identity() == (0, 0, [0])
    record('abrupt_child_exit_reports_verifier_error')

    with patch.object(reader.os, 'setuid', side_effect=OSError('author identity drop failed')):
        try:
            reader.rows_from(ordinary)
        except RuntimeError as error:
            assert 'author identity drop failed' in str(error)
        else:
            raise AssertionError('identity drop failure was hidden')
    assert identity() == (0, 0, [0])
    record('child_identity_drop_failure_keeps_parent_identity')

    pipe_fds = []
    real_pipe = os.pipe
    def tracked_pipe():
        pair = real_pipe()
        pipe_fds.extend(pair)
        return pair
    with patch.object(reader.os, 'pipe', side_effect=tracked_pipe), \
         patch.object(reader.os, 'fork', side_effect=OSError('author fork failed')):
        try:
            reader.rows_from(ordinary)
        except OSError as error:
            assert 'author fork failed' in str(error)
        else:
            raise AssertionError('fork failure was hidden')
    for descriptor in pipe_fds:
        try:
            os.fstat(descriptor)
        except OSError:
            pass
        else:
            raise AssertionError('pipe descriptor leaked after fork failure')
    assert len(pipe_fds) == 2 and identity() == (0, 0, [0])
    record('fork_failure_closes_both_pipe_descriptors')
    try:
        os.waitpid(-1, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        raise AssertionError('output reader left an unreaped child')
    record('all_output_workers_reaped')

    result = dict(status='PASS', scope='NON_SCORING_FIXED_CHILD_IDENTITY_CONTROLS',
                  records=records, total=len(records), model_calls=0, platform_tests=0,
                  platform_static_gate_reassessment=False)
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status='PASS', controls=len(records))))


if __name__ == '__main__':
    main()
