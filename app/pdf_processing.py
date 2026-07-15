# Copyright (c) 2026 Jordan Zavaleta
# This file is part of GeoRefMaps.
# GeoRefMaps is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

from pathlib import Path
import unicodedata

import fitz
import numpy as np
from PIL import Image

from app.models import GridLine, PDFTextItem


class PDFPageData:
    def __init__(self, input_path: Path, page_index: int = 0, dpi: int = 220) -> None:
        self.input_path = Path(input_path)
        self.page_index = page_index
        self.dpi = dpi
        self.kind = self._detect_kind(self.input_path)
        self.doc = None
        self.page = None
        self.page_rect = None
        self._image = None
        self.scale = 1.0

        if self.kind == "pdf":
            self.doc = fitz.open(self.input_path)
            self.page = self.doc.load_page(page_index)
            self.page_rect = self.page.rect
            self.scale = dpi / 72.0
        else:
            self._image = Image.open(self.input_path).convert("RGB")

    @staticmethod
    def _detect_kind(input_path: Path) -> str:
        suffix = input_path.suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            return "image"
        raise ValueError(f"Formato no soportado: {suffix}")

    @property
    def page_size_points(self) -> tuple[float, float]:
        if self.kind == "pdf":
            return (self.page_rect.width, self.page_rect.height)
        return self.image_size_pixels

    @property
    def image_size_pixels(self) -> tuple[int, int]:
        if self.kind == "pdf":
            return (
                int(round(self.page_rect.width * self.scale)),
                int(round(self.page_rect.height * self.scale)),
            )
        return self._image.size

    def render_image(self) -> Image.Image:
        if self.kind == "image":
            return self._image.copy()

        matrix = fitz.Matrix(self.scale, self.scale)
        pix = self.page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def extract_text_items(self) -> list[PDFTextItem]:
        if self.kind == "image":
            return []

        text_dict = self.page.get_text("dict")
        items: list[PDFTextItem] = []

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if not text:
                        continue
                    x0, y0, x1, y1 = span["bbox"]
                    items.append(PDFTextItem(text=text, x0=x0, y0=y0, x1=x1, y1=y1))

        return items

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(char for char in normalized if not unicodedata.combining(char)).upper()

    @staticmethod
    def _longest_dense_segment(
        density: np.ndarray,
        thresholds: tuple[float, ...],
        min_length: int,
    ) -> tuple[int, int] | None:
        for threshold in thresholds:
            indexes = np.where(density >= threshold)[0]
            if len(indexes) == 0:
                continue

            best_segment: tuple[int, int] | None = None
            start = int(indexes[0])
            previous = int(indexes[0])
            for index in indexes[1:]:
                current = int(index)
                if current != previous + 1:
                    if previous - start + 1 >= min_length:
                        if best_segment is None or (previous - start) > (best_segment[1] - best_segment[0]):
                            best_segment = (start, previous)
                    start = current
                previous = current

            if previous - start + 1 >= min_length:
                if best_segment is None or (previous - start) > (best_segment[1] - best_segment[0]):
                    best_segment = (start, previous)

            if best_segment is not None:
                return best_segment

        return None

    @staticmethod
    def _snap_to_dark_line(
        profile: np.ndarray,
        target: int,
        width: int,
        search_radius: int,
        minimum_density: float,
    ) -> int:
        start = max(0, target - search_radius)
        end = min(width - 1, target + search_radius)
        best_index = target
        best_density = minimum_density
        for index in range(start, end + 1):
            density = float(profile[index])
            if density < best_density:
                continue
            if density > best_density:
                best_density = density
                best_index = index
                continue
            if abs(index - target) < abs(best_index - target):
                best_index = index
        return best_index

    def _detect_image_main_map_bbox(self) -> tuple[float, float, float, float] | None:
        if self.kind != "image":
            return None

        array = np.asarray(self._image.convert("RGB"))
        height, width = array.shape[:2]
        saturation = array.max(axis=2) - array.min(axis=2)
        colorful_mask = saturation > 28

        col_segment = self._longest_dense_segment(
            colorful_mask.mean(axis=0),
            thresholds=(0.20, 0.18, 0.15, 0.12),
            min_length=max(int(width * 0.28), 1200),
        )
        row_segment = self._longest_dense_segment(
            colorful_mask.mean(axis=1),
            thresholds=(0.20, 0.18, 0.15, 0.12),
            min_length=max(int(height * 0.28), 1200),
        )
        if col_segment is None or row_segment is None:
            return None

        x0, x1 = col_segment
        y0, y1 = row_segment

        gray = array.mean(axis=2)
        dark_mask = gray < 190
        col_profile = dark_mask[max(0, y0 - 80) : min(height, y1 + 81), :].mean(axis=0)
        row_profile = dark_mask[:, max(0, x0 - 80) : min(width, x1 + 81)].mean(axis=1)
        search_radius = max(20, min(width, height) // 140)

        snapped_x0 = self._snap_to_dark_line(col_profile, x0, width, search_radius=search_radius, minimum_density=0.12)
        snapped_x1 = self._snap_to_dark_line(col_profile, x1, width, search_radius=search_radius, minimum_density=0.12)
        snapped_y0 = self._snap_to_dark_line(row_profile, y0, height, search_radius=search_radius, minimum_density=0.12)
        snapped_y1 = self._snap_to_dark_line(row_profile, y1, height, search_radius=search_radius, minimum_density=0.12)

        margin_x = max(12, int(round(width * 0.004)))
        margin_y = max(12, int(round(height * 0.004)))
        x0 = max(0, snapped_x0 - margin_x)
        y0 = max(0, snapped_y0 - margin_y)
        x1 = min(width, snapped_x1 + margin_x)
        y1 = min(height, snapped_y1 + margin_y)
        if x1 <= x0 or y1 <= y0:
            return None

        return (float(x0), float(y0), float(x1), float(y1))

    def detect_main_map_bbox(self, items: list[PDFTextItem] | None = None) -> tuple[float, float, float, float] | None:
        if self.kind == "image":
            return self._detect_image_main_map_bbox()

        if self.kind != "pdf":
            return None

        items = items or self.extract_text_items()
        page_width, page_height = self.page_size_points

        title_items = [
            item
            for item in items
            if item.y0 < page_height * 0.18
            and any(token in self._normalize(item.text) for token in ("MAPA", "GEOLOGIC", "CUADRANGULO", "HOJA"))
        ]
        if not title_items:
            return None

        title_y = min(item.y0 for item in title_items)
        title_items = [item for item in title_items if abs(item.y0 - title_y) <= 24]
        title_x0 = min(item.x0 for item in title_items)
        title_y0 = min(item.y0 for item in title_items)
        title_x1 = max(item.x1 for item in title_items)
        title_y1 = max(item.y1 for item in title_items)

        page_area = page_width * page_height
        rectangles: list[tuple[float, float, float, float]] = []
        for drawing in self.page.get_drawings():
            rect = drawing.get("rect")
            if rect is None:
                continue
            area = rect.width * rect.height
            if area < page_area * 0.12 or area > page_area * 0.82:
                continue
            if rect.y1 <= title_y1:
                continue
            if rect.x0 > title_x0 or rect.x1 < title_x1:
                continue
            rectangles.append((rect.x0, rect.y0, rect.x1, rect.y1))

        if not rectangles:
            return None

        def score(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
            x0, y0, x1, y1 = bbox
            width = x1 - x0
            height = y1 - y0
            area = width * height
            distance = abs(y0 - title_y1)
            return (distance, -area)

        return min(rectangles, key=score)

    def extract_grid_lines(self, focus_bbox: tuple[float, float, float, float] | None) -> list[GridLine]:
        if self.kind != "pdf" or focus_bbox is None:
            return []

        fx0, fy0, fx1, fy1 = focus_bbox
        min_vertical_span = (fy1 - fy0) * 0.55
        min_horizontal_span = (fx1 - fx0) * 0.55
        merged_lines: list[GridLine] = []

        for drawing in self.page.get_drawings():
            color = tuple(drawing.get("color") or ())
            width = float(drawing.get("width") or 0.0)
            if len(color) < 3:
                continue
            # Grid lines in INGEMMET PDFs are typically thin cyan/blue vector lines.
            if not (color[2] >= 0.8 and color[1] >= 0.25 and color[0] <= 0.1):
                continue
            if width > 0.6:
                continue

            for item in drawing.get("items", []):
                if item[0] != "l":
                    continue
                p1, p2 = item[1], item[2]
                x1, y1, x2, y2 = p1.x, p1.y, p2.x, p2.y
                if max(x1, x2) < fx0 or min(x1, x2) > fx1 or max(y1, y2) < fy0 or min(y1, y2) > fy1:
                    continue

                if abs(x1 - x2) <= 0.8 and abs(y1 - y2) >= min_vertical_span:
                    line = GridLine(
                        orientation="vertical",
                        coord=(x1 + x2) / 2.0,
                        span_start=max(min(y1, y2), fy0),
                        span_end=min(max(y1, y2), fy1),
                        color=color,
                        width=width,
                    )
                elif abs(y1 - y2) <= 0.8 and abs(x1 - x2) >= min_horizontal_span:
                    line = GridLine(
                        orientation="horizontal",
                        coord=(y1 + y2) / 2.0,
                        span_start=max(min(x1, x2), fx0),
                        span_end=min(max(x1, x2), fx1),
                        color=color,
                        width=width,
                    )
                else:
                    continue

                self._merge_grid_line(merged_lines, line)

        return [
            line
            for line in merged_lines
            if (
                line.orientation == "vertical"
                and (line.span_end - line.span_start) >= min_vertical_span
                or line.orientation == "horizontal"
                and (line.span_end - line.span_start) >= min_horizontal_span
            )
        ]

    @staticmethod
    def _merge_grid_line(lines: list[GridLine], candidate: GridLine) -> None:
        for line in lines:
            if line.orientation != candidate.orientation:
                continue
            if abs(line.coord - candidate.coord) > 2.0:
                continue
            line.coord = (line.coord + candidate.coord) / 2.0
            line.span_start = min(line.span_start, candidate.span_start)
            line.span_end = max(line.span_end, candidate.span_end)
            return
        lines.append(candidate)
