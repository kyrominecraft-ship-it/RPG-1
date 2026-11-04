"""Durable local file primitives; Windows writes deny concurrent writers/deleters."""
import ctypes
import os
from contextlib import contextmanager
from pathlib import Path


def durable_write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def locked_file(path, exclusive_write=False):
    if os.name == 'nt' and exclusive_write:
        import msvcrt
        from ctypes import wintypes
        create = ctypes.WinDLL('kernel32', use_last_error=True).CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        # Share READ only: another writer/deleter (including editor saves) cannot race us.
        handle = create(str(Path(path).resolve()), 0xC0000000, 1, None, 3, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), 'File is busy; close the editor and retry')
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        with os.fdopen(descriptor, 'r+b') as stream:
            yield stream
    else:
        with open(path, 'r+b') as stream:
            if os.name != 'nt':
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield stream


@contextmanager
def campaign_lock(path):
    path.touch(exist_ok=True)
    with open(path, 'r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
