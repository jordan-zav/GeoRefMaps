from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from PIL import Image

from app.models import CoordinateCandidate, CornerDetection, GridLine, PDFTextItem


PROJECTED_RE = re.compile(r"(?<!\d)(\d{3,7}(?:[.,]\d{1,3})?)(?!\d)")
DMS_RE = re.compile(
    r"(?P<deg>\d{1,3})\s*(?:[°º])?\s*(?P<min>\d{1,2})\s*['’]?\s*(?P<sec>\d{1,2}(?:[.,]\d+)?)\s*[\"”']*\s*(?P<hem>[NSEWO])",
    re.IGNORECASE,
)
DECIMAL_GEO_RE = re.compile(
    r"(?<!\d)(?P<value>-?\d{1,3}(?:[.,]\d+))\s*(?:[°º])?\s*(?P<hem>[NSEWO])",
    re.IGNORECASE,
)
COMPACT_DMS_RE = re.compile(
    r"(?P<degmin>\d{4,5})\s*['’]\s*(?P<sec>\d{1,2}(?:[.,]\d+)?)\s*[\"”']*\s*(?P<hem>[NSEWO])",
    re.IGNORECASE,
)


@dataclass
class DetectionResult:
    corners: list[CornerDetection]
    candidates: list[CoordinateCandidate]
    mode: str
    notes: list[str]
    focus_bbox: tuple[float, float, float, float] | None = None
    mode_candidates: list[str] | None = None
    axis_counts: dict[str, int] | None = None


def _normalize_number(text: str) -> float:
    cleaned = text.replace(" ", "")
    if cleaned.count(",") > 1 and "." not in cleaned:
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") > 1 and "," not in cleaned:
        cleaned = cleaned.replace(".", "")
    else:
        cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).upper()


def _dms_to_decimal(degrees: str, minutes: str, seconds: str, hemisphere: str) -> float:
    value = _normalize_number(degrees) + _normalize_number(minutes) / 60.0 + _normalize_number(seconds) / 3600.0
    if hemisphere.upper() in {"S", "W", "O"}:
        return -value
    return value


def _compact_dms_to_decimal(degmin: str, seconds: str, hemisphere: str) -> float | None:
    digits = re.sub(r"[^0-9]", "", degmin)
    if len(digits) not in {4, 5}:
        return None

    if len(digits) == 5 and digits[-3] == "9":
        degrees = digits[:-3]
        minutes = digits[-2:]
    else:
        degrees = digits[:-2]
        minutes = digits[-2:]

    if not degrees or not minutes:
        return None
    return _dms_to_decimal(degrees, minutes, seconds, hemisphere)


def _classify_projected(value: float) -> tuple[str, str] | None:
    if 150000 <= value <= 900000:
        return ("E", "projected")
    if 8000000 <= value <= 10000000:
        return ("N", "projected")
    return None


def _classify_geographic(value: float, suffix: str) -> tuple[str, str] | None:
    suffix = suffix.upper()
    if suffix in {"E", "W", "O"} and abs(value) <= 180:
        return ("LON", "geographic")
    if suffix in {"N", "S"} and abs(value) <= 90:
        return ("LAT", "geographic")
    return None


def _projected_value_variants(
    value_text: str,
    item: PDFTextItem,
    page_width: float,
    page_height: float,
) -> list[tuple[float, str]]:
    cleaned_digits = re.sub(r"[^0-9]", "", value_text)
    if not cleaned_digits:
        return []

    values: list[tuple[float, str]] = []
    parsed_value = _normalize_number(value_text)
    rounded_value = round(parsed_value / 1000.0) * 1000.0
    if abs(parsed_value - rounded_value) <= 250:
        parsed_value = rounded_value
    values.append((parsed_value, value_text))

    if cleaned_digits.startswith("0"):
        return values

    digit_count = len(cleaned_digits)
    integer_value = float(cleaned_digits)
    # Solo expandimos fragmentos cortos en raster, donde las dimensiones del "page"
    # coinciden con pixeles y el OCR suele comerse ceros en bordes.
    if page_width < 5000 or page_height < 4000:
        return values

    center_x, center_y = item.center
    is_lateral = item.y1 - item.y0 > item.x1 - item.x0 or center_x < page_width * 0.15 or center_x > page_width * 0.85
    is_top_or_bottom = center_y < page_height * 0.18 or center_y > page_height * 0.82

    if digit_count == 5 and is_top_or_bottom:
        values.append((integer_value * 10.0, f"{cleaned_digits}0"))
    if digit_count == 4 and is_top_or_bottom:
        values.append((integer_value * 100.0, f"{cleaned_digits}00"))
    if digit_count == 5 and is_lateral:
        values.append((integer_value * 100.0, f"{cleaned_digits}00"))
    if digit_count == 4 and is_lateral:
        values.append((integer_value * 1000.0, f"{cleaned_digits}000"))
    if digit_count == 6 and is_lateral and 800000 <= integer_value <= 1000000:
        values.append((integer_value * 10.0, f"{cleaned_digits}0"))

    unique: dict[int, tuple[float, str]] = {}
    for value, raw in values:
        rounded = round(value / 1000.0) * 1000.0
        if abs(value - rounded) <= 250:
            value = rounded
        unique[int(round(value))] = (value, raw)
    return list(unique.values())


