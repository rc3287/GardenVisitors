from pathlib import Path
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QPixmap, QImage

THUMB_W = 160
THUMB_H = 120
PREVIEW_MAX = 1200


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
            suffix = self.path.suffix.upper()
            if suffix in (".JPG", ".JPEG", ".PNG", ".BMP"):
                pixmap = self._load_image()
            else:
                pixmap = self._load_video_frame()

            if pixmap and not pixmap.isNull():
                self.signals.ready.emit(str(self.path), pixmap)
                return
        except Exception:
            pass
        self.signals.failed.emit(str(self.path))

    def _load_image(self) -> QPixmap:
        pix = QPixmap(str(self.path))
        if pix.isNull():
            return QPixmap()
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

    def _load_video_frame(self) -> QPixmap:
        try:
            import cv2
        except ImportError:
            return QPixmap()
        cap = cv2.VideoCapture(str(self.path))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return QPixmap()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img)
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
