"""Retry ambiguous Celsius glyphs against the source image, without guessing units.

Only a numeric ``C/c`` next to a temperature label, or an existing ``°c``, is
eligible. Two *different source-image crops* must explicitly recognize ``°C``
with the same number and sign at >= 0.85 confidence. The retries share one OCR
model, so this is corroboration rather than independent statistical evidence.
Only the unit span is changed; values, signs and other text stay untouched.
Every attempted crop and an unresolved outcome are returned for audit.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

NUMBER = r"[+\-−–]?\s*\d+(?:[.,]\d+)?"
_SUSPECT = re.compile(
    rf"(?<![\w.,])(?P<number>{NUMBER})\s*(?P<unit>[°º]?\s*[cC])(?!\w)"
)
_CELSIUS = re.compile(
    rf"(?<![\w.,])(?P<number>{NUMBER})\s*(?:°\s*C|℃)(?!\w)"
)
_OTHER_DEGREE_UNIT = re.compile(
    rf"(?<![\w.,])(?P<number>{NUMBER})\s*°\s*(?P<unit>[FK])(?!\w)"
)
_NUMBERS = re.compile(rf"(?<![\w.,])(?P<number>{NUMBER})")
_TEMPERATURE_CONTEXT = re.compile(
    r"온도|녹는점|어는점|끓는점|인화점|발화|융점|비등|연화점|분해|비점|증기압|용해도"
    r"|temperature|melting|boiling|flash\s*point|solubility|vapo[u]?r\s*pressure",
    re.IGNORECASE,
)
MIN_RETRY_SCORE = 0.85
MIN_DISTINCT_CROPS = 2

# Fractions of detector-box height. Different horizontal/vertical padding can
# recover the small raised circle that the original tight line crop missed.
_PADDINGS = (
    (0.0, 0.0), (0.1, 0.1), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4),
    (0.1, 0.3), (0.1, 0.5), (0.2, 0.4), (0.2, 0.5), (0.3, 0.45),
    (0.4, 0.5),
)


def build_unit_recognizer(device: str = "cpu", model_dir: str | Path | None = None):
    """Build only the cached Korean line recognizer; never download a model."""
    model_dir = Path(model_dir or Path.home() / ".paddlex/official_models/korean_PP-OCRv5_mobile_rec")
    if not (model_dir / "inference.yml").is_file():
        raise FileNotFoundError(f"Cached unit recognizer not found: {model_dir}")
    from paddleocr import TextRecognition

    kwargs = {"enable_mkldnn": False, "cpu_threads": 4} if device == "cpu" else {}
    return TextRecognition(
        model_name="korean_PP-OCRv5_mobile_rec", model_dir=str(model_dir),
        device=device, **kwargs,
    )


def _number_key(text: str) -> str:
    # Comparing equivalent minus glyphs never changes the original sign.
    return "".join(text.split()).translate(str.maketrans({"−": "-", "–": "-"}))


def _box(item: dict) -> list[float]:
    return [float(x) for x in item.get("box", item.get("bbox", []))]


def _context(item: dict, items: list[dict]) -> str:
    x0, y0, _, y1 = _box(item)
    cy, height = (y0 + y1) / 2, max(1.0, y1 - y0)
    labels = [str(item.get("text", ""))]
    for other in items:
        if other is item or len(_box(other)) != 4:
            continue
        ox0, oy0, ox1, oy1 = _box(other)
        if ox0 < x0 and ox1 <= x0 + height and abs((oy0 + oy1) / 2 - cy) <= height * 0.6:
            labels.append(str(other.get("text", "")))
    return " ".join(labels)


def _suspects(item: dict, items: list[dict]) -> list[re.Match]:
    text = str(item.get("text", ""))
    has_context = bool(_TEMPERATURE_CONTEXT.search(_context(item, items)))
    return [
        match for match in _SUSPECT.finditer(text)
        if "".join(match.group("unit").split()) != "°C"
        and (has_context or "°" in match.group("unit"))
    ]


def _crop_boxes(item: dict, suspects: list[re.Match], width: int, height: int) -> list[list[int]]:
    x0, y0, x1, y1 = _box(item)
    line_height = max(1.0, y1 - y0)
    bases = [(x0, y0, x1, y1)]
    text = str(item["text"])
    # Focus crops are proposals only. Their OCR must still contain the exact
    # unique numeric token; approximate character positions never supply text.
    for match in suspects:
        left = x0 + (x1 - x0) * match.start() / max(1, len(text))
        right = x0 + (x1 - x0) * match.end() / max(1, len(text))
        bases.append((left - line_height * 0.5, y0, right + line_height * 0.5, y1))
    out = []
    seen = set()
    for base in bases:
        for px, py in _PADDINGS:
            box = [
                max(0, math.floor(base[0] - line_height * px)),
                max(0, math.floor(base[1] - line_height * py)),
                min(width, math.ceil(base[2] + line_height * px)),
                min(height, math.ceil(base[3] + line_height * py)),
            ]
            key = tuple(box)
            if key not in seen and box[2] > box[0] and box[3] > box[1]:
                out.append(box)
                seen.add(key)
    return out


def _read_crop(recognizer: Any, image: Any) -> tuple[str, float]:
    result = recognizer.predict(image)[0]
    value = getattr(result, "json", result)
    value = value() if callable(value) else value
    value = json.loads(value) if isinstance(value, str) else value
    value = value.get("res", value)
    return str(value.get("rec_text", "")), float(value.get("rec_score", 0.0))


def repair_unit_items(
    items: list[dict], image: str | Path, recognizer: Any = None,
) -> tuple[list[dict], list[dict]]:
    """Return copied OCR items and complete applied/unresolved crop audit.

    ``items`` use ``text``, ``box`` (or ``bbox``), and optional ``confidence``.
    The caller should also save its complete original detector/recognizer output.
    Empty/no-candidate pages do not load the image or instantiate an OCR model.
    """
    repaired = [dict(item) for item in items]
    candidates = [
        (index, _suspects(item, items)) for index, item in enumerate(items)
        if len(_box(item)) == 4
    ]
    candidates = [(index, matches) for index, matches in candidates if matches]
    if not candidates:
        return repaired, []

    import numpy as np
    from PIL import Image

    recognizer = recognizer if recognizer is not None else build_unit_recognizer()
    audit = []
    with Image.open(image) as source:
        source = source.convert("RGB")
        for index, matches in candidates:
            item, before = items[index], str(items[index]["text"])
            record = {
                "item_index": index, "raw_text": before, "before": before,
                "after": before, "box": _box(item),
                "original_confidence": item.get("confidence", item.get("score")),
                "policy": {"min_score": MIN_RETRY_SCORE, "min_distinct_crops": MIN_DISTINCT_CROPS,
                           "numeric_and_sign_preserved": True, "replacement": "unit_span_only"},
                "recognizer": "korean_PP-OCRv5_mobile_rec",
                "retries": [], "unit_decisions": [], "applied": False,
            }
            for crop_box in _crop_boxes(item, matches, source.width, source.height):
                # Paddle's ndarray input is BGR, unlike PIL's RGB image.
                crop = np.asarray(source.crop(tuple(crop_box)))[:, :, ::-1].copy()
                try:
                    retry_text, retry_score = _read_crop(recognizer, crop)
                    record["retries"].append({"crop_box": crop_box, "text": retry_text,
                                              "score": retry_score})
                except Exception as error:
                    record["retries"].append({"crop_box": crop_box, "text": "", "score": 0.0,
                                              "error": f"{type(error).__name__}: {error}"})

            replacements = []
            for match in matches:
                number = _number_key(match.group("number"))
                # A crop with a repeated numeric value cannot tell which unit
                # occurrence it supports; keep the source OCR and flag review.
                repeated = sum(_number_key(m.group("number")) == number for m in _NUMBERS.finditer(before)) > 1
                support, conflicts = [], []
                for retry_no, retry in enumerate(record["retries"]):
                    if retry["score"] < MIN_RETRY_SCORE:
                        continue
                    if any(_number_key(m.group("number")) == number for m in _CELSIUS.finditer(retry["text"])):
                        support.append(retry_no)
                    if any(_number_key(m.group("number")) == number for m in _OTHER_DEGREE_UNIT.finditer(retry["text"])):
                        conflicts.append(retry_no)
                apply = not repeated and not conflicts and len(support) >= MIN_DISTINCT_CROPS
                reason = ("source_crop_celsius_agreement" if apply else
                          "repeated_numeric_value" if repeated else
                          "conflicting_degree_unit" if conflicts else "insufficient_source_crop_agreement")
                record["unit_decisions"].append({
                    "original_unit": match.group("unit"), "number": match.group("number"),
                    "span": [match.start("unit"), match.end("unit")],
                    "supporting_retry_indices": support, "conflicting_retry_indices": conflicts,
                    "applied": apply, "reason": reason,
                })
                if apply:
                    replacements.append((match.start("unit"), match.end("unit"), "°C"))
            after = before
            for start, end, replacement in sorted(replacements, reverse=True):
                after = after[:start] + replacement + after[end:]
            record.update(after=after, applied=bool(replacements),
                          needs_review=any(not decision["applied"] for decision in record["unit_decisions"]))
            repaired[index].update(text=after, raw_ocr_text=before,
                                   unit_fidelity_needs_review=record["needs_review"])
            audit.append(record)
    return repaired, audit
