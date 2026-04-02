from __future__ import annotations

import os
from pathlib import Path
from shutil import which
from typing import Iterable

from PIL import Image, ImageOps

from app.models import PDFTextItem

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None


def _resolve_tessdata_prefix() -> str | None:
    candidates = []
    env_value = os.environ.get("TESSDATA_PREFIX")
    if env_value:
        candidates.append(Path(env_value))

    user_profile = Path.home()
    candidates.append(user_profile / "scoop" / "apps" / "tesseract" / "current" / "tessdata")
    candidates.append(Path(r"C:\Program Files\Tesseract-OCR\tessdata"))

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return str(candidate)
    return None


def tesseract_available() -> bool:
    return pytesseract is not None and which("tesseract") is not None


def _ocr_to_text_items(
    image: Image.Image,
    *,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    rotation: str = "none",
    source_width: int | None = None,
    source_height: int | None = None,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    psm: int = 11,
    extra_config: str = "",
) -> list[PDFTextItem]:
    tessdata_prefix = _resolve_tessdata_prefix()
    config = f"--psm {psm}"
    if tessdata_prefix:
        os.environ["TESSDATA_PREFIX"] = tessdata_prefix
    if extra_config:
        config = f"{config} {extra_config}".strip()

    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config=config,
        lang="eng",
    )
    results: list[PDFTextItem] = []
    count = len(data["text"])
    width, height = image.size
    base_width = source_width if source_width is not None else width
    base_height = source_height if source_height is not None else height

    for idx in range(count):
        text = (data["text"][idx] or "").strip()
        if not text:
            continue
        x0 = float(data["left"][idx]) / scale_x
        y0 = float(data["top"][idx]) / scale_y
        x1 = x0 + float(data["width"][idx]) / scale_x
        y1 = y0 + float(data["height"][idx]) / scale_y

        if rotation == "none":
            mapped = (x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y)
        elif rotation == "cw":
            mapped = (
                y0 + offset_x,
                (base_height - x1) + offset_y,
                y1 + offset_x,
                (base_height - x0) + offset_y,
            )
        elif rotation == "ccw":
            mapped = (
                (base_width - y1) + offset_x,
                x0 + offset_y,
                (base_width - y0) + offset_x,
                x1 + offset_y,
            )
        else:
            raise ValueError(f"Rotacion no soportada: {rotation}")

        results.append(PDFTextItem(text=text, x0=mapped[0], y0=mapped[1], x1=mapped[2], y1=mapped[3]))

    return results


def _prepare_ocr_variants(image: Image.Image) -> list[tuple[Image.Image, float, float]]:
    grayscale = ImageOps.autocontrast(ImageOps.grayscale(image))
    scale = 2.0 if max(grayscale.size) < 5000 else 1.5
    resized = grayscale.resize(
        (max(1, int(round(grayscale.width * scale))), max(1, int(round(grayscale.height * scale)))),
        Image.Resampling.LANCZOS,
    )
    binary = resized.point(lambda value: 255 if value > 185 else 0)
    return [
        (image, 1.0, 1.0),
        (resized, scale, scale),
        (binary, scale, scale),
    ]


def _default_border_regions(image: Image.Image) -> list[tuple[Image.Image, float, float, str, int, int, int, str]]:
    width, height = image.size
    border_x = max(220, int(round(width * 0.18)))
    border_y = max(120, int(round(height * 0.08)))
    return [
        (image.crop((0, 0, width, border_y)), 0.0, 0.0, "none", width, border_y, 6, ""),
        (image.crop((0, height - border_y, width, height)), 0.0, float(height - border_y), "none", width, border_y, 6, ""),
        (
            image.crop((0, 0, border_x, height)).transpose(Image.Transpose.ROTATE_270),
            0.0,
            0.0,
            "cw",
            border_x,
            height,
            6,
            "",
        ),
        (
            image.crop((width - border_x, 0, width, height)).transpose(Image.Transpose.ROTATE_270),
            float(width - border_x),
            0.0,
            "cw",
            border_x,
            height,
            6,
            "",
        ),
    ]


