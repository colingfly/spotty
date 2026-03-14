# backend/services/ocr.py
from __future__ import annotations

import io
from typing import List

import cv2
import numpy as np
import pytesseract
from PIL import Image, UnidentifiedImageError


def ocr_text_from_image(file_bytes: bytes) -> str:
    try:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except UnidentifiedImageError:
        raise ValueError("Not a valid image file.")

    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    th = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 41, 10
    )
    pil = Image.fromarray(th)
    try:
        return pytesseract.image_to_string(pil, lang="eng")
    except (OSError, pytesseract.TesseractNotFoundError) as e:
        raise RuntimeError("OCR unavailable on this server") from e


def tokenize_candidate_lines(text_blob: str) -> List[str]:
    raw = [ln.strip() for ln in text_blob.splitlines()]
    keep: List[str] = []
    bad = {"doors", "live", "stage", "tickets", "am", "pm", "show", "venue"}

    for ln in raw:
        if not ln or len(ln) < 2:
            continue
        if any(ch.isdigit() for ch in ln) and len(ln) <= 4:
            continue
        clean = "".join(
            ch for ch in ln if ch.isalnum() or ch.isspace() or ch in "&-.'"
        )
        if not clean:
            continue
        words = clean.split()
        if len(words) > 7:
            continue
        if clean.lower() in bad:
            continue
        keep.append(clean.strip())

    seen: set = set()
    out: List[str] = []
    for k in keep:
        low = k.lower()
        if low not in seen:
            seen.add(low)
            out.append(k)
    return out


def jaccard(a, b) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0
