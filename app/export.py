from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from PIL import Image
from rasterio.warp import Resampling, calculate_default_transform, reproject

from app.models import CornerDetection


def build_spatial_reference(mode: str, utm_zone: str) -> dict:
    if mode == "geographic":
        return {
            "mode": "geographic",
            "crs_name": "WGS 84",
            "epsg": 4326,
        }

    zone_to_epsg = {
        "17S": 32717,
        "18S": 32718,
        "19S": 32719,
    }
    return {
        "mode": "projected",
        "crs_name": f"WGS 84 / UTM zone {utm_zone}",
        "utm_zone": utm_zone,
        "epsg": zone_to_epsg.get(utm_zone),
    }


def export_gcps(
    output_path: Path,
    corners: list[CornerDetection],
    mode: str,
    utm_zone: str,
) -> None:
    payload = {
        "mode": mode,
        "spatial_reference": build_spatial_reference(mode, utm_zone),
        "corners": [corner.to_dict() for corner in corners],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_geotiff(
    output_path: Path,
    data: np.ndarray,
    transform,
    crs: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count, height, width = data.shape
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=count,
        dtype=data.dtype,
        crs=crs,
        transform=transform,
    ) as dataset:
        for band in range(count):
            dataset.write(data[band], band + 1)


def _reproject_rgb(
    data: np.ndarray,
    src_transform,
    src_crs: str,
    dst_crs: str,
) -> tuple[np.ndarray, object]:
    height, width = data.shape[1:]
    left, bottom, right, top = rasterio.transform.array_bounds(height, width, src_transform)
    dst_transform, dst_width, dst_height = calculate_default_transform(
        src_crs,
        dst_crs,
        width,
        height,
        left,
        bottom,
        right,
        top,
    )
    dst_data = np.zeros((data.shape[0], dst_height, dst_width), dtype=data.dtype)
    for band in range(data.shape[0]):
        reproject(
            source=data[band],
            destination=dst_data[band],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
    )
    return dst_data, dst_transform


def _require_corners(corners: list[CornerDetection]) -> dict[str, CornerDetection]:
    corner_map = {corner.name: corner for corner in corners}
    required = {"top_left", "top_right", "bottom_left", "bottom_right"}
    if not required.issubset(corner_map):
        raise ValueError("Faltan esquinas para exportar el GeoTIFF.")
    return corner_map


def _resolve_source_crs(mode: str, utm_zone: str) -> str:
    reference = build_spatial_reference(mode, utm_zone)
    epsg = reference.get("epsg")
    if epsg is None:
        raise ValueError("No se pudo resolver el CRS fuente.")
    return f"EPSG:{epsg}"


def _map_bounds_from_corners(corner_map: dict[str, CornerDetection], mode: str) -> tuple[float, float, float, float]:
    tl = corner_map["top_left"]
    tr = corner_map["top_right"]
    bl = corner_map["bottom_left"]
    br = corner_map["bottom_right"]

    if mode == "geographic":
        values = [tl.longitude, tr.longitude, bl.longitude, br.longitude, tl.latitude, tr.latitude, bl.latitude, br.latitude]
        if any(value is None for value in values):
            raise ValueError("Las coordenadas geograficas estan incompletas.")
        if not (float(tl.longitude) < float(tr.longitude) and float(bl.longitude) < float(br.longitude)):
            raise ValueError("Las longitudes no forman un marco geografico consistente. Revisa el modo o corrige las esquinas.")
        if not (float(tl.latitude) > float(bl.latitude) and float(tr.latitude) > float(br.latitude)):
            raise ValueError("Las latitudes no forman un marco geografico consistente. Revisa el modo o corrige las esquinas.")
        west = min(float(tl.longitude), float(bl.longitude))
        east = max(float(tr.longitude), float(br.longitude))
        south = min(float(bl.latitude), float(br.latitude))
        north = max(float(tl.latitude), float(tr.latitude))
        return west, south, east, north

    values = [tl.east, tr.east, bl.east, br.east, tl.north, tr.north, bl.north, br.north]
    if any(value is None for value in values):
        raise ValueError("Las coordenadas proyectadas estan incompletas.")
    if not (float(tl.east) < float(tr.east) and float(bl.east) < float(br.east)):
        raise ValueError("Los eastings no forman un marco UTM consistente. Revisa el modo o corrige las esquinas.")
    if not (float(tl.north) > float(bl.north) and float(tr.north) > float(br.north)):
        raise ValueError("Los northings no forman un marco UTM consistente. Revisa el modo o corrige las esquinas.")
    west = min(float(tl.east), float(bl.east))
    east = max(float(tr.east), float(br.east))
    south = min(float(bl.north), float(br.north))
    north = max(float(tl.north), float(tr.north))
    return west, south, east, north


def _build_full_image_transform(
    corners: dict[str, CornerDetection],
    bounds: tuple[float, float, float, float],
) -> Affine:
    west, south, east, north = bounds
    tl = corners["top_left"]
    tr = corners["top_right"]
    bl = corners["bottom_left"]
    br = corners["bottom_right"]

    width_top = tr.pixel_x - tl.pixel_x
    width_bottom = br.pixel_x - bl.pixel_x
    height_left = bl.pixel_y - tl.pixel_y
    height_right = br.pixel_y - tr.pixel_y
    if width_top <= 0 or width_bottom <= 0 or height_left <= 0 or height_right <= 0:
        raise ValueError("Las intersecciones detectadas no forman un marco valido para georreferenciar.")

    pixel_width = ((east - west) / width_top + (east - west) / width_bottom) / 2.0
    pixel_height = ((south - north) / height_left + (south - north) / height_right) / 2.0
    translate_x = west - (pixel_width * tl.pixel_x)
    translate_y = north - (pixel_height * tl.pixel_y)
    return Affine(pixel_width, 0.0, translate_x, 0.0, pixel_height, translate_y)


def export_geotiff(
    output_path: Path,
    image: Image.Image,
    corners: list[CornerDetection],
    *,
    mode: str,
    map_bbox: tuple[float, float, float, float],
    utm_zone: str,
    output_epsg: int | None = None,
) -> None:
    corner_map = _require_corners(corners)
    bounds = _map_bounds_from_corners(corner_map, mode)
    src_crs = _resolve_source_crs(mode, utm_zone)
    full_image = image.convert("RGB")
    data = np.moveaxis(np.asarray(full_image), 2, 0)
    src_transform = _build_full_image_transform(corner_map, bounds)

    destination_epsg = output_epsg or int(src_crs.split(":")[1])
    if destination_epsg == int(src_crs.split(":")[1]):
        _write_geotiff(output_path, data, src_transform, src_crs)
        return

    dst_crs = f"EPSG:{destination_epsg}"
    dst_data, dst_transform = _reproject_rgb(data, src_transform, src_crs, dst_crs)
    _write_geotiff(output_path, dst_data, dst_transform, dst_crs)