def _focused_border_regions(
    image: Image.Image,
    focus_bbox: tuple[float, float, float, float],
) -> list[tuple[Image.Image, float, float, str, int, int, int, str]]:
    width, height = image.size
    x0, y0, x1, y1 = [int(round(value)) for value in focus_bbox]
    outer_x = max(90, int(round(width * 0.016)))
    outer_y = max(80, int(round(height * 0.016)))
    inner_x = max(55, int(round(width * 0.008)))
    inner_y = max(55, int(round(height * 0.008)))
    pad_x = max(30, int(round(width * 0.005)))
    pad_y = max(30, int(round(height * 0.005)))

    left_box = (
        max(0, x0 - outer_x),
        max(0, y0 - pad_y),
        min(width, x0 + inner_x),
        min(height, y1 + pad_y),
    )
    right_box = (
        max(0, x1 - inner_x),
        max(0, y0 - pad_y),
        min(width, x1 + outer_x),
        min(height, y1 + pad_y),
    )
    top_box = (
        max(0, x0 - pad_x),
        max(0, y0 - outer_y),
        min(width, x1 + pad_x),
        min(height, y0 + inner_y),
    )
    bottom_box = (
        max(0, x0 - pad_x),
        max(0, y1 - inner_y),
        min(width, x1 + pad_x),
        min(height, y1 + outer_y),
    )

    coord_whitelist = "-c tessedit_char_whitelist=0123456789NSEWOnsew'\".,-"
    numeric_whitelist = "-c tessedit_char_whitelist=0123456789"
    return [
        (image.crop(top_box), float(top_box[0]), float(top_box[1]), "none", top_box[2] - top_box[0], top_box[3] - top_box[1], 6, coord_whitelist),
        (image.crop(bottom_box), float(bottom_box[0]), float(bottom_box[1]), "none", bottom_box[2] - bottom_box[0], bottom_box[3] - bottom_box[1], 6, coord_whitelist),
        (
            image.crop(left_box).transpose(Image.Transpose.ROTATE_270),
            float(left_box[0]),
            float(left_box[1]),
            "cw",
            left_box[2] - left_box[0],
            left_box[3] - left_box[1],
            6,
            coord_whitelist,
        ),
        (
            image.crop(right_box).transpose(Image.Transpose.ROTATE_270),
            float(right_box[0]),
            float(right_box[1]),
            "cw",
            right_box[2] - right_box[0],
            right_box[3] - right_box[1],
            6,
            coord_whitelist,
        ),
        (
            image.crop(left_box).transpose(Image.Transpose.ROTATE_270),
            float(left_box[0]),
            float(left_box[1]),
            "cw",
            left_box[2] - left_box[0],
            left_box[3] - left_box[1],
            6,
            numeric_whitelist,
        ),
        (
            image.crop(right_box).transpose(Image.Transpose.ROTATE_270),
            float(right_box[0]),
            float(right_box[1]),
            "cw",
            right_box[2] - right_box[0],
            right_box[3] - right_box[1],
            6,
            numeric_whitelist,
        ),
    ]


def extract_ocr_text_items(
    image: Image.Image,
    *,
    focus_bbox: tuple[float, float, float, float] | None = None,
) -> list[PDFTextItem]:
    if not tesseract_available():
        return []

    results: list[PDFTextItem] = []
    border_regions = _focused_border_regions(image, focus_bbox) if focus_bbox is not None else _default_border_regions(image)

    if focus_bbox is None:
        for variant, scale_x, scale_y in _prepare_ocr_variants(image):
            results.extend(_ocr_to_text_items(variant, scale_x=scale_x, scale_y=scale_y))

    for crop, offset_x, offset_y, rotation, source_width, source_height, psm, extra_config in border_regions:
        for variant, scale_x, scale_y in _prepare_ocr_variants(crop):
            results.extend(
                _ocr_to_text_items(
                    variant,
                    offset_x=offset_x,
                    offset_y=offset_y,
                    rotation=rotation,
                    source_width=source_width,
                    source_height=source_height,
                    scale_x=scale_x,
                    scale_y=scale_y,
                    psm=psm,
                    extra_config=extra_config,
                )
            )

    unique: dict[tuple[str, int, int, int, int], PDFTextItem] = {}
    for item in results:
        key = (
            item.text,
            int(round(item.x0)),
            int(round(item.y0)),
            int(round(item.x1)),
            int(round(item.y1)),
        )
        unique[key] = item

    return list(unique.values())


def crop_regions(image: Image.Image, boxes: Iterable[tuple[int, int, int, int]]) -> list[Image.Image]:
    return [image.crop(box) for box in boxes]
