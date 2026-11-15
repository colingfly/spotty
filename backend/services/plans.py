# backend/services/plans.py
"""
The three plans and what each one unlocks.

  free      one-click tracks on the fast model
  studio    better-sounding songs: XL model, Claude lyrics, full length, takes, references
  producer  working on a song: projects, section edits, stems, custom LoRAs

Payments are not built yet. While settings.pro_unlocked is true every account is
treated as a producer; set PRO_UNLOCKED=false to enforce the account's own plan.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from config import settings

FREE = "free"
STUDIO = "studio"
PRODUCER = "producer"
PLANS = (FREE, STUDIO, PRODUCER)
_RANK = {FREE: 0, STUDIO: 1, PRODUCER: 2}

# feature -> the lowest plan that includes it
FEATURES: Dict[str, str] = {
    "claude_lyrics": STUDIO,
    "long_tracks": STUDIO,
    "takes": STUDIO,
    "reference": STUDIO,
    "repaint": PRODUCER,
    "stems": PRODUCER,
    "projects": PRODUCER,
    "lora": PRODUCER,
}

FREE_MAX_DURATION = 60
LABELS = {
    "claude_lyrics": "Claude-written lyrics",
    "long_tracks": "tracks over a minute",
    "takes": "multiple takes",
    "reference": "reference tracks",
    "repaint": "editing a section",
    "stems": "stems",
    "projects": "producer projects",
    "lora": "custom LoRAs",
}


def plan_of(account: Any) -> str:
    if settings.pro_unlocked:
        return PRODUCER
    plan = getattr(account, "plan", None) or FREE
    return plan if plan in _RANK else FREE


def tier_allows(plan: str, tier: str) -> bool:
    return _RANK.get(plan, 0) >= _RANK.get(tier, 0)


def allows(plan: str, feature: str) -> bool:
    return tier_allows(plan, FEATURES[feature])


def denied(plan: str, feature: str) -> Optional[Tuple[dict, int]]:
    """None when the plan includes the feature, otherwise the 402 response to return."""
    if allows(plan, feature):
        return None
    need = FEATURES[feature]
    return {"error": "upgrade_required", "message": f"{LABELS[feature]} need the {need} plan.", "plan": plan, "needs": need}, 402


def describe(plan: str) -> Dict[str, Any]:
    return {
        "plan": plan,
        "enforced": not settings.pro_unlocked,
        "features": {f: allows(plan, f) for f in FEATURES},
        "feature_tiers": dict(FEATURES),
        "free_max_duration": FREE_MAX_DURATION,
    }
