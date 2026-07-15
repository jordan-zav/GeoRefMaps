# GeoRefMaps

MVP tool for semi-automatic georeferencing of geological maps from PDFs and raster images.


## ⚖️ License (Dual Licensing)

This project is distributed under a **Dual Licensing** model:

1. **Open Source Use (GNU GPLv3):** You can use, study, modify, and redistribute this software for free, provided that any modified version or derivative work is also 100% open source under the GNU GPLv3 license.
2. **Commercial / Private Use (Commercial License):** If you wish to integrate this code into proprietary, closed-source, or commercial software (without the obligation to open your own source code under the GPLv3), you must acquire an exclusive commercial license. Please contact the author to negotiate terms.

For more details, see the [LICENSE](LICENSE) file.

---

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

## License

This project is licensed under the GNU GPLv3 and the Dual Licensing agreement described above. See the [LICENSE](LICENSE) file for more details.
