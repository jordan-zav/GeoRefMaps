from __future__ import annotations

import tkinter as tk
import unicodedata
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from app.detector import detect_corner_gcps
from app.export import export_gcps, export_geotiff
from app.ocr import extract_ocr_text_items, tesseract_available
from app.pdf_processing import PDFPageData


class App(tk.Tk):
    BRAND_BG = "#EEF5F8"
    BRAND_CARD = "#FFFFFF"
    BRAND_BORDER = "#C9D9E4"
    BRAND_TEXT = "#183247"
    BRAND_MUTED = "#5E7485"
    BRAND_BLUE = "#174F8A"
    BRAND_BLUE_ALT = "#1F74B7"
    BRAND_CYAN = "#33B6E6"
    BRAND_GREEN = "#5FAF4E"

    def __init__(self) -> None:
        super().__init__()
        self.title("GeoRefMaps")
        self.geometry("1920x1080")
        self.minsize(920, 760)
        self.configure(bg=self.BRAND_BG)

        self.page_data: PDFPageData | None = None
        self.rendered_image = None
        self.display_image = None
        self.tk_image = None
        self.detection_result = None
        self.detected_items = []
        self.focus_bbox = None
        self.grid_lines = []
        self.zoom_factor = 1.0
        self.min_zoom = 0.2
        self.max_zoom = 3.5
        self.zoom_var = tk.DoubleVar(value=100.0)
        self._last_auto_target_epsg = "32718"
        self.logo_photo = None
        self.logo_icon = None
        self.entry_vars: dict[str, dict[str, tk.StringVar]] = {}

        self._load_branding_assets()
        self._configure_styles()
        self._build_ui()

    def _load_branding_assets(self) -> None:
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "branding" / "logo.png"
        if not logo_path.exists():
            return

        try:
            logo_image = Image.open(logo_path).convert("RGBA")
        except Exception:
            return

        try:
            header_logo = logo_image.copy()
            header_logo.thumbnail((56, 56), Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(header_logo)
        except Exception:
            self.logo_photo = None

        try:
            icon_logo = logo_image.copy()
            icon_logo.thumbnail((64, 64), Image.Resampling.LANCZOS)
            self.logo_icon = ImageTk.PhotoImage(icon_logo)
            self.iconphoto(True, self.logo_icon)
        except Exception:
            self.logo_icon = None

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=self.BRAND_BG)
        style.configure("Card.TFrame", background=self.BRAND_CARD, relief="solid", borderwidth=1)
        style.configure("Header.TLabel", background=self.BRAND_BG, foreground=self.BRAND_BLUE, font=("Segoe UI", 20, "bold"))
        style.configure("SubHeader.TLabel", background=self.BRAND_BG, foreground=self.BRAND_MUTED, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=self.BRAND_CARD, foreground=self.BRAND_BLUE, font=("Segoe UI", 10, "bold"))
        style.configure("Field.TLabel", background=self.BRAND_CARD, foreground=self.BRAND_TEXT, font=("Segoe UI", 9, "bold"))
        style.configure("Status.TLabel", background=self.BRAND_BG, foreground=self.BRAND_MUTED, font=("Segoe UI", 9))
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), background=self.BRAND_BLUE, foreground="#FFFFFF", borderwidth=0, padding=(12, 8))
        style.map("Primary.TButton", background=[("active", self.BRAND_BLUE_ALT), ("pressed", self.BRAND_BLUE_ALT)])
        style.configure("Secondary.TButton", font=("Segoe UI", 9), background="#F7FBFD", foreground=self.BRAND_BLUE, padding=(12, 8))
        style.map("Secondary.TButton", background=[("active", "#E8F3F8"), ("pressed", "#E8F3F8")])
        style.configure("App.TCheckbutton", background=self.BRAND_CARD, foreground=self.BRAND_TEXT, font=("Segoe UI", 9))
        style.configure("App.TLabelframe", background=self.BRAND_CARD, borderwidth=1, relief="solid")
        style.configure("App.TLabelframe.Label", background=self.BRAND_CARD, foreground=self.BRAND_BLUE, font=("Segoe UI", 9, "bold"))
        style.configure("App.TCombobox", padding=4, foreground=self.BRAND_TEXT, fieldbackground="#F9FCFE", background="#F9FCFE", arrowcolor=self.BRAND_BLUE)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, style="App.TFrame", padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header_content = ttk.Frame(header, style="App.TFrame")
        header_content.pack(fill="x")
        if self.logo_photo is not None:
            logo_label = tk.Label(header_content, image=self.logo_photo, bg=self.BRAND_BG)
            logo_label.pack(side="left", padx=(0, 12))

        header_text = ttk.Frame(header_content, style="App.TFrame")
        header_text.pack(side="left", fill="x", expand=True)
        ttk.Label(header_text, text="GeoRefMaps", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header_text,
            text="Detección semiautomática de coordenadas para georreferenciar mapas en el territorio peruano.",
            style="SubHeader.TLabel",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        controls_card = ttk.Frame(outer, style="Card.TFrame", padding=14)
        controls_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        controls_card.columnconfigure(1, weight=1)

        self.input_path_var = tk.StringVar()
        ttk.Label(controls_card, text="Archivo de entrada", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(controls_card, textvariable=self.input_path_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(controls_card, text="Abrir", command=self.open_document, style="Secondary.TButton").grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Button(controls_card, text="Ayuda", command=lambda: webbrowser.open("https://gisgeo.dev/portfolio/georefmaps/"), style="Secondary.TButton").grid(row=0, column=3, padx=(8, 0), pady=4)

        action_column = ttk.Frame(controls_card, style="Card.TFrame")
        action_column.grid(row=0, column=4, rowspan=2, sticky="nw", padx=(14, 0), pady=2)
        ttk.Button(action_column, text="Detectar", command=self.detect, style="Primary.TButton").pack(fill="x")
        ttk.Button(action_column, text="Exportar GeoTIFF", command=self.export_geotiff, style="Secondary.TButton").pack(fill="x", pady=(8, 0))

        settings_row = ttk.Frame(controls_card, style="Card.TFrame")
        settings_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 4))
        settings_row.columnconfigure(5, weight=1)

        ttk.Label(settings_row, text="Zona UTM", style="Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.utm_zone_var = tk.StringVar(value="18S")
        self.utm_zone_combo = ttk.Combobox(
            settings_row,
            textvariable=self.utm_zone_var,
            values=["17S", "18S", "19S"],
            width=10,
            state="readonly",
            style="App.TCombobox",
        )
        self.utm_zone_combo.grid(row=0, column=1, sticky="w", padx=(0, 24))

        ttk.Label(settings_row, text="EPSG destino", style="Field.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.target_epsg_var = tk.StringVar(value="4326")
        self.target_epsg_combo = ttk.Combobox(
            settings_row,
            textvariable=self.target_epsg_var,
            values=["4326", "32717", "32718", "32719"],
            width=12,
            state="readonly",
            style="App.TCombobox",
        )
        self.target_epsg_combo.grid(row=0, column=3, sticky="w", padx=(0, 24))

        self.use_ocr_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            settings_row,
            text="Usar OCR de respaldo",
            variable=self.use_ocr_var,
            style="App.TCheckbutton",
        ).grid(row=0, column=4, sticky="w", padx=(0, 24))

        ttk.Label(settings_row, text="Modo de detección", style="Field.TLabel").grid(row=0, column=6, sticky="e", padx=(0, 8))
        self.mode_var = tk.StringVar(value="Proyectado")
        self.mode_combo = ttk.Combobox(
            settings_row,
            textvariable=self.mode_var,
            values=["Proyectado", "Geográfico (experimental)"],
            width=26,
            state="readonly",
            style="App.TCombobox",
        )
        self.mode_combo.grid(row=0, column=7, sticky="w")
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)
        self.mode_detection_status_var = tk.StringVar(value="Disponibilidad: sin analizar.")
        ttk.Label(
            settings_row,
            textvariable=self.mode_detection_status_var,
            style="Status.TLabel",
        ).grid(row=1, column=6, columnspan=2, sticky="w", pady=(6, 0))

        status_row = ttk.Frame(outer, style="App.TFrame")
        status_row.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.status_var = tk.StringVar(value="Carga un PDF o PNG para comenzar.")
        ttk.Label(status_row, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")

        body = ttk.Panedwindow(outer, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")

        left_card = ttk.Frame(body, style="Card.TFrame", padding=12)
        right_card = ttk.Frame(body, style="Card.TFrame", padding=12, width=400)
        body.add(left_card, weight=5)
        body.add(right_card, weight=2)

        ttk.Label(left_card, text="Vista previa del mapa", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        canvas_frame = ttk.Frame(left_card, style="Card.TFrame")
        canvas_frame.pack(fill="both", expand=True)
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(canvas_frame, bg="#1C2F3F", highlightthickness=0, xscrollincrement=20, yscrollincrement=20)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas_h_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas_h_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas_v_scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas_v_scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=self.canvas_h_scroll.set, yscrollcommand=self.canvas_v_scroll.set)
        self.canvas.bind("<ButtonPress-1>", self._start_canvas_pan)
        self.canvas.bind("<B1-Motion>", self._drag_canvas_pan)
        self.canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_canvas_shift_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_canvas_ctrl_mousewheel)

        zoom_row = ttk.Frame(left_card, style="Card.TFrame")
        zoom_row.pack(fill="x", pady=(8, 0))
        ttk.Label(zoom_row, text="Zoom", style="Field.TLabel").pack(side="left", padx=(0, 10))
        self.zoom_scale = tk.Scale(
            zoom_row,
            from_=self.min_zoom * 100.0,
            to=self.max_zoom * 100.0,
            orient="horizontal",
            variable=self.zoom_var,
            showvalue=False,
            resolution=5,
            highlightthickness=0,
            bd=0,
            sliderlength=18,
            troughcolor="#D8E8EF",
            activebackground=self.BRAND_CYAN,
            command=self._on_zoom_scale_changed,
        )
        self.zoom_scale.pack(side="left", fill="x", expand=True)
        self.zoom_value_label = ttk.Label(zoom_row, text="100%", style="Field.TLabel")
        self.zoom_value_label.pack(side="left", padx=(10, 0))

        ttk.Label(right_card, text="Esquinas detectadas", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            right_card,
            text="Revisión y corrección manual para coordenadas no coincidentes con las intersecciones cartográficas.",
            style="SubHeader.TLabel",
            wraplength=600,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        self.form_frame = ttk.Frame(right_card, style="Card.TFrame")
        self.form_frame.pack(fill="x")

        ttk.Separator(right_card).pack(fill="x", pady=12)
        ttk.Label(right_card, text="Parámetros", style="Section.TLabel").pack(anchor="w")
        self.notes_text = tk.Text(
            right_card,
            height=18,
            wrap="word",
            relief="flat",
            bg="#F7FBFD",
            fg=self.BRAND_TEXT,
            font=("Segoe UI", 9),
            padx=10,
            pady=10,
        )
        self.notes_text.pack(fill="both", expand=True, pady=(8, 0))

        footer = ttk.Frame(outer, style="App.TFrame")
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)

        left_footer = ttk.Frame(footer, style="App.TFrame")
        left_footer.grid(row=0, column=0, sticky="w")

        author = tk.Label(
            left_footer,
            text="Zavaleta, J.",
            font=("Segoe UI", 8, "underline"),
            fg=self.BRAND_BLUE_ALT,
            bg=self.BRAND_BG,
            cursor="hand2",
        )
        author.pack(side="left", padx=(0, 1))
        author.bind("<Button-1>", lambda _event: webbrowser.open("https://linkedin.com/in/jordan-zav"))

        affiliation = tk.Label(
            left_footer,
            text="Desarrollador principal, Estudiante de Ingeniería Geológica en la Universidad Nacional de Ingeniería (UNI) |",
            font=("Segoe UI", 8, "italic"),
            fg=self.BRAND_MUTED,
            bg=self.BRAND_BG,
        )
        affiliation.pack(side="left")

        collaborator = tk.Label(
            left_footer,
            text="Yacila, F.",
            font=("Segoe UI", 8, "underline"),
            fg=self.BRAND_BLUE_ALT,
            bg=self.BRAND_BG,
            cursor="hand2",
        )
        collaborator.pack(side="left", padx=(0, 1))
        collaborator.bind("<Button-1>", lambda _event: webbrowser.open("https://www.linkedin.com/in/fabian-yacila-gomez/"))

        collaborator_role = tk.Label(
            left_footer,
            text="Colaborador conceptual",
            font=("Segoe UI", 8, "italic"),
            fg=self.BRAND_MUTED,
            bg=self.BRAND_BG,
        )
        collaborator_role.pack(side="left")

        ttk.Label(
            footer,
            text="GeoRefMaps | Licencia MIT",
            style="Status.TLabel",
        ).grid(row=0, column=1, sticky="e")

    def open_document(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Selecciona un PDF o imagen",
            filetypes=[
                ("Mapas compatibles", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff"),
                ("PDF files", "*.pdf"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("TIFF files", "*.tif *.tiff"),
            ],
        )
        if not file_path:
            return

        self.page_data = PDFPageData(Path(file_path))
        self.rendered_image = self.page_data.render_image()
        self.display_image = self.rendered_image
        self.detection_result = None
        self.detected_items = []
        self.focus_bbox = None
        self.grid_lines = []
        self.zoom_factor = 1.0
        self._sync_zoom_controls()
        self.input_path_var.set(file_path)
        self.mode_var.set("Proyectado")
        self.mode_combo.config(values=["Proyectado", "Geográfico (experimental)"], state="readonly")
        self.mode_detection_status_var.set("Disponibilidad: sin analizar.")
        self._refresh_target_epsg_default(force=True)
        self._draw_image()
        kind_label = "PDF" if self.page_data.kind == "pdf" else "imagen"
        self.status_var.set(f"{kind_label.capitalize()} cargado: {Path(file_path).name}")
        self.notes_text.delete("1.0", tk.END)
        if self.page_data.kind == "pdf":
            self.notes_text.insert(tk.END, "PDF cargado. Ejecuta la detección.\n")
        else:
            self.notes_text.insert(tk.END, "Imagen cargada. OCR se usará para intentar leer las coordenadas.\n")

    def detect(self) -> None:
        if self.page_data is None:
            messagebox.showwarning("Sin archivo", "Primero carga un PDF o una imagen.")
            return

        items = self.page_data.extract_text_items()
        focus_bbox = self.page_data.detect_main_map_bbox(items)
        self.focus_bbox = focus_bbox
        self.grid_lines = self.page_data.extract_grid_lines(focus_bbox) if self.page_data.kind == "pdf" else []
        if self.page_data.kind == "pdf":
            notes = [f"Texto vectorial detectado: {len(items)} spans."]
            if self.grid_lines:
                notes.append(f"Líneas de grilla vectorial detectadas: {len(self.grid_lines)}.")
        else:
            notes = ["Entrada raster detectada: no hay texto vectorial disponible."]

        should_use_ocr = self.use_ocr_var.get() or self.page_data.kind == "image"
        if should_use_ocr:
            if tesseract_available():
                ocr_items = extract_ocr_text_items(self.rendered_image, focus_bbox=focus_bbox)
                items.extend(ocr_items)
                notes.append(f"Texto OCR detectado: {len(ocr_items)} spans.")
            else:
                notes.append("OCR no disponible: instala Tesseract y agrégalo al PATH.")

        self.detected_items = list(items)
        self._run_detection(notes=notes)
        self._configure_mode_selector()
        if self.detection_result is not None:
            mode_label = self._mode_to_label(self.detection_result.mode)
            self.status_var.set(f"Detecci?n terminada en modo {mode_label}. Revisa las esquinas antes de exportar.")

    def _run_detection(self, notes: list[str] | None = None) -> None:
        if self.page_data is None:
            return

        base_notes = notes or []
        width_px, height_px = self.page_data.image_size_pixels
        width_pt, height_pt = self.page_data.page_size_points
        preferred_mode = self._label_to_mode(self.mode_var.get().strip())
        self.detection_result = detect_corner_gcps(
            list(self.detected_items),
            width_pt,
            height_pt,
            width_px,
            height_px,
            focus_bbox=self.focus_bbox,
            grid_lines=self.grid_lines,
            raster_image=self.rendered_image if self.page_data and self.page_data.kind == "image" else None,
            preferred_mode=preferred_mode,
        )
        self.detection_result.notes = base_notes + self.detection_result.notes
        self._draw_image()
        self._render_form()
        self._render_notes()
        self._update_mode_detection_status()
        self._refresh_target_epsg_default()

    def _configure_mode_selector(self) -> None:
        selected_mode = self._label_to_mode(self.mode_var.get().strip())
        mode_labels = [self._mode_to_label(mode) for mode in self._gui_available_modes([])]
        self.mode_combo.config(values=mode_labels, state="readonly")
        if selected_mode not in {"projected", "geographic"}:
            selected_mode = "projected"
        self.mode_var.set(self._mode_to_label(selected_mode))

    def _on_mode_changed(self, _event=None) -> None:
        self._refresh_target_epsg_default()
        if self.detection_result is None or not self.detected_items:
            return
            messagebox.showwarning("Sin detección", "Primero ejecuta la detección.")
            return
        self._run_detection()
        self._configure_mode_selector()

    def export(self) -> None:
        if self.detection_result is None:
            messagebox.showwarning("Sin detección", "Primero ejecuta la detección.")
            return

        self._pull_form_values()
        file_path = filedialog.asksaveasfilename(
            title="Guardar GCPs",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not file_path:
            return

        export_gcps(
            Path(file_path),
            self.detection_result.corners,
            self.detection_result.mode,
            self.utm_zone_var.get(),
        )
        self.status_var.set(f"JSON exportado: {Path(file_path).name}")

    def export_geotiff(self) -> None:
        if self.detection_result is None or self.rendered_image is None:
            messagebox.showwarning("Sin detección", "Primero ejecuta la detección.")
            return

        if self.focus_bbox is None:
            messagebox.showwarning("Sin marco", "No se pudo determinar el marco principal para georreferenciar.")
            return

        self._pull_form_values()
        file_path = filedialog.asksaveasfilename(
            title="Guardar GeoTIFF",
            defaultextension=".tif",
            filetypes=[("GeoTIFF files", "*.tif *.tiff")],
        )
        if not file_path:
            return

        try:
            source_mode = self._label_to_mode(self.mode_var.get().strip()) or self.detection_result.mode
            default_output_epsg = 4326 if source_mode == "geographic" else {"17S": 32717, "18S": 32718, "19S": 32719}.get(self.utm_zone_var.get(), 32718)
            output_epsg = self._safe_int(self.target_epsg_var.get()) or default_output_epsg
            export_geotiff(
                Path(file_path),
                self.rendered_image,
                self.detection_result.corners,
                mode=source_mode,
                map_bbox=self.focus_bbox,
                utm_zone=self.utm_zone_var.get(),
                output_epsg=output_epsg,
            )
        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc))
            return

        self.status_var.set(f"GeoTIFF exportado: {Path(file_path).name} (EPSG:{output_epsg})")

    def _draw_image(self) -> None:
        self.canvas.delete("all")
        if self.rendered_image is None:
            return

        self.display_image = self._build_display_image()
        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.canvas.config(scrollregion=(0, 0, self.display_image.width, self.display_image.height))
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)

        if self.detection_result is None:
            return

        for corner in self.detection_result.corners:
            x = corner.pixel_x * self.zoom_factor
            y = corner.pixel_y * self.zoom_factor
            marker_radius = max(6, int(round(10 * self.zoom_factor)))
            font_size = max(9, int(round(11 * min(self.zoom_factor, 1.6))))
            corner_label = self._corner_name_to_label(corner.name)
            label_x = x + max(56, 78 * self.zoom_factor)
            label_y = y + max(14, 16 * self.zoom_factor)
            self.canvas.create_oval(x - marker_radius, y - marker_radius, x + marker_radius, y + marker_radius, outline="#ff5c5c", width=3)
            for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                self.canvas.create_text(
                    label_x + offset_x,
                    label_y + offset_y,
                    text=corner_label,
                    fill="#000000",
                    font=("Segoe UI", font_size, "bold"),
                )
            self.canvas.create_text(
                label_x,
                label_y,
                text=corner_label,
                fill="#ffd966",
                font=("Segoe UI", font_size, "bold"),
            )

    def _build_display_image(self) -> Image.Image:
        if self.rendered_image is None or abs(self.zoom_factor - 1.0) < 1e-6:
            return self.rendered_image

        new_width = max(1, int(round(self.rendered_image.width * self.zoom_factor)))
        new_height = max(1, int(round(self.rendered_image.height * self.zoom_factor)))
        return self.rendered_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def _sync_zoom_controls(self) -> None:
        zoom_percent = self.zoom_factor * 100.0
        self.zoom_var.set(zoom_percent)
        self.zoom_value_label.config(text=f"{int(round(zoom_percent))}%")

    def _set_zoom(
        self,
        new_zoom: float,
        *,
        anchor_x: float | None = None,
        anchor_y: float | None = None,
        event_x: int | None = None,
        event_y: int | None = None,
    ) -> None:
        if self.rendered_image is None:
            return

        new_zoom = min(self.max_zoom, max(self.min_zoom, new_zoom))
        if abs(new_zoom - self.zoom_factor) < 1e-6:
            self._sync_zoom_controls()
            return

        if anchor_x is None:
            anchor_x = self.canvas.canvasx(self.canvas.winfo_width() / 2)
        if anchor_y is None:
            anchor_y = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        if event_x is None:
            event_x = self.canvas.winfo_width() // 2
        if event_y is None:
            event_y = self.canvas.winfo_height() // 2

        rel_x = anchor_x / max(1.0, self.display_image.width if self.display_image else self.rendered_image.width)
        rel_y = anchor_y / max(1.0, self.display_image.height if self.display_image else self.rendered_image.height)

        self.zoom_factor = new_zoom
        self._draw_image()
        self.update_idletasks()
        self._sync_zoom_controls()

        target_x = rel_x * self.display_image.width
        target_y = rel_y * self.display_image.height
        x_fraction = (target_x - event_x) / max(1, self.display_image.width)
        y_fraction = (target_y - event_y) / max(1, self.display_image.height)
        self.canvas.xview_moveto(min(1.0, max(0.0, x_fraction)))
        self.canvas.yview_moveto(min(1.0, max(0.0, y_fraction)))

    def _on_zoom_scale_changed(self, value: str) -> None:
        if self.rendered_image is None:
            self.zoom_value_label.config(text=f"{int(round(float(value)))}%")
            return
        self._set_zoom(float(value) / 100.0)

    def _start_canvas_pan(self, event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _drag_canvas_pan(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_canvas_mousewheel(self, event) -> None:
        if self.rendered_image is None:
            return
        delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta * 3, "units")

    def _on_canvas_shift_mousewheel(self, event) -> None:
        if self.rendered_image is None:
            return
        delta = -1 if event.delta > 0 else 1
        self.canvas.xview_scroll(delta * 3, "units")

    def _on_canvas_ctrl_mousewheel(self, event) -> None:
        if self.rendered_image is None:
            return

        direction = 1 if event.delta > 0 else -1
        zoom_step = 1.15 if direction > 0 else (1 / 1.15)
        self._set_zoom(
            self.zoom_factor * zoom_step,
            anchor_x=self.canvas.canvasx(event.x),
            anchor_y=self.canvas.canvasy(event.y),
            event_x=event.x,
            event_y=event.y,
        )

    def _render_form(self) -> None:
        for child in self.form_frame.winfo_children():
            child.destroy()

        self.entry_vars.clear()
        mode = self.detection_result.mode

        for corner in self.detection_result.corners:
            block = ttk.LabelFrame(self.form_frame, text=self._corner_name_to_label(corner.name), style="App.TLabelframe")
            block.pack(fill="x", pady=6)
            status_label = "Intersección de grilla" if corner.source == "grid_intersection" else "Auto confiable" if corner.source == "auto" and not corner.notes else "Revisión recomendada"
            ttk.Label(block, text=status_label, style="Field.TLabel").pack(anchor="w", padx=8, pady=(6, 0))

            vars_for_corner: dict[str, tk.StringVar] = {}
            if mode == "projected":
                fields = {
                    "east": "" if corner.east is None else str(corner.east),
                    "north": "" if corner.north is None else str(corner.north),
                }
            else:
                fields = {
                    "longitude": "" if corner.longitude is None else str(corner.longitude),
                    "latitude": "" if corner.latitude is None else str(corner.latitude),
                }

            for field_name, value in fields.items():
                row = ttk.Frame(block, style="Card.TFrame")
                row.pack(fill="x", padx=8, pady=5)
                ttk.Label(row, text=field_name.capitalize(), width=12, style="Field.TLabel").pack(side="left")
                var = tk.StringVar(value=value)
                ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
                vars_for_corner[field_name] = var

            self.entry_vars[corner.name] = vars_for_corner

    def _pull_form_values(self) -> None:
        if self.detection_result is None:
            return

        for corner in self.detection_result.corners:
            vars_for_corner = self.entry_vars.get(corner.name, {})
            if "east" in vars_for_corner:
                corner.east = self._safe_float(vars_for_corner["east"].get())
                corner.north = self._safe_float(vars_for_corner["north"].get())
            if "longitude" in vars_for_corner:
                corner.longitude = self._safe_float(vars_for_corner["longitude"].get())
                corner.latitude = self._safe_float(vars_for_corner["latitude"].get())
            corner.source = "reviewed"

    def _default_output_epsg_for_selected_mode(self) -> str:
        mode = self._label_to_mode(self.mode_var.get().strip())
        if mode == "geographic":
            return "4326"
        return {"17S": "32717", "18S": "32718", "19S": "32719"}.get(self.utm_zone_var.get(), "32718")

    def _refresh_target_epsg_default(self, *, force: bool = False) -> None:
        default_epsg = self._default_output_epsg_for_selected_mode()
        current_epsg = self.target_epsg_var.get().strip()
        if force or not current_epsg or current_epsg == self._last_auto_target_epsg:
            self.target_epsg_var.set(default_epsg)
        self._last_auto_target_epsg = default_epsg

    def _update_mode_detection_status(self) -> None:
        if self.detection_result is None:
            self.mode_detection_status_var.set("Disponibilidad: sin analizar.")
            return

        detected_modes = set(self.detection_result.mode_candidates or [])
        projected_status = "Proyectado detectado" if "projected" in detected_modes else "No proyectado detectado"
        geographic_status = "Geográfico detectado" if "geographic" in detected_modes else "No geográfico detectado"
        self.mode_detection_status_var.set(f"{projected_status} | {geographic_status}")

    def _render_notes(self) -> None:
        self.notes_text.delete("1.0", tk.END)
        if self.detection_result.mode == "geographic":
            self.notes_text.insert(tk.END, "- CRS asumido: WGS 84 (EPSG:4326).\n")
        else:
            zone = self.utm_zone_var.get()
            epsg = {"17S": 32717, "18S": 32718, "19S": 32719}.get(zone, "desconocido")
            self.notes_text.insert(tk.END, f"- CRS asumido: WGS 84 / UTM zone {zone} (EPSG:{epsg}).\n")
        if self.detection_result.mode_candidates and "geographic" in self.detection_result.mode_candidates:
            self.notes_text.insert(
                tk.END,
                "- El modo Geográfico (experimental) está disponible en la GUI; úsalo con validación visual adicional.\n",
            )
        if self.detection_result.mode_candidates and len(self.detection_result.mode_candidates) > 1:
            self.notes_text.insert(
                tk.END,
                f"- Modos plausibles detectados: {', ' .join(self._mode_to_label(mode) for mode in self.detection_result.mode_candidates)}.\n",
            )
        if self.detection_result.focus_bbox is not None:
            x0, y0, x1, y1 = self.detection_result.focus_bbox
            self.notes_text.insert(tk.END, f"- Marco principal para exportación completa: ({x0:.0f}, {y0:.0f}) a ({x1:.0f}, {y1:.0f}).\n")
        for note in self.detection_result.notes:
            self.notes_text.insert(tk.END, f"- {note}\n")

    @staticmethod
    def _safe_float(value: str) -> float | None:
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _safe_int(value: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    @staticmethod
    def _corner_name_to_label(name: str) -> str:
        return {
            "top_left": "Superior izquierda",
            "top_right": "Superior derecha",
            "bottom_left": "Inferior izquierda",
            "bottom_right": "Inferior derecha",
        }.get(name, name.replace("_", " ").title())

    @staticmethod
    def _mode_to_label(mode: str) -> str:
        return {"projected": "Proyectado", "geographic": "Geográfico (experimental)"}.get(mode, mode)

    @staticmethod
    def _label_to_mode(label: str) -> str:
        normalized = unicodedata.normalize("NFKD", label.strip().lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        return {
            "proyectado": "projected",
            "geografico": "geographic",
            "geografico (experimental)": "geographic",
        }.get(normalized, label)

    @staticmethod
    def _gui_available_modes(modes: list[str]) -> list[str]:
        del modes
        return ["projected", "geographic"]


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
