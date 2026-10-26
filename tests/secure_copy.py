"""Snapshot candidate files without following untrusted filesystem links.

All source traversal is relative to pinned directory descriptors. A path is
opened with O_NOFOLLOW at every component; source node metadata is checked both
before and after opening. No candidate code runs before the snapshot finishes.
"""
import os
import errno
from pathlib import Path
import stat


class UnsafeCandidateTree(ValueError):
    pass


DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _directory_fd(path):
    absolute = os.path.abspath(os.fspath(path))
    descriptor = os.open(os.sep, DIR_FLAGS)
    try:
        for part in absolute.split(os.sep):
            if not part:
                continue
            next_descriptor = os.open(part, DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _copy_directory(source_fd, destination_fd):
    with os.scandir(source_fd) as entries:
        names = sorted(entry.name for entry in entries)
    for name in names:
        before = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode):
            raise UnsafeCandidateTree('symbolic link in candidate project: ' + repr(name))
        if not (stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode)):
            raise UnsafeCandidateTree('special node in candidate project: ' + repr(name))
        if name == '__pycache__' or name.endswith('.pyc'):
            continue
        if stat.S_ISDIR(before.st_mode):
            child_source = os.open(name, DIR_FLAGS, dir_fd=source_fd)
            try:
                current = os.fstat(child_source)
                if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                    raise UnsafeCandidateTree('directory changed during snapshot')
                os.mkdir(name, 0o700, dir_fd=destination_fd)
                child_destination = os.open(name, DIR_FLAGS, dir_fd=destination_fd)
                try:
                    _copy_directory(child_source, child_destination)
                    os.fchmod(child_destination, stat.S_IMODE(current.st_mode) & 0o777)
                finally:
                    os.close(child_destination)
            finally:
                os.close(child_source)
            continue
        if before.st_nlink != 1:
            raise UnsafeCandidateTree('hard link in candidate project: ' + repr(name))
        source = os.open(name, FILE_FLAGS, dir_fd=source_fd)
        try:
            current = os.fstat(source)
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                raise UnsafeCandidateTree('source file type changed during snapshot')
            if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                raise UnsafeCandidateTree('source file changed during snapshot')
            destination = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  0o600, dir_fd=destination_fd)
            try:
                while True:
                    chunk = os.read(source, 1024 * 1024)
                    if not chunk:
                        break
                    remaining = memoryview(chunk)
                    while remaining:
                        written = os.write(destination, remaining)
                        if written <= 0:
                            raise OSError(errno.EIO, 'snapshot write made no progress')
                        remaining = remaining[written:]
                after = os.fstat(source)
                if (after.st_size, after.st_mtime_ns, after.st_nlink) != (current.st_size, current.st_mtime_ns, 1):
                    raise UnsafeCandidateTree('source file mutated during snapshot')
                os.fchmod(destination, stat.S_IMODE(current.st_mode) & 0o777)
            finally:
                os.close(destination)
        finally:
            os.close(source)


def copy_candidate_tree(source, destination):
    """Copy ordinary files only, or reject before publishing/chowning the copy."""
    source_fd = None
    destination_fd = None
    try:
        source_fd = _directory_fd(source)
        Path(destination).mkdir(mode=0o700)
        destination_fd = _directory_fd(destination)
        _copy_directory(source_fd, destination_fd)
    except UnsafeCandidateTree:
        raise
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENOENT, errno.ESTALE):
            raise UnsafeCandidateTree('candidate snapshot rejected: ' + type(error).__name__) from error
        # Disk/transport/permission failures are infrastructure errors, never a
        # zero-score security verdict or a normal low mathematical score.
        raise
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        if source_fd is not None:
            os.close(source_fd)
