<p align="center"><a href="README.md">English</a> · <strong>Español</strong></p>

# GeoRefMaps

**Georreferenciación semiautomática de mapas geológicos y figuras escaneadas.**

Extrae etiquetas de coordenadas de PDF o imágenes, permite revisar cuatro
esquinas y exporta un GeoTIFF documentado con un CRS de origen explícito.

> La detección automática propone puntos de control; no demuestra que el datum,
> la zona UTM ni las esquinas sean correctos. Compara el resultado con una capa
> de referencia fiable antes de utilizarlo en un análisis.

## Entradas y alcance

Admite PDF, PNG, JPEG y TIFF. Los PDF con texto vectorial permiten extraer
etiquetas sin OCR; los escaneos necesitan Tesseract y bordes legibles. El
procesamiento PDF se limita actualmente a la página seleccionada/primera.

| Modo de coordenadas | CRS de origen |
| --- | --- |
| Longitud/latitud | WGS 84, EPSG:4326 |
| UTM 17 Sur | WGS 84, EPSG:32717 |
| UTM 18 Sur | WGS 84, EPSG:32718 |
| UTM 19 Sur | WGS 84, EPSG:32719 |

No fuerces mapas PSAD56, SAD69 o mallas locales a estos preajustes. Su
transformación requiere un flujo explícito que este MVP aún no generaliza.

## Instalación y apertura

Requiere Python 3.10 o superior. Usa un entorno Python aislado:

~~~powershell
git clone https://github.com/jordan-zav/GeoRefMaps.git
cd GeoRefMaps
python -m pip install -r requirements.txt
python -m app.main
~~~

En Windows también está disponible run_georefmaps.bat. Instala
[Tesseract](https://github.com/tesseract-ocr/tesseract) por separado cuando
necesites OCR; no es obligatorio para extraer texto vectorial de un PDF.

## Flujo de uso

1. Abre el mapa y comprueba el datum/CRS declarado en su cartela.
2. Revisa las coordenadas detectadas y el modo propuesto.
3. Corrige manualmente la asignación de las cuatro esquinas.
4. Selecciona la zona UTM o el modo geográfico correcto.
5. Guarda el registro JSON de puntos de control.
6. Exporta el GeoTIFF y, opcionalmente, reproyéctalo a otro EPSG.
7. Ábrelo en QGIS y contrasta extensión, rotación y ajuste con referencias.

El JSON conserva modo, CRS y controles aceptados. El GeoTIFF RGB usa el marco
revisado; Rasterio realiza la reproyección opcional. El método de cuatro
esquinas es adecuado para marcos rectangulares, no sustituye un ajuste con más
controles cuando el papel o escaneo está deformado.

## Organización

| Módulo | Función |
| --- | --- |
| app/main.py | Interfaz Tkinter y flujo del operador |
| app/pdf_processing.py | Carga y extracción de texto vectorial |
| app/ocr.py | Localización de Tesseract y OCR de bordes |
| app/detector.py | Análisis de etiquetas y asociación de esquinas |
| app/export.py | JSON, GeoTIFF y reproyección |
| app/models.py | Modelos compartidos |

## Estado y límites

La versión 1.0 es un MVP orientado a mapas rectangulares del Perú con WGS84
geográfico o UTM 17S–19S. No dispone todavía de una suite automática de
regresión. Quedan pendientes más datums, selección multipágina generalizada,
ajustes rotados/no lineales y reporte cuantitativo de residuos.

## Licencia y contacto

[GNU GPL v3](LICENSE). Jordan Zavaleta — GisGeo Dev.
[Correo](mailto:jordanzav@gisgeo.dev) · [Sitio web](https://gisgeo.dev).
