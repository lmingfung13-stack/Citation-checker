import os
import shutil
import tempfile
import uuid


class TempWorkDir:
    def __init__(self, prefix: str = "job", root_name: str = "citation_checker_temp"):
        base_root = tempfile.gettempdir()
        self._root_dir = os.path.abspath(os.path.join(base_root, root_name))
        self._prefix = prefix
        self.path = None

    def create(self):
        os.makedirs(self._root_dir, exist_ok=True)
        self.path = os.path.abspath(
            os.path.join(self._root_dir, f"{self._prefix}_{uuid.uuid4().hex}")
        )
        os.makedirs(self.path, exist_ok=True)
        return self

    def file_path(self, filename: str) -> str:
        if not self.path:
            raise RuntimeError("Temp work dir is not created.")
        return os.path.abspath(os.path.join(self.path, filename))

    def cleanup(self):
        if not self.path:
            return
        try:
            shutil.rmtree(self.path, ignore_errors=True)
        finally:
            self.path = None

    def __enter__(self):
        return self.create()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def create_temp_work_dir(prefix: str = "job") -> TempWorkDir:
    return TempWorkDir(prefix=prefix).create()
