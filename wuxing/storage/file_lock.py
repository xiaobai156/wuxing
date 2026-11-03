from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile
import threading
from typing import Iterator


_PROCESS_LOCK = threading.RLock()


@contextmanager
def exclusive_file_lock(path: str | Path) -> Iterator[None]:
    target = Path(path)
    temporary_lock = target.suffix.lower() == ".txt"
    lock_path = (
        Path(tempfile.gettempdir())
        / "wuxing-file-locks"
        / f"txt-{hashlib.sha256(str(target.resolve()).casefold().encode()).hexdigest()}"
        if temporary_lock
        else Path(f"{target}.lock")
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESS_LOCK:
        try:
            with lock_path.open("a+b") as handle:
                try:
                    import msvcrt

                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                except (ImportError, OSError):
                    msvcrt = None
                try:
                    yield
                finally:
                    if msvcrt is not None:
                        handle.seek(0)
                        try:
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        except OSError:
                            pass
        finally:
            if temporary_lock:
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
