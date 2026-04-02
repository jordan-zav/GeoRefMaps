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