def infer_main_map_bbox_from_title(
    items: list[PDFTextItem],
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    title_tokens = [
        item
        for item in items
        if item.y0 < page_height * 0.2
        and any(token in _normalize_text(item.text) for token in ("MAPA", "GEOLOGIC", "CUADRANGULO", "HOJA"))
    ]
    if len(title_tokens) < 2:
        return None

    title_y = min(item.y0 for item in title_tokens)
    title_tokens = [item for item in title_tokens if abs(item.y0 - title_y) <= max(24.0, page_height * 0.02)]
    if len(title_tokens) < 2:
        return None

    x0 = min(item.x0 for item in title_tokens) - page_width * 0.18
    x1 = max(item.x1 for item in title_tokens) + page_width * 0.18
    y0 = max(0.0, max(item.y1 for item in title_tokens) + page_height * 0.02)
    y1 = min(page_height * 0.85, y0 + page_height * 0.72)
    return (max(0.0, x0), y0, min(page_width, x1), y1)


def _is_near_focus_border(
    item: PDFTextItem,
    page_width: float,
    page_height: float,
    focus_bbox: tuple[float, float, float, float] | None,
    border_ratio: float,
) -> bool:
    if focus_bbox is None:
        border_x = page_width * border_ratio
        border_y = page_height * border_ratio
        return (
            item.x0 <= border_x
            or item.x1 >= page_width - border_x
            or item.y0 <= border_y
            or item.y1 >= page_height - border_y
        )

    x0, y0, x1, y1 = focus_bbox
    margin_x = max((x1 - x0) * 0.08, page_width * 0.015, 22.0)
    margin_y = max((y1 - y0) * 0.08, page_height * 0.015, 22.0)
    center_x, center_y = item.center
    inside = x0 - margin_x <= center_x <= x1 + margin_x and y0 - margin_y <= center_y <= y1 + margin_y
    if not inside:
        return False
    return (
        abs(center_x - x0) <= margin_x
        or abs(center_x - x1) <= margin_x
        or abs(center_y - y0) <= margin_y
        or abs(center_y - y1) <= margin_y
    )


def _make_candidate(
    raw_text: str,
    value: float,
    axis: str,
    kind: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> CoordinateCandidate:
    return CoordinateCandidate(
        raw_text=raw_text,
        value=value,
        axis=axis,
        kind=kind,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        page_x=(x0 + x1) / 2.0,
        page_y=(y0 + y1) / 2.0,
    )


def _extract_combined_projected_candidates(items: list[PDFTextItem]) -> list[CoordinateCandidate]:
    candidates: list[CoordinateCandidate] = []
    digit_items = []
    for item in items:
        if any(symbol in item.text for symbol in ("°", "º", "'", '"')):
            continue
        cleaned = re.sub(r"[^0-9]", "", item.text.upper().replace("O", "0"))
        if cleaned:
            digit_items.append((item, cleaned))

    for idx, (item_a, digits_a) in enumerate(digit_items):
        for item_b, digits_b in digit_items[idx + 1 :]:
            ay = (item_a.y0 + item_a.y1) / 2.0
            by = (item_b.y0 + item_b.y1) / 2.0
            ax = (item_a.x0 + item_a.x1) / 2.0
            bx = (item_b.x0 + item_b.x1) / 2.0

            left_item, left_digits = (item_a, digits_a) if item_a.x0 <= item_b.x0 else (item_b, digits_b)
            right_item, right_digits = (item_b, digits_b) if left_item is item_a else (item_a, digits_a)
            same_row = abs(ay - by) <= 18 and -8 <= right_item.x0 - left_item.x1 <= 36
            if same_row:
                if right_digits != "000":
                    continue
                combined = left_digits + right_digits
                if len(combined) == 6:
                    value = float(combined)
                    classified = _classify_projected(value)
                    if classified is not None:
                        axis, kind = classified
                        candidates.append(
                            _make_candidate(
                                f"{left_item.text}{right_item.text}",
                                value,
                                axis,
                                kind,
                                min(left_item.x0, right_item.x0),
                                min(left_item.y0, right_item.y0),
                                max(left_item.x1, right_item.x1),
                                max(left_item.y1, right_item.y1),
                            )
                        )

            top_item, top_digits = (item_a, digits_a) if item_a.y0 <= item_b.y0 else (item_b, digits_b)
            bottom_item, bottom_digits = (item_b, digits_b) if top_item is item_a else (item_a, digits_a)
            same_column = abs(ax - bx) <= 24 and -10 <= bottom_item.y0 - top_item.y1 <= 34
            if same_column:
                lengths = {len(top_digits), len(bottom_digits)}
                if lengths != {3, 4}:
                    continue
                prefix_digits = top_digits if len(top_digits) == 3 else bottom_digits
                suffix_digits = top_digits if len(top_digits) == 4 else bottom_digits
                combined = prefix_digits + suffix_digits
                if len(combined) == 7:
                    value = float(combined)
                    classified = _classify_projected(value)
                    if classified is not None:
                        axis, kind = classified
                        candidates.append(
                            _make_candidate(
                                f"{top_item.text}{bottom_item.text}",
                                value,
                                axis,
                                kind,
                                min(top_item.x0, bottom_item.x0),
                                min(top_item.y0, bottom_item.y0),
                                max(top_item.x1, bottom_item.x1),
                                max(top_item.y1, bottom_item.y1),
                            )
                        )

    unique: dict[tuple[str, int, int, int], CoordinateCandidate] = {}
    for candidate in candidates:
        key = (candidate.axis, int(round(candidate.value)), int(round(candidate.page_x)), int(round(candidate.page_y)))
        unique[key] = candidate
    return list(unique.values())


def extract_coordinate_candidates(
    items: Iterable[PDFTextItem],
    page_width: float,
    page_height: float,
    border_ratio: float = 0.16,
    focus_bbox: tuple[float, float, float, float] | None = None,
) -> list[CoordinateCandidate]:
    filtered_items = [
        item for item in items if _is_near_focus_border(item, page_width, page_height, focus_bbox, border_ratio)
    ]
    candidates: list[CoordinateCandidate] = []

    for item in filtered_items:
        text = item.text.upper().replace("O", "0")

        if not any(symbol in item.text for symbol in ("°", "º", "'", '"')):
            for match in PROJECTED_RE.finditer(text):
                for value, raw_text in _projected_value_variants(match.group(1), item, page_width, page_height):
                    classified = _classify_projected(value)
                    if classified is None:
                        continue
                    axis, kind = classified
                    candidates.append(_make_candidate(raw_text, value, axis, kind, item.x0, item.y0, item.x1, item.y1))

        original_text = item.text.upper()
        for match in DMS_RE.finditer(original_text):
            value = _dms_to_decimal(match.group("deg"), match.group("min"), match.group("sec"), match.group("hem"))
            classified = _classify_geographic(value, match.group("hem"))
            if classified is None:
                continue
            axis, kind = classified
            candidates.append(_make_candidate(match.group(0), value, axis, kind, item.x0, item.y0, item.x1, item.y1))

        for match in COMPACT_DMS_RE.finditer(original_text):
            value = _compact_dms_to_decimal(match.group("degmin"), match.group("sec"), match.group("hem"))
            if value is None:
                continue
            classified = _classify_geographic(value, match.group("hem"))
            if classified is None:
                continue
            axis, kind = classified
            candidates.append(_make_candidate(match.group(0), value, axis, kind, item.x0, item.y0, item.x1, item.y1))

        for match in DECIMAL_GEO_RE.finditer(original_text):
            value = _normalize_number(match.group("value"))
            classified = _classify_geographic(value, match.group("hem"))
            if classified is None:
                continue
            axis, kind = classified
            if match.group("hem").upper() in {"S", "W", "O"}:
                value = -abs(value)
            candidates.append(_make_candidate(match.group(0), value, axis, kind, item.x0, item.y0, item.x1, item.y1))

    candidates.extend(_extract_combined_projected_candidates(filtered_items))
    return candidates


def _corner_templates(width_px: int, height_px: int) -> dict[str, tuple[float, float]]:
    return {
        "top_left": (0.0, 0.0),
        "top_right": (float(width_px), 0.0),
        "bottom_left": (0.0, float(height_px)),
        "bottom_right": (float(width_px), float(height_px)),
    }


def _bbox_corner_templates(
    bbox: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
) -> dict[str, tuple[float, float]]:
    x0, y0, x1, y1 = bbox
    return {
        "top_left": (x0 * scale_x, y0 * scale_y),
        "top_right": (x1 * scale_x, y0 * scale_y),
        "bottom_left": (x0 * scale_x, y1 * scale_y),
        "bottom_right": (x1 * scale_x, y1 * scale_y),
    }


def _best_candidate(
    candidates: list[CoordinateCandidate],
    target_x: float,
    target_y: float,
    axis: str,
    scale_x: float,
    scale_y: float,
) -> CoordinateCandidate | None:
    relevant = [candidate for candidate in candidates if candidate.axis == axis]
    if not relevant:
        return None

    def score(candidate: CoordinateCandidate) -> float:
        px = candidate.page_x * scale_x
        py = candidate.page_y * scale_y
        return math.dist((px, py), (target_x, target_y))

    return min(relevant, key=score)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _split_by_y_clusters(
    candidates: list[CoordinateCandidate],
    gap_threshold: float = 500.0,
) -> list[list[CoordinateCandidate]]:
    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda candidate: candidate.page_y)
    clusters: list[list[CoordinateCandidate]] = [[ordered[0]]]
    for candidate in ordered[1:]:
        if candidate.page_y - clusters[-1][-1].page_y > gap_threshold:
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)
    return clusters


