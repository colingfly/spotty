# backend/services/engines.py
"""
The catalogue of song models a render can use, and the engine each one runs on.

An engine is a backend that turns a brief into audio (today only the ACE-Step
server). A model is one selectable option on an engine. Adding a model on an
existing engine is a new CATALOG entry; adding an engine means implementing
the Engine protocol and registering it in generation_service.ENGINES.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

from config import settings

FREE = "free"
STUDIO = "studio"
PRODUCER = "producer"


class Engine(Protocol):
    """
    What generation_service needs from a render backend.

    Poll results use ACE-Step's shape, which other engines adapt to:
    {"task_id", "status": 0 pending | 1 done | 2 failed, "result": [{"file": <ref for download()>}], "error"}.
    """

    def health_check(self, max_age: float = 5.0) -> bool: ...
    def submit_task(self, params: Dict[str, Any], files: Optional[Dict[str, tuple]] = None) -> str: ...
    def query_results(self, task_ids: List[str]) -> Dict[str, Dict[str, Any]]: ...
    def query_result(self, task_id: str) -> Dict[str, Any]: ...
    def download(self, file_ref: str) -> bytes: ...


@dataclass(frozen=True)
class SongModel:
    id: str
    label: str
    description: str
    engine: str                       # key into generation_service.ENGINES
    engine_model: Optional[str]       # the engine's own name for it
    tier: str                         # the lowest plan that can use it: free | studio | producer
    infer_steps: int
    max_duration: int                 # seconds
    capabilities: Tuple[str, ...]     # vocals, repaint, extend, cover

    def engine_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {"infer_steps": self.infer_steps}
        if self.engine_model:
            params["model"] = self.engine_model
        return params

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["capabilities"] = list(self.capabilities)
        d.pop("engine_model")
        return d


CATALOG: List[SongModel] = [
    SongModel(
        id="ace-turbo",
        label="ACE-Step turbo",
        description="ACE-Step 1.5 turbo: 2B model, 8 steps. Fastest render.",
        engine="acestep",
        engine_model="acestep-v15-turbo",
        tier=FREE,
        infer_steps=8,
        max_duration=120,
        capabilities=("vocals",),
    ),
    SongModel(
        id="ace-xl-turbo",
        label="ACE-Step XL",
        description="ACE-Step 1.5 XL turbo: 4B model, 8 steps. Higher fidelity, slightly slower.",
        engine="acestep",
        engine_model="acestep-v15-xl-turbo",
        tier=STUDIO,
        infer_steps=8,
        max_duration=settings.max_duration_seconds,
        capabilities=("vocals", "repaint", "extend", "cover"),
    ),
]

DEFAULT_MODEL_ID = CATALOG[0].id
_BY_ID = {m.id: m for m in CATALOG}


def get_model(model_id: Optional[str]) -> SongModel:
    """Unknown or missing ids fall back to the default so old rows and clients keep working."""
    return _BY_ID.get(model_id or "", _BY_ID[DEFAULT_MODEL_ID])


def find_model(model_id: Optional[str]) -> Optional[SongModel]:
    return _BY_ID.get(model_id or "")


def model_with(capability: str, preferred: Optional[str] = None) -> Optional[SongModel]:
    """The preferred model if it has the capability, otherwise the first model that does."""
    want = _BY_ID.get(preferred or "")
    if want and capability in want.capabilities:
        return want
    return next((m for m in CATALOG if capability in m.capabilities), None)


def catalog() -> List[Dict[str, Any]]:
    return [m.to_dict() for m in CATALOG]
