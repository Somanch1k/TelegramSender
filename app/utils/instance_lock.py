"""Prevent multiple copies of the sender from using one Telegram session."""

import os
from pathlib import Path


class InstanceLock:
    """An advisory process lock on Linux; a no-op on platforms without fcntl."""

    def __init__(self, path: Path):
        self.path = path
        self._file = None

    def acquire(self):
        try:
            import fcntl
        except ImportError:
            # The production service runs on Linux. Do not break local Windows use.
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._file.close()
            self._file = None
            raise RuntimeError(
                "Уже запущен другой экземпляр Telegram Sender. "
                "Используйте только systemctl для перезапуска сервиса."
            ) from error

        self._file.seek(0)
        self._file.truncate()
        self._file.write(str(os.getpid()))
        self._file.flush()

    def release(self):
        if self._file is None:
            return
        try:
            import fcntl
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        except ImportError:
            pass
        finally:
            self._file.close()
            self._file = None
