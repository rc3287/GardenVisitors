"""Image enhancement dialog for GardenVisitors.

Non-destructive: edits are rendered through core.imaging and saved as a new
file in the `edited/` subfolder via MediaFile.save_edited — the original is
never touched. The live preview runs on a downscaled working copy off the
main thread (debounced); the full-resolution render happens only on save.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QSlider, QCheckBox, QScrollArea, QFrame, QApplication,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QThreadPool, QRunnable, QObject, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor

from PIL import Image, ImageOps

from core.imaging import Adjustments, apply as apply_adjustments, auto_enhance

PREVIEW_MAX = 1000   # working-copy size for the live preview
SPOT_RADIUS = 0.02   # default spot-heal radius, normalized to image size


def _pil_to_qimage(img: Image.Image) -> QImage:
    img = img.convert("RGB")
    w, h = img.size
    data = img.tobytes("raw", "RGB")
    # .copy() so the QImage owns its buffer once `data` is gone.
    return QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


# --- Threaded preview render ----------------------------------------------
class _RenderSignals(QObject):
    done = pyqtSignal(int, QImage)


class _RenderTask(QRunnable):
    def __init__(self, img: Image.Image, adj: Adjustments, generation: int, signals: _RenderSignals):
        super().__init__()
        self._img = img
        self._adj = adj
        self._gen = generation
        self._signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            result = apply_adjustments(self._img, self._adj)
            self._signals.done.emit(self._gen, _pil_to_qimage(result))
        except Exception:
            pass


# --- Preview widget with crop / spot overlays ------------------------------
class PreviewArea(QWidget):
    """Paints the rendered preview scaled-to-fit, and handles crop rubber-band
    and spot-heal clicks. Coordinates are reported normalized to [0, 1]."""

    crop_changed = pyqtSignal(object)   # (l, t, r, b) normalized, or None
    spot_added = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #181825; border-radius: 8px;")
        self._pixmap: QPixmap | None = None
        self._crop_mode = False
        self._spot_mode = False
        self._crop_norm: tuple | None = None
        self._drag_start: QPoint | None = None
        self._drag_now: QPoint | None = None

    def set_image(self, qimg: QImage):
        self._pixmap = QPixmap.fromImage(qimg)
        self.update()

    def set_crop_mode(self, on: bool):
        self._crop_mode = on
        self.update()

    def set_spot_mode(self, on: bool):
        self._spot_mode = on

    def set_crop_norm(self, box: tuple | None):
        self._crop_norm = box
        self.update()

    # --- geometry: where the scaled image sits inside the widget ----------
    def _image_rect(self) -> QRect | None:
        if self._pixmap is None or self._pixmap.isNull():
            return None
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph)
        dw, dh = int(pw * scale), int(ph * scale)
        return QRect((ww - dw) // 2, (wh - dh) // 2, dw, dh)

    def _to_norm(self, pos: QPoint) -> tuple | None:
        rect = self._image_rect()
        if rect is None or rect.width() == 0 or rect.height() == 0:
            return None
        x = (pos.x() - rect.x()) / rect.width()
        y = (pos.y() - rect.y()) / rect.height()
        return (min(1.0, max(0.0, x)), min(1.0, max(0.0, y)))

    def paintEvent(self, event):
        p = QPainter(self)
        rect = self._image_rect()
        if self._pixmap and rect:
            p.drawPixmap(rect, self._pixmap)
            if self._crop_mode:
                self._paint_crop(p, rect)
        p.end()

    def _paint_crop(self, p: QPainter, rect: QRect):
        box = self._crop_norm
        if self._drag_start and self._drag_now:
            r = QRect(self._drag_start, self._drag_now).normalized()
        elif box:
            r = QRect(
                rect.x() + int(box[0] * rect.width()),
                rect.y() + int(box[1] * rect.height()),
                int((box[2] - box[0]) * rect.width()),
                int((box[3] - box[1]) * rect.height()),
            )
        else:
            return
        # Dim outside the crop box, outline the box
        overlay = QColor(0, 0, 0, 110)
        p.fillRect(rect, overlay)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(r & rect, Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.drawPixmap(r & rect, self._pixmap, self._src_subrect(r & rect, rect))
        p.setPen(QPen(QColor("#94E2D5"), 2))
        p.drawRect(r & rect)

    def _src_subrect(self, target: QRect, rect: QRect) -> QRect:
        # Map a widget-space target rect back to pixmap source coords.
        sx = self._pixmap.width() / rect.width()
        sy = self._pixmap.height() / rect.height()
        return QRect(
            int((target.x() - rect.x()) * sx), int((target.y() - rect.y()) * sy),
            int(target.width() * sx), int(target.height() * sy),
        )

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._spot_mode:
            norm = self._to_norm(event.pos())
            if norm:
                self.spot_added.emit(norm[0], norm[1])
            return
        if self._crop_mode:
            self._drag_start = event.pos()
            self._drag_now = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._crop_mode and self._drag_start:
            self._drag_now = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if not (self._crop_mode and self._drag_start):
            return
        rect = self._image_rect()
        start, now = self._drag_start, event.pos()
        self._drag_start = self._drag_now = None
        if rect is None:
            return
        a = self._to_norm(start)
        b = self._to_norm(now)
        if a and b:
            l, r = sorted((a[0], b[0]))
            t, btm = sorted((a[1], b[1]))
            if r - l > 0.02 and btm - t > 0.02:
                self._crop_norm = (l, t, r, btm)
                self.crop_changed.emit(self._crop_norm)
        self.update()


# --- The dialog ------------------------------------------------------------
class EditorDialog(QDialog):
    def __init__(self, media, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Améliorer — {media.path.name}")
        self.resize(1100, 720)
        self._media = media
        self.saved_path: Path | None = None

        self._adj = Adjustments()
        self._pool = QThreadPool.globalInstance()
        self._render_signals = _RenderSignals()
        self._render_signals.done.connect(self._on_render_done)
        self._generation = 0

        self._sliders: dict[str, QSlider] = {}
        self._slider_value_labels: dict[str, QLabel] = {}
        self._checks: dict[str, QCheckBox] = {}

        # Load source upright (respect EXIF orientation, like the rest of the app)
        with Image.open(media.path) as im:
            self._full = ImageOps.exif_transpose(im).convert("RGB")
        self._work = self._full.copy()
        self._work.thumbnail((PREVIEW_MAX, PREVIEW_MAX))

        self._build_ui()

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(120)
        self._render_timer.timeout.connect(self._render_preview)
        self._render_preview()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QHBoxLayout(self)

        self._preview = PreviewArea()
        self._preview.crop_changed.connect(self._on_crop_changed)
        self._preview.spot_added.connect(self._on_spot_added)
        root.addWidget(self._preview, stretch=1)

        # --- Controls panel (scrollable) ---
        panel = QWidget()
        panel.setFixedWidth(300)
        col = QVBoxLayout(panel)
        col.setSpacing(8)

        col.addWidget(self._group_label("Exposition / Ton"))
        self._add_slider(col, "brightness", "Luminosité", 20, 300, 100)
        self._add_slider(col, "contrast", "Contraste", 20, 300, 100)
        self._add_slider(col, "gamma", "Ombres (gamma)", 30, 300, 100)
        self._add_slider(col, "clahe", "Contraste local", 0, 50, 0)

        col.addWidget(self._group_label("Couleur"))
        self._add_slider(col, "temperature", "Température", -100, 100, 0)
        self._add_slider(col, "saturation", "Saturation", 0, 300, 100)
        self._add_check(col, "white_balance", "Balance des blancs auto")
        self._add_check(col, "grayscale", "Noir et blanc")

        col.addWidget(self._group_label("Détail"))
        self._add_slider(col, "sharpen", "Netteté", 0, 200, 0)
        self._add_slider(col, "denoise", "Réduction du bruit", 0, 30, 0)

        col.addWidget(self._group_label("Géométrie"))
        geo = QHBoxLayout()
        for label, slot in [
            ("Pivoter ⟳", self._rotate),
            ("Miroir H", lambda: self._toggle_flip("flip_h")),
            ("Miroir V", lambda: self._toggle_flip("flip_v")),
        ]:
            b = QPushButton(label)
            b.setObjectName("nav")
            b.clicked.connect(slot)
            geo.addWidget(b)
        col.addLayout(geo)

        tools = QHBoxLayout()
        self._crop_btn = QPushButton("Recadrer")
        self._crop_btn.setObjectName("nav")
        self._crop_btn.setCheckable(True)
        self._crop_btn.toggled.connect(self._on_crop_toggled)
        tools.addWidget(self._crop_btn)
        self._spot_btn = QPushButton("Correcteur")
        self._spot_btn.setObjectName("nav")
        self._spot_btn.setCheckable(True)
        self._spot_btn.toggled.connect(self._on_spot_toggled)
        tools.addWidget(self._spot_btn)
        clear_spots = QPushButton("Effacer retouches")
        clear_spots.setObjectName("nav")
        clear_spots.clicked.connect(self._clear_spots)
        tools.addWidget(clear_spots)
        col.addLayout(tools)

        col.addStretch()

        actions = QHBoxLayout()
        auto_btn = QPushButton("Auto")
        auto_btn.clicked.connect(self._apply_auto)
        actions.addWidget(auto_btn)
        reset_btn = QPushButton("Réinitialiser")
        reset_btn.setObjectName("secondary")
        reset_btn.clicked.connect(self._reset)
        actions.addWidget(reset_btn)
        col.addLayout(actions)

        save_row = QHBoxLayout()
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        save_row.addWidget(cancel_btn)
        save_btn = QPushButton("Enregistrer")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        col.addLayout(save_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFixedWidth(320)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

    def _group_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; margin-top: 6px;")
        return lbl

    # --- control factories --------------------------------------------
    def _add_slider(self, layout, key, label, lo, hi, default):
        row = QVBoxLayout()
        row.setSpacing(2)
        head = QHBoxLayout()
        head.addWidget(QLabel(label))
        head.addStretch()
        val_lbl = QLabel(str(default))
        val_lbl.setObjectName("dim")
        head.addWidget(val_lbl)
        row.addLayout(head)
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(default)
        s.valueChanged.connect(lambda v, k=key, lab=val_lbl: self._on_slider(k, v, lab))
        row.addWidget(s)
        layout.addLayout(row)
        self._sliders[key] = s
        self._slider_value_labels[key] = val_lbl

    def _add_check(self, layout, key, label):
        c = QCheckBox(label)
        c.toggled.connect(lambda on, k=key: self._on_check(k, on))
        layout.addWidget(c)
        self._checks[key] = c

    # --- slider/check value mapping -----------------------------------
    @staticmethod
    def _slider_to_value(key: str, raw: int):
        if key in ("brightness", "contrast", "gamma", "saturation", "sharpen"):
            return raw / 100.0
        if key == "clahe":
            return raw / 10.0
        return raw  # temperature, denoise are 1:1

    def _on_slider(self, key: str, raw: int, val_lbl: QLabel):
        val_lbl.setText(str(raw))
        setattr(self._adj, key, self._slider_to_value(key, raw))
        self._schedule_render()

    def _on_check(self, key: str, on: bool):
        setattr(self._adj, key, on)
        self._schedule_render()

    # --- geometry / tools ---------------------------------------------
    def _rotate(self):
        self._adj.rotate = (self._adj.rotate + 90) % 360
        self._schedule_render()

    def _toggle_flip(self, key: str):
        setattr(self._adj, key, not getattr(self._adj, key))
        self._schedule_render()

    def _on_crop_toggled(self, on: bool):
        if on and self._spot_btn.isChecked():
            self._spot_btn.setChecked(False)
        self._preview.set_crop_mode(on)
        self._preview.set_crop_norm(self._adj.crop)
        self._schedule_render()   # crop mode shows the uncropped image + overlay

    def _on_crop_changed(self, box):
        self._adj.crop = box

    def _on_spot_toggled(self, on: bool):
        if on and self._crop_btn.isChecked():
            self._crop_btn.setChecked(False)
        self._preview.set_spot_mode(on)

    def _on_spot_added(self, x: float, y: float):
        self._adj.spots.append((x, y, SPOT_RADIUS))
        self._schedule_render()

    def _clear_spots(self):
        self._adj.spots.clear()
        self._schedule_render()

    # --- auto / reset -------------------------------------------------
    def _apply_auto(self):
        auto = auto_enhance(self._full)
        # carry over geometry/crop/spots the user already set
        auto.rotate, auto.flip_h, auto.flip_v = self._adj.rotate, self._adj.flip_h, self._adj.flip_v
        auto.crop, auto.spots = self._adj.crop, self._adj.spots
        self._adj = auto
        self._sync_controls_from_adj()
        self._schedule_render()

    def _reset(self):
        self._adj = Adjustments()
        self._crop_btn.setChecked(False)
        self._spot_btn.setChecked(False)
        self._sync_controls_from_adj()
        self._preview.set_crop_norm(None)
        self._schedule_render()

    def _sync_controls_from_adj(self):
        """Push current self._adj values back into the widgets without firing
        a render per-widget (signals blocked; one render scheduled by caller).
        Also updates each slider's value label."""
        for key, s in self._sliders.items():
            val = getattr(self._adj, key)
            if key in ("brightness", "contrast", "gamma", "saturation", "sharpen"):
                raw = round(val * 100)
            elif key == "clahe":
                raw = round(val * 10)
            else:  # temperature, denoise
                raw = int(val)
            s.blockSignals(True)
            s.setValue(raw)
            s.blockSignals(False)
            # value label is the widget right before the slider in its row
            lbl = self._slider_value_labels.get(key)
            if lbl:
                lbl.setText(str(raw))
        for key, c in self._checks.items():
            c.blockSignals(True)
            c.setChecked(bool(getattr(self._adj, key)))
            c.blockSignals(False)

    # --- rendering ----------------------------------------------------
    def _schedule_render(self):
        self._render_timer.start()

    def _preview_adjustments(self) -> Adjustments:
        # In crop mode, show the uncropped image so the user can (re)draw the box.
        adj = self._adj.copy()
        if self._crop_btn.isChecked():
            adj.crop = None
        return adj

    def _render_preview(self):
        self._generation += 1
        task = _RenderTask(self._work, self._preview_adjustments(),
                           self._generation, self._render_signals)
        self._pool.start(task)

    def _on_render_done(self, generation: int, qimg: QImage):
        if generation == self._generation:
            self._preview.set_image(qimg)

    # --- save ---------------------------------------------------------
    def _save(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = apply_adjustments(self._full, self._adj)
            self.saved_path = self._media.save_edited(result)
        finally:
            QApplication.restoreOverrideCursor()
        self.accept()
