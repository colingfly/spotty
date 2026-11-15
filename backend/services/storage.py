# backend/services/storage.py
"""
Durable storage for rendered audio.

The backend's own disk is a cache: on hosts like Render's free tier it is wiped
on every deploy. When BLOB_READ_WRITE_TOKEN is set, each finished track is also
written to a private Vercel Blob store and pulled back to disk on demand.
Without the token everything stays local, which is fine for development.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from config import settings

log = logging.getLogger("spotty.storage")

_API = "https://blob.vercel-storage.com"
_API_VERSION = "7"


def enabled() -> bool:
    return bool(settings.blob_token)


def _auth() -> dict:
    return {"authorization": f"Bearer {settings.blob_token}", "x-api-version": _API_VERSION}


def upload(pathname: str, data: bytes, content_type: str = "audio/mpeg") -> Optional[str]:
    """Store bytes at a fixed pathname and return the blob URL, or None when disabled or failed."""
    if not enabled():
        return None
    try:
        r = requests.put(
            f"{_API}/{pathname}",
            data=data,
            headers={
                **_auth(),
                "x-vercel-blob-access": "private",
                "x-add-random-suffix": "0",
                "x-allow-overwrite": "1",
                "content-type": content_type,
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("url")
    except Exception as e:
        log.warning("Blob upload failed for %s: %s", pathname, e)
        return None


def restore(url: str, local_path: str) -> bool:
    """Download a blob back to the local cache. Returns True when the file is in place."""
    if not enabled() or not url:
        return False
    try:
        r = requests.get(url, headers=_auth(), timeout=120)
        r.raise_for_status()
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        tmp = f"{local_path}.part"
        with open(tmp, "wb") as fp:
            fp.write(r.content)
        os.replace(tmp, local_path)
        return True
    except Exception as e:
        log.warning("Blob restore failed for %s: %s", url, e)
        return False


def delete(url: str) -> None:
    if not enabled() or not url:
        return
    try:
        requests.post(f"{_API}/delete", json={"urls": [url]}, headers=_auth(), timeout=30).raise_for_status()
    except Exception as e:
        log.warning("Blob delete failed for %s: %s", url, e)
