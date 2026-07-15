# ⚖️ Licencia / License (Dual Licensing)

Este proyecto se distribuye bajo un modelo de **Licencia Dual**:

1. **Uso de Código Abierto (GNU GPLv3):** Puedes usar, estudiar, modificar y redistribuir este software de forma gratuita, siempre y cuando cualquier versión modificada o distribución derivada también sea 100% de código abierto bajo la licencia GNU GPLv3.
2. **Uso Comercial / Privado (Licencia Comercial):** Si deseas integrar este código en software propietario, cerrado o comercial (sin la obligación de abrir tu propio código fuente bajo la GPLv3), debes adquirir una licencia comercial exclusiva. Por favor, ponte en contacto con el autor para acordar los términos.

Para más detalles, consulta el archivo [LICENSE](LICENSE).

---
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
