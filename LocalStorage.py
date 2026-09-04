import os
from pathlib import Path
from typing import Any, Dict, Union

from chainlit.data.storage_clients.base import BaseStorageClient

UPLOAD_DIR = Path(__file__).parent / ".uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


class LocalStorageClient(BaseStorageClient):

    def __init__(self, base_url: str = "/uploads"):
        self.base_url = base_url.rstrip("/")

    def _resolve(self, object_key: str) -> Path:
        path = (UPLOAD_DIR / object_key).resolve()
        if UPLOAD_DIR.resolve() not in path.parents and path != UPLOAD_DIR.resolve():
            raise ValueError(f"Invalid object_key: {object_key!r}")
        return path

    async def upload_file(
        self,
        object_key: str,
        data: Union[bytes, str],
        mime: str = "application/octet-stream",
        overwrite: bool = True,
        content_disposition: str | None = None,
    ) -> Dict[str, Any]:
        path = self._resolve(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not overwrite and path.exists():
            return {"object_key": object_key, "url": f"{self.base_url}/{object_key}"}

        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with open(path, mode) as f:
            f.write(data)

        return {"object_key": object_key, "url": f"{self.base_url}/{object_key}"}

    async def delete_file(self, object_key: str) -> bool:
        path = self._resolve(object_key)
        if path.exists():
            os.remove(path)
            return True
        return False

    async def get_read_url(self, object_key: str) -> str:
        return f"{self.base_url}/{object_key}"

    async def close(self) -> None:
        return None