def _near_extreme(
    candidates: list[CoordinateCandidate],
    key: str,
    mode: str,
    tolerance: float = 40.0,
) -> list[CoordinateCandidate]:
    values = [getattr(candidate, key) for candidate in candidates]
    if not values:
        return []
    target = min(values) if mode == "min" else max(values)
    selected = [candidate for candidate in candidates if abs(getattr(candidate, key) - target) <= tolerance]
    return selected or candidates


def _filter_border_role(
    candidates: list[CoordinateCandidate],
    focus_bbox: tuple[float, float, float, float] | None,
    role: str,
) -> list[CoordinateCandidate]:
    if focus_bbox is None:
        return candidates

    x0, y0, x1, y1 = focus_bbox
    tolerance_x = max((x1 - x0) * 0.04, 28.0)
    tolerance_y = max((y1 - y0) * 0.04, 28.0)
    filtered: list[CoordinateCandidate] = []
    for candidate in candidates:
        distance_horizontal = min(abs(candidate.page_y - y0), abs(candidate.page_y - y1))
        distance_vertical = min(abs(candidate.page_x - x0), abs(candidate.page_x - x1))
        width = candidate.x1 - candidate.x0
        height = candidate.y1 - candidate.y0
        if role == "horizontal":
            if distance_horizontal <= max(tolerance_y, distance_vertical * 1.15) and width >= height * 0.8:
                filtered.append(candidate)
        else:
            if distance_vertical <= max(tolerance_x, distance_horizontal * 1.15) and height >= width * 0.8:
                filtered.append(candidate)
    return filtered or candidates


