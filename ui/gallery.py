from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QVBoxLayout,
    QLabel, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThreadPool
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont

from core.media import MediaFile
from core.thumbnail import ThumbnailLoader, THUMB_W, THUMB_H

CARD_W = 192
CARD_H = 172
GRID_COLS = 4
GRID_SPACING = 10


class ThumbnailCard(QFrame):
    clicked = pyqtSignal(object)  # MediaFile

    def __init__(self, media: MediaFile, parent=None):
        super().__init__(parent)
        self.media = media
        self.setObjectName("ThumbnailCard")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(5)

        self.img_label = QLabel()
        self.img_label.setFixedSize(THUMB_W, THUMB_H)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder = QPixmap(THUMB_W, THUMB_H)
        placeholder.fill(QColor("#313244"))
        self.img_label.setPixmap(placeholder)

        date_label = QLabel(media.display_date)
        date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_label.setObjectName("dim")
        date_label.setWordWrap(True)

        layout.addWidget(self.img_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(date_label)

    def set_pixmap(self, pixmap: QPixmap):
        if self.media.is_video:
            overlay = QPixmap(pixmap.size())
            overlay.fill(Qt.GlobalColor.transparent)
            p = QPainter(overlay)
            p.drawPixmap(0, 0, pixmap)
            p.fillRect(overlay.rect(), QColor(0, 0, 0, 70))
            p.setPen(QColor("#94E2D5"))
            f = QFont()
            f.setPointSize(18)
            p.setFont(f)
            p.drawText(overlay.rect(), Qt.AlignmentFlag.AlignCenter, "▶")
            p.end()
            self.img_label.setPixmap(overlay)
        else:
            self.img_label.setPixmap(pixmap)

    def set_selected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.media)


class GalleryWidget(QWidget):
    media_selected = pyqtSignal(object)  # MediaFile

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, ThumbnailCard] = {}
        self._selected: ThumbnailCard | None = None
        self._pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(GRID_SPACING)
        self._grid.setContentsMargins(10, 10, 10, 10)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_widget)

        layout.addWidget(scroll)

    def load_files(self, media_files: list[MediaFile]):
        for card in self._cards.values():
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected = None

        for i, mf in enumerate(media_files):
            card = ThumbnailCard(mf)
            card.clicked.connect(self._on_card_clicked)
            row, col = divmod(i, GRID_COLS)
            self._grid.addWidget(card, row, col)
            self._cards[str(mf.path)] = card

            loader = ThumbnailLoader(mf.path, preview=False)
            loader.signals.ready.connect(self._on_thumb_ready)
            self._pool.start(loader)

    def _on_thumb_ready(self, path_str: str, pixmap: QPixmap):
        card = self._cards.get(path_str)
        if card:
            card.set_pixmap(pixmap)

    def _on_card_clicked(self, media: MediaFile):
        if self._selected:
            self._selected.set_selected(False)
        card = self._cards.get(str(media.path))
        if card:
            card.set_selected(True)
            self._selected = card
        self.media_selected.emit(media)

    def update_card_path(self, old_path: Path, new_path: Path):
        card = self._cards.pop(str(old_path), None)
        if card:
            self._cards[str(new_path)] = card
