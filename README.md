# GeoRefMaps

MVP tool for semi-automatic georeferencing of geological maps from PDFs and raster images.

## 🌍 Overview

GeoRefMaps is designed to accelerate the georeferencing of geological maps by automatically detecting coordinate information along map borders and generating Ground Control Points (GCPs).

Originally developed for workflows such as GEOCATMIN, it generalizes well to regional geological mapping and GIS integration tasks.

## 🚀 Features

- Automatic detection of corner coordinates
- Supports PDF (vector) and raster images (PNG, JPG, TIFF)
- OCR fallback using Tesseract
- Semi-automatic workflow with manual correction
- Export of GCPs (JSON)
- Export of fully georeferenced GeoTIFF
- Support for geographic and UTM coordinate systems
- Reprojection to target CRS

## ⚙️ Workflow

1. Load a PDF or image
2. Render preview of the first page
3. Extract vector text (PDF) or apply OCR
4. Detect coordinate patterns (UTM or geographic)
5. Assign candidates to corners
6. Allow manual correction
7. Export GCPs and GeoTIFF

## 📦 Installation

```powershell
pip install -r requirements.txt
```

## ▶️ Run

```powershell
python -m app.main
```

## 🧭 Spatial Reference Rules

- latitude/longitude → WGS84 (EPSG:4326)
- east/north → WGS84 / UTM
- Supported zones:
  - 17S → EPSG:32717
  - 18S → EPSG:32718
  - 19S → EPSG:32719

## 📁 Supported Formats

- PDF
- PNG
- JPG / JPEG
- TIFF

## 🧪 Data

Test maps can be placed in:

data/test_maps/

Generated outputs should NOT be versioned:

data/evaluation_outputs/
data/generated/
exports/

## ⚠️ Status

This is an MVP optimized for:

- maps with border coordinates
- first page processing
- semi-automatic workflows
- OCR-assisted extraction

## 🔄 Reprojection

Outputs can be exported in:

- EPSG:4326
- EPSG:32717 / 32718 / 32719