def _filter_peru_geographic_candidates(candidates: list[CoordinateCandidate]) -> list[CoordinateCandidate]:
    if not candidates:
        return candidates

    filtered = []
    for candidate in candidates:
        if candidate.axis == "LON" and -85.0 <= candidate.value <= -65.0:
            filtered.append(candidate)
        elif candidate.axis == "LAT" and -20.0 <= candidate.value <= 5.0:
            filtered.append(candidate)

    return filtered or candidates


def _geographic_corners_from_label_centers(
    lon_candidates: list[CoordinateCandidate],
    lat_candidates: list[CoordinateCandidate],
    scale_x: float,
    scale_y: float,
) -> tuple[list[CornerDetection], list[str]] | None:
    if len(lon_candidates) < 2 or len(lat_candidates) < 2:
        return None

    left_lons = _near_extreme(lon_candidates, "page_x", "min")
    right_lons = _near_extreme(lon_candidates, "page_x", "max")
    top_lats = _near_extreme(lat_candidates, "page_y", "min")
    bottom_lats = _near_extreme(lat_candidates, "page_y", "max")
    if not left_lons or not right_lons or not top_lats or not bottom_lats:
        return None

    west = _median([candidate.value for candidate in left_lons])
    east = _median([candidate.value for candidate in right_lons])
    north = _median([candidate.value for candidate in top_lats])
    south = _median([candidate.value for candidate in bottom_lats])
    if not (west < east and south < north):
        return None

    map_x0_pt = _median([candidate.page_x for candidate in left_lons])
    map_x1_pt = _median([candidate.page_x for candidate in right_lons])
    map_y0_pt = _median([candidate.page_y for candidate in top_lats])
    map_y1_pt = _median([candidate.page_y for candidate in bottom_lats])
    if not (map_x0_pt < map_x1_pt and map_y0_pt < map_y1_pt):
        return None

    corners = [
        CornerDetection(name="top_left", pixel_x=map_x0_pt * scale_x, pixel_y=map_y0_pt * scale_y, longitude=west, latitude=north, source="grid_intersection"),
        CornerDetection(name="top_right", pixel_x=map_x1_pt * scale_x, pixel_y=map_y0_pt * scale_y, longitude=east, latitude=north, source="grid_intersection"),
        CornerDetection(name="bottom_left", pixel_x=map_x0_pt * scale_x, pixel_y=map_y1_pt * scale_y, longitude=west, latitude=south, source="grid_intersection"),
        CornerDetection(name="bottom_right", pixel_x=map_x1_pt * scale_x, pixel_y=map_y1_pt * scale_y, longitude=east, latitude=south, source="grid_intersection"),
    ]
    notes = [
        "Coordenadas geograficas calculadas cruzando el centro horizontal de las longitudes con el centro vertical de las latitudes rotadas.",
        f"Longitudes: {west:.6f} a {east:.6f}.",
        f"Latitudes: {south:.6f} a {north:.6f}.",
    ]
    return corners, notes


def _match_candidate_to_grid_line(
    candidate: CoordinateCandidate,
    lines: list[GridLine],
    orientation: str,
) -> GridLine | None:
    relevant = [line for line in lines if line.orientation == orientation]
    if not relevant:
        return None

    if orientation == "vertical":
        return min(relevant, key=lambda line: abs(line.coord - candidate.page_x))
    return min(relevant, key=lambda line: abs(line.coord - candidate.page_y))


