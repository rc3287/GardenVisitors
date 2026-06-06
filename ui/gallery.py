from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QRadioButton, QButtonGroup,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThreadPool
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont

from core.media import MediaFile
from core.thumbnail import ThumbnailLoader, THUMB_W, THUMB_H

CARD_W = 192
CARD_H = 172
GRID_SPACING = 10

_FILTER_ALL = 0
_FILTER_RENAMED = 1
_FILTER_UNREVIEWED = 2


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
        self._all_media_files: list[MediaFile] = []
        self._media_files: list[MediaFile] = []
        self._pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Filter bar
        filter_bar = QWidget()
        filter_bar.setObjectName("FilterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(10, 6, 10, 6)
        filter_layout.setSpacing(12)

        filter_layout.addWidget(QLabel("Afficher :"))
        self._filter_group = QButtonGroup(self)
        for fid, label in [
            (_FILTER_ALL, "Tous"),
            (_FILTER_RENAMED, "Renommés"),
            (_FILTER_UNREVIEWED, "Non revus"),
        ]:
            rb = QRadioButton(label)
            self._filter_group.addButton(rb, fid)
            filter_layout.addWidget(rb)
        self._filter_group.button(_FILTER_ALL).setChecked(True)
        filter_layout.addStretch()
        layout.addWidget(filter_bar)

        self._filter_group.idClicked.connect(lambda _: self._apply_filter())

        # Scrollable grid
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(GRID_SPACING)
        self._grid.setContentsMargins(10, 10, 10, 10)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._grid_widget)

        layout.addWidget(self._scroll)

    # ------------------------------------------------------------------
    @property
    def visible_media(self) -> list[MediaFile]:
        return list(self._media_files)

    def _cols(self) -> int:
        available = self._scroll.viewport().width() - 20
        cols = max(1, available // (CARD_W + GRID_SPACING))
        return cols

    def _rebuild_grid(self):
        visible_keys = {str(mf.path) for mf in self._media_files}
        for key, card in self._cards.items():
            self._grid.removeWidget(card)
            if key in visible_keys:
                card.show()
            else:
                card.hide()
        cols = self._cols()
        for i, mf in enumerate(self._media_files):
            card = self._cards.get(str(mf.path))
            if card:
                row, col = divmod(i, cols)
                self._grid.addWidget(card, row, col)

    def _apply_filter(self):
        fid = self._filter_group.checkedId()
        if fid == _FILTER_RENAMED:
            self._media_files = [m for m in self._all_media_files if m.is_renamed]
        elif fid == _FILTER_UNREVIEWED:
            self._media_files = [m for m in self._all_media_files if not m.is_renamed]
        else:
            self._media_files = list(self._all_media_files)
        self._rebuild_grid()

    def refresh_filter(self):
        self._apply_filter()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_grid()

    # ------------------------------------------------------------------
    def load_files(self, media_files: list[MediaFile]):
        for card in self._cards.values():
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected = None
        self._all_media_files = media_files
        self._media_files = list(media_files)
        self._filter_group.button(_FILTER_ALL).setChecked(True)

        cols = self._cols()
        for i, mf in enumerate(media_files):
            card = ThumbnailCard(mf)
            card.clicked.connect(self._on_card_clicked)
            row, col = divmod(i, cols)
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

    def select_media(self, media: MediaFile):
        self._on_card_clicked(media)

    def remove_media(self, path: Path):
        key = str(path)
        card = self._cards.pop(key, None)
        if card:
            self._grid.removeWidget(card)
            card.deleteLater()
            if self._selected is card:
                self._selected = None
        self._all_media_files = [m for m in self._all_media_files if str(m.path) != key]
        self._media_files = [m for m in self._media_files if str(m.path) != key]
        self._rebuild_grid()

    def update_card_path(self, old_path: Path, new_path: Path):
        card = self._cards.pop(str(old_path), None)
        if card:
            self._cards[str(new_path)] = card
