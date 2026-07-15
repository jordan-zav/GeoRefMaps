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

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PDFTextItem:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)


@dataclass
class CoordinateCandidate:
    raw_text: str
    value: float
    axis: str
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_x: float
    page_y: float


@dataclass
class GridLine:
    orientation: str
    coord: float
    span_start: float
    span_end: float
    color: tuple[float, ...] = field(default_factory=tuple)
    width: float = 0.0


@dataclass
class CornerDetection:
    name: str
    pixel_x: float
    pixel_y: float
    east: Optional[float] = None
    north: Optional[float] = None
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    source: str = "auto"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pixel_x": self.pixel_x,
            "pixel_y": self.pixel_y,
            "east": self.east,
            "north": self.north,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "source": self.source,
            "notes": self.notes,
        }