def _longest_true_run(mask_1d: np.ndarray) -> tuple[int, int, int]:
    best_start = 0
    best_end = -1
    best_length = 0
    start = None
    for index, value in enumerate(mask_1d):
        if value and start is None:
            start = index
        elif not value and start is not None:
            length = index - start
            if length > best_length:
                best_start, best_end, best_length = start, index - 1, length
            start = None
    if start is not None:
        length = len(mask_1d) - start
        if length > best_length:
            best_start, best_end, best_length = start, len(mask_1d) - 1, length
    return best_start, best_end, best_length


def _search_raster_line(
    mask: np.ndarray,
    orientation: str,
    center: float,
    focus_bbox: tuple[float, float, float, float],
    search_radius: int,
) -> GridLine | None:
    fx0, fy0, fx1, fy1 = [int(round(value)) for value in focus_bbox]
    best_line: GridLine | None = None
    best_score = -1.0

    if orientation == "vertical":
        start = max(fx0, int(round(center)) - search_radius)
        end = min(fx1 - 1, int(round(center)) + search_radius)
        for x in range(start, end + 1):
            column = mask[fy0:fy1, x]
            run_start, run_end, run_length = _longest_true_run(column)
            if run_length < int((fy1 - fy0) * 0.22):
                continue
            score = run_length - abs(x - center) * 1.5
            if score > best_score:
                best_score = score
                best_line = GridLine(
                    orientation="vertical",
                    coord=float(x),
                    span_start=float(fy0 + run_start),
                    span_end=float(fy0 + run_end),
                    color=(0.0, 0.439, 1.0),
                    width=1.0,
                )
    else:
        start = max(fy0, int(round(center)) - search_radius)
        end = min(fy1 - 1, int(round(center)) + search_radius)
        for y in range(start, end + 1):
            row = mask[y, fx0:fx1]
            run_start, run_end, run_length = _longest_true_run(row)
            if run_length < int((fx1 - fx0) * 0.22):
                continue
            score = run_length - abs(y - center) * 1.5
            if score > best_score:
                best_score = score
                best_line = GridLine(
                    orientation="horizontal",
                    coord=float(y),
                    span_start=float(fx0 + run_start),
                    span_end=float(fx0 + run_end),
                    color=(0.0, 0.439, 1.0),
                    width=1.0,
                )
    return best_line


def _project_raster_border_line(
    dark_mask: np.ndarray,
    orientation: str,
    center: float,
    focus_bbox: tuple[float, float, float, float],
    search_radius: int,
) -> GridLine:
    fx0, fy0, fx1, fy1 = [int(round(value)) for value in focus_bbox]
    border_band = max(22, int(round(min(fx1 - fx0, fy1 - fy0) * 0.018)))

    if orientation == "vertical":
        top_band = dark_mask[fy0 : min(fy1, fy0 + border_band), :]
        line = _search_raster_line(top_band, "vertical", center, (fx0, 0, fx1, top_band.shape[0]), search_radius)
        coord = line.coord if line is not None else float(min(max(center, fx0), fx1))
        return GridLine("vertical", float(coord), float(fy0), float(fy1), (0.0, 0.0, 0.0), 1.0)

    left_band = dark_mask[:, fx0 : min(fx1, fx0 + border_band)]
    line = _search_raster_line(left_band, "horizontal", center, (0, fy0, left_band.shape[1], fy1), search_radius)
    coord = line.coord if line is not None else float(min(max(center, fy0), fy1))
    return GridLine("horizontal", float(coord), float(fx0), float(fx1), (0.0, 0.0, 0.0), 1.0)


def _infer_raster_grid_lines(
    raster_image: Image.Image,
    candidates: list[CoordinateCandidate],
    focus_bbox: tuple[float, float, float, float] | None,
) -> list[GridLine]:
    if focus_bbox is None:
        return []

    rgb = np.asarray(raster_image.convert("RGB"))
    blue_mask = (
        (rgb[:, :, 2] >= 145)
        & (rgb[:, :, 1] >= 110)
        & (rgb[:, :, 0] <= 120)
        & ((rgb[:, :, 2].astype(np.int16) - rgb[:, :, 0].astype(np.int16)) >= 35)
    )
    gray = rgb.mean(axis=2)
    dark_mask = gray <= 90
    search_radius = max(24, int(round(min(focus_bbox[2] - focus_bbox[0], focus_bbox[3] - focus_bbox[1]) * 0.03)))

    lines: list[GridLine] = []
    for candidate in candidates:
        line: GridLine | None = None
        if candidate.axis == "E":
            line = _search_raster_line(blue_mask, "vertical", candidate.page_x, focus_bbox, search_radius)
        elif candidate.axis == "N":
            line = _search_raster_line(blue_mask, "horizontal", candidate.page_y, focus_bbox, search_radius)
        elif candidate.axis == "LON":
            line = _project_raster_border_line(dark_mask, "vertical", candidate.page_x, focus_bbox, search_radius)
        elif candidate.axis == "LAT":
            line = _project_raster_border_line(dark_mask, "horizontal", candidate.page_y, focus_bbox, search_radius)

        if line is not None:
            merged = False
            for existing in lines:
                if existing.orientation == line.orientation and abs(existing.coord - line.coord) <= 3.0:
                    existing.coord = (existing.coord + line.coord) / 2.0
                    existing.span_start = min(existing.span_start, line.span_start)
                    existing.span_end = max(existing.span_end, line.span_end)
                    merged = True
                    break
            if not merged:
                lines.append(line)

    return lines


