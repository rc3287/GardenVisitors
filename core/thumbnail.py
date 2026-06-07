import hashlib
import os
from pathlib import Path
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QPixmap, QImage

try:
    from PIL import Image as PILImage, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

THUMB_W = 160
THUMB_H = 120
PREVIEW_MAX = 1200


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "GardenVisitors" / "thumbs"


def _cache_key(path: Path) -> str | None:
    """Hash of the absolute path + mtime — naturally invalidates when the file changes."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    raw = f"{path.resolve()}|{mtime}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class ThumbnailSignals(QObject):
    ready = pyqtSignal(str, QPixmap)
    failed = pyqtSignal(str)


class ThumbnailLoader(QRunnable):
    def __init__(self, path: Path, preview: bool = False):
        super().__init__()
        self.path = path
        self.preview = preview
        self.signals = ThumbnailSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        try:
            if not self.preview:
                cached = self._load_from_cache()
                if cached is not None:
                    self.signals.ready.emit(str(self.path), cached)
                    return

            suffix = self.path.suffix.upper()
            if suffix in (".JPG", ".JPEG", ".PNG", ".BMP"):
                pixmap = self._load_image()
            else:
                pixmap = self._load_video_frame()

            if pixmap and not pixmap.isNull():
                if not self.preview:
                    self._save_to_cache(pixmap)
                self.signals.ready.emit(str(self.path), pixmap)
                return
        except Exception:
            pass
        self.signals.failed.emit(str(self.path))

    # --- Disk cache for gallery thumbnails (not used for big previews) --
    def _load_from_cache(self) -> QPixmap | None:
        key = _cache_key(self.path)
        if key is None:
            return None
        cache_path = _cache_dir() / f"{key}.png"
        if not cache_path.exists():
            return None
        pix = QPixmap(str(cache_path))
        return pix if not pix.isNull() else None

    def _save_to_cache(self, pixmap: QPixmap):
        key = _cache_key(self.path)
        if key is None:
            return
        try:
            cache_dir = _cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            pixmap.save(str(cache_dir / f"{key}.png"), "PNG")
        except OSError:
            pass

    # --------------------------------------------------------------------
    def _scale(self, pix: QPixmap) -> QPixmap:
        if self.preview:
            return pix.scaled(
                PREVIEW_MAX, PREVIEW_MAX,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pix.scaled(
            THUMB_W, THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _load_image(self) -> QPixmap:
        pix = self._load_image_oriented()
        if pix is None:
            pix = QPixmap(str(self.path))
        if pix.isNull():
            return QPixmap()
        return self._scale(pix)

    def _load_image_oriented(self) -> QPixmap | None:
        """Load via Pillow and apply EXIF orientation (tag 274) so portrait /
        rotated photos display upright. Returns None to fall back to a plain
        QPixmap load (PIL unavailable, or the file isn't a Pillow-readable image)."""
        if not PIL_AVAILABLE:
            return None
        try:
            with PILImage.open(self.path) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                w, h = img.size
                data = img.tobytes("raw", "RGB")
                qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
                return QPixmap.fromImage(qimg)
        except Exception:
            return None

    def _load_video_frame(self) -> QPixmap:
        try:
            import cv2
        except ImportError:
            return QPixmap()
        cap = cv2.VideoCapture(str(self.path))
        # Trail-cam first frames are frequently black — seek ~1s in for a
        # representative frame, falling back to frame 0 if that fails.
        cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()
        if not ret:
            return QPixmap()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img)
        return self._scale(pix)