def _choose_extreme_with_grid(
    candidates: list[CoordinateCandidate],
    lines: list[GridLine],
    orientation: str,
    extreme: str,
) -> tuple[CoordinateCandidate, GridLine] | None:
    matches: list[tuple[CoordinateCandidate, GridLine]] = []
    for candidate in candidates:
        line = _match_candidate_to_grid_line(candidate, lines, orientation)
        if line is not None:
            matches.append((candidate, line))
    if not matches:
        return None

    index = 1 if extreme == "max" else 0
    return sorted(matches, key=lambda pair: pair[1].coord)[-1 if index == 1 else 0]


def _geographic_fallback_from_grid(
    candidates: list[CoordinateCandidate],
    grid_lines: list[GridLine],
    scale_x: float,
    scale_y: float,
) -> tuple[list[CornerDetection], list[str]] | None:
    del grid_lines
    lon_candidates = _filter_peru_geographic_candidates([candidate for candidate in candidates if candidate.axis == "LON"])
    lat_candidates = _filter_peru_geographic_candidates([candidate for candidate in candidates if candidate.axis == "LAT"])
    return _geographic_corners_from_label_centers(lon_candidates, lat_candidates, scale_x, scale_y)


def _detect_geographic_corners(
    candidates: list[CoordinateCandidate],
    focus_bbox: tuple[float, float, float, float] | None,
    grid_lines: list[GridLine] | None,
    scale_x: float,
    scale_y: float,
) -> tuple[list[CornerDetection], list[str]] | None:
    geographic_candidates = [candidate for candidate in candidates if candidate.kind == "geographic"]
    if len(geographic_candidates) < 4:
        return None

    chosen_cluster: list[CoordinateCandidate] | None = None
    for cluster in _split_by_y_clusters(geographic_candidates):
        lon_values = sorted({round(candidate.value, 6) for candidate in cluster if candidate.axis == "LON"})
        lat_values = sorted({round(candidate.value, 6) for candidate in cluster if candidate.axis == "LAT"})
        if len(lon_values) >= 2 and len(lat_values) >= 2:
            chosen_cluster = cluster
            break

    if chosen_cluster is None:
        filtered_all = _filter_peru_geographic_candidates(geographic_candidates)
        lon_values = sorted({round(candidate.value, 6) for candidate in filtered_all if candidate.axis == "LON"})
        lat_values = sorted({round(candidate.value, 6) for candidate in filtered_all if candidate.axis == "LAT"})
        if len(lon_values) < 2 or len(lat_values) < 2:
            return None
        chosen_cluster = filtered_all

    lon_candidates = _filter_peru_geographic_candidates(_filter_border_role(
        [candidate for candidate in chosen_cluster if candidate.axis == "LON"],
        focus_bbox,
        "horizontal",
    ))
    lat_candidates = _filter_peru_geographic_candidates(_filter_border_role(
        [candidate for candidate in chosen_cluster if candidate.axis == "LAT"],
        focus_bbox,
        "vertical",
    ))
    result = _geographic_corners_from_label_centers(lon_candidates, lat_candidates, scale_x, scale_y)
    if result is None:
        return None
    corners, notes = result
    notes.insert(1, f"Cluster geografico seleccionado: {len(chosen_cluster)} etiquetas.")
    return corners, notes


def _detect_projected_corners(
    candidates: list[CoordinateCandidate],
    focus_bbox: tuple[float, float, float, float] | None,
    grid_lines: list[GridLine] | None,
    scale_x: float,
    scale_y: float,
) -> tuple[list[CornerDetection], list[str]] | None:
    east_candidates = _filter_border_role(
        [candidate for candidate in candidates if candidate.kind == "projected" and candidate.axis == "E"],
        focus_bbox,
        "horizontal",
    )
    north_candidates = _filter_border_role(
        [candidate for candidate in candidates if candidate.kind == "projected" and candidate.axis == "N"],
        focus_bbox,
        "vertical",
    )
    if len(east_candidates) < 2 or len(north_candidates) < 2:
        return None

    left_easts = _near_extreme(east_candidates, "page_x", "min")
    right_easts = _near_extreme(east_candidates, "page_x", "max")
    top_easts = _near_extreme(east_candidates, "page_y", "min")
    bottom_easts = _near_extreme(east_candidates, "page_y", "max")
    left_norths = _near_extreme(north_candidates, "page_x", "min")
    right_norths = _near_extreme(north_candidates, "page_x", "max")
    top_norths = _near_extreme(north_candidates, "page_y", "min")
    bottom_norths = _near_extreme(north_candidates, "page_y", "max")
    if not left_easts or not right_easts or not top_norths or not bottom_norths:
        return None

    west = _median([candidate.value for candidate in left_easts])
    east = _median([candidate.value for candidate in right_easts])
    north = _median([candidate.value for candidate in top_norths])
    south = _median([candidate.value for candidate in bottom_norths])

    if focus_bbox is not None:
        map_x0_pt, map_y0_pt, map_x1_pt, map_y1_pt = focus_bbox
    else:
        map_x0_pt = _mean([candidate.x1 for candidate in left_norths])
        map_x1_pt = _mean([candidate.x0 for candidate in right_norths])
        map_y0_pt = _mean([candidate.y1 for candidate in top_easts])
        map_y1_pt = _mean([candidate.y0 for candidate in bottom_easts])

    if grid_lines:
        west_match = _choose_extreme_with_grid(left_easts, grid_lines, "vertical", "min")
        east_match = _choose_extreme_with_grid(right_easts, grid_lines, "vertical", "max")
        north_match = _choose_extreme_with_grid(top_norths, grid_lines, "horizontal", "min")
        south_match = _choose_extreme_with_grid(bottom_norths, grid_lines, "horizontal", "max")
        if west_match and east_match and north_match and south_match:
            west_candidate, west_line = west_match
            east_candidate, east_line = east_match
            north_candidate, north_line = north_match
            south_candidate, south_line = south_match
            west = west_candidate.value
            east = east_candidate.value
            north = north_candidate.value
            south = south_candidate.value
            map_x0_pt = west_line.coord
            map_x1_pt = east_line.coord
            map_y0_pt = north_line.coord
            map_y1_pt = south_line.coord

    corners = [
        CornerDetection(name="top_left", pixel_x=map_x0_pt * scale_x, pixel_y=map_y0_pt * scale_y, east=west, north=north, source="grid_intersection" if grid_lines else "auto"),
        CornerDetection(name="top_right", pixel_x=map_x1_pt * scale_x, pixel_y=map_y0_pt * scale_y, east=east, north=north, source="grid_intersection" if grid_lines else "auto"),
        CornerDetection(name="bottom_left", pixel_x=map_x0_pt * scale_x, pixel_y=map_y1_pt * scale_y, east=west, north=south, source="grid_intersection" if grid_lines else "auto"),
        CornerDetection(name="bottom_right", pixel_x=map_x1_pt * scale_x, pixel_y=map_y1_pt * scale_y, east=east, north=south, source="grid_intersection" if grid_lines else "auto"),
    ]
    notes = [
        "Coordenadas proyectadas detectadas sobre la grilla principal." if grid_lines else "Coordenadas proyectadas detectadas sobre el marco principal.",
        f"Borde E estimado: {west:.0f}-{east:.0f}.",
        f"Borde N estimado: {south:.0f}-{north:.0f}.",
    ]
    return corners, notes


def _select_mode(candidates: list[CoordinateCandidate]) -> tuple[str, dict[str, int]]:
    counts = {
        "E": len([candidate for candidate in candidates if candidate.axis == "E"]),
        "N": len([candidate for candidate in candidates if candidate.axis == "N"]),
        "LON": len([candidate for candidate in candidates if candidate.axis == "LON"]),
        "LAT": len([candidate for candidate in candidates if candidate.axis == "LAT"]),
    }
    projected_ready = counts["E"] >= 2 and counts["N"] >= 1
    geographic_ready = counts["LON"] >= 2 and counts["LAT"] >= 1

    if projected_ready and not geographic_ready:
        return "projected", counts
    if geographic_ready and not projected_ready:
        return "geographic", counts

    projected_score = counts["E"] * 2 + counts["N"] * 3
    geographic_score = counts["LON"] * 2 + counts["LAT"] * 3
    return ("projected", counts) if projected_score >= geographic_score else ("geographic", counts)


def _mode_candidates(axis_counts: dict[str, int]) -> list[str]:
    candidates: list[str] = []
    if axis_counts["E"] >= 2 and axis_counts["N"] >= 1:
        candidates.append("projected")
    if axis_counts["LON"] >= 2 and axis_counts["LAT"] >= 1:
        candidates.append("geographic")
    return candidates or ["projected", "geographic"]


def detect_corner_gcps(
    items: list[PDFTextItem],
    page_width_pt: float,
    page_height_pt: float,
    image_width_px: int,
    image_height_px: int,
    focus_bbox: tuple[float, float, float, float] | None = None,
    grid_lines: list[GridLine] | None = None,
    raster_image: Image.Image | None = None,
    preferred_mode: str | None = None,
) -> DetectionResult:
    effective_bbox = focus_bbox or infer_main_map_bbox_from_title(items, page_width_pt, page_height_pt)
    candidates = extract_coordinate_candidates(
        items,
        page_width_pt,
        page_height_pt,
        focus_bbox=effective_bbox,
    )
    if raster_image is not None and not grid_lines:
        grid_lines = _infer_raster_grid_lines(raster_image, candidates, effective_bbox)
    notes: list[str] = []

    if effective_bbox is not None:
        x0, y0, x1, y1 = effective_bbox
        notes.append(f"Marco objetivo usado: x={x0:.1f}-{x1:.1f} pt, y={y0:.1f}-{y1:.1f} pt.")
    if grid_lines:
        notes.append(f"Lineas de referencia detectadas: {len(grid_lines)}.")

    projected_count = len([candidate for candidate in candidates if candidate.kind == "projected"])
    geographic_count = len([candidate for candidate in candidates if candidate.kind == "geographic"])
    mode, axis_counts = _select_mode(candidates)
    candidate_modes = _mode_candidates(axis_counts)
    if preferred_mode in candidate_modes:
        mode = preferred_mode
    scale_x = image_width_px / page_width_pt
    scale_y = image_height_px / page_height_pt
    notes.append(
        "Candidatos por eje: "
        f"E={axis_counts['E']}, N={axis_counts['N']}, Lon={axis_counts['LON']}, Lat={axis_counts['LAT']}."
    )

    if mode == "projected":
        projected_result = _detect_projected_corners(candidates, effective_bbox, grid_lines, scale_x, scale_y)
        if projected_result is not None:
            corners, projected_notes = projected_result
            notes.extend(projected_notes)
            notes.append(f"Modo detectado: {mode}.")
            notes.append(
                f"Candidatos detectados: {len(candidates)} "
                f"(proyectados={projected_count}, geograficos={geographic_count})."
            )
            return DetectionResult(
                corners=corners,
                candidates=candidates,
                mode=mode,
                notes=notes,
                focus_bbox=effective_bbox,
                mode_candidates=candidate_modes,
                axis_counts=axis_counts,
            )

    if mode == "geographic":
        geographic_result = _detect_geographic_corners(candidates, effective_bbox, grid_lines, scale_x, scale_y)
        if geographic_result is not None:
            corners, geographic_notes = geographic_result
            notes.extend(geographic_notes)
            notes.append(f"Modo detectado: {mode}.")
            notes.append(
                f"Candidatos detectados: {len(candidates)} "
                f"(proyectados={projected_count}, geograficos={geographic_count})."
            )
            return DetectionResult(
                corners=corners,
                candidates=candidates,
                mode=mode,
                notes=notes,
                focus_bbox=effective_bbox,
                mode_candidates=candidate_modes,
                axis_counts=axis_counts,
            )
        if grid_lines:
            geographic_fallback = _geographic_fallback_from_grid(candidates, grid_lines, scale_x, scale_y)
            if geographic_fallback is not None:
                corners, geographic_notes = geographic_fallback
                notes.extend(geographic_notes)
                notes.append(f"Modo detectado: {mode}.")
                notes.append(
                    f"Candidatos detectados: {len(candidates)} "
                    f"(proyectados={projected_count}, geograficos={geographic_count})."
                )
                return DetectionResult(
                    corners=corners,
                    candidates=candidates,
                    mode=mode,
                    notes=notes,
                    focus_bbox=effective_bbox,
                    mode_candidates=candidate_modes,
                    axis_counts=axis_counts,
                )

    target_templates = (
        _bbox_corner_templates(effective_bbox, scale_x, scale_y)
        if effective_bbox is not None
        else _corner_templates(image_width_px, image_height_px)
    )
    corners: list[CornerDetection] = []
    for name, (target_x, target_y) in target_templates.items():
        detection = CornerDetection(name=name, pixel_x=target_x, pixel_y=target_y)
        if mode == "projected":
            east = _best_candidate(candidates, target_x, target_y, "E", scale_x, scale_y)
            north = _best_candidate(candidates, target_x, target_y, "N", scale_x, scale_y)
            detection.east = east.value if east else None
            detection.north = north.value if north else None
            if east is None or north is None:
                detection.source = "partial"
                detection.notes.append("Coordenada proyectada incompleta")
        else:
            lon = _best_candidate(candidates, target_x, target_y, "LON", scale_x, scale_y)
            lat = _best_candidate(candidates, target_x, target_y, "LAT", scale_x, scale_y)
            detection.longitude = lon.value if lon else None
            detection.latitude = lat.value if lat else None
            if lon is None or lat is None:
                detection.source = "partial"
                detection.notes.append("Coordenada geografica incompleta")
        corners.append(detection)

    if not candidates:
        notes.append("No se encontraron coordenadas candidatas en los bordes del documento.")
    else:
        notes.append(f"Modo detectado: {mode}.")
        notes.append(
            f"Candidatos detectados: {len(candidates)} "
            f"(proyectados={projected_count}, geograficos={geographic_count})."
        )

    return DetectionResult(
        corners=corners,
        candidates=candidates,
        mode=mode,
        notes=notes,
        focus_bbox=effective_bbox,
        mode_candidates=candidate_modes,
        axis_counts=axis_counts,
    )
