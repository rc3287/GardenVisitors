from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QRadioButton, QButtonGroup, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThreadPool, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont

from core.media import MediaFile
from core.thumbnail import ThumbnailLoader, THUMB_W, THUMB_H

CARD_W = 192
CARD_H = 172
GRID_SPACING = 10

_FILTER_ALL = 0
_FILTER_UNREVIEWED = 1
_FILTER_DONE = 2
_FILTER_TO_DELETE = 3
_FILTER_EDITED = 4


class ThumbnailCard(QFrame):
    clicked = pyqtSignal(object, bool)  # MediaFile, ctrl_held

    def __init__(self, media: MediaFile, parent=None):
        super().__init__(parent)
        self.media = media
        self.setObjectName("ThumbnailCard")
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)
        self.setProperty("marked", False)

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

    def set_marked(self, marked: bool):
        self.setProperty("marked", marked)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl_held = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.clicked.emit(self.media, ctrl_held)


class GalleryWidget(QWidget):
    media_selected = pyqtSignal(object)  # MediaFile
    batch_reject_requested = pyqtSignal(list)  # list[MediaFile]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, ThumbnailCard] = {}
        self._selected: ThumbnailCard | None = None
        self._marked: dict[str, MediaFile] = {}
        self._all_media_files: list[MediaFile] = []
        self._media_files: list[MediaFile] = []
        self._thumb_requested: set[str] = set()
        self._pool = QThreadPool.globalInstance()
        self._last_cols = 0

        # Resizing fires resizeEvent on every pixel of a window drag — debounce
        # the (relatively expensive) grid rebuild until the resize settles.
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(100)
        self._resize_timer.timeout.connect(self._on_resize_settled)

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
            (_FILTER_UNREVIEWED, "Non revus"),
            (_FILTER_DONE, "Traités"),
            (_FILTER_EDITED, "Édités"),
            (_FILTER_TO_DELETE, "À effacer"),
            (_FILTER_ALL, "Tous"),
        ]:
            rb = QRadioButton(label)
            self._filter_group.addButton(rb, fid)
            filter_layout.addWidget(rb)
        self._filter_group.button(_FILTER_UNREVIEWED).setChecked(True)
        filter_layout.addStretch()
        layout.addWidget(filter_bar)

        self._filter_group.idClicked.connect(lambda _: self._apply_filter())
        self._update_filter_counts()

        # Multi-selection bar (shown only when files are marked via Ctrl+clic)
        self._selection_bar = QWidget()
        self._selection_bar.setObjectName("SelectionBar")
        sel_layout = QHBoxLayout(self._selection_bar)
        sel_layout.setContentsMargins(10, 6, 10, 6)
        sel_layout.setSpacing(12)

        self._selection_label = QLabel("")
        sel_layout.addWidget(self._selection_label)
        sel_layout.addStretch()

        clear_btn = QPushButton("Désélectionner")
        clear_btn.setObjectName("secondary")
        clear_btn.clicked.connect(self.clear_marked)
        sel_layout.addWidget(clear_btn)

        reject_btn = QPushButton("Rejeter la sélection")
        reject_btn.setObjectName("danger")
        reject_btn.clicked.connect(self._on_reject_selection_clicked)
        sel_layout.addWidget(reject_btn)

        self._selection_bar.hide()
        layout.addWidget(self._selection_bar)

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
        self._scroll.verticalScrollBar().valueChanged.connect(lambda _: self._load_visible_thumbnails())

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
        self._last_cols = cols
        for i, mf in enumerate(self._media_files):
            card = self._cards.get(str(mf.path))
            if card:
                row, col = divmod(i, cols)
                self._grid.addWidget(card, row, col)
        self._load_visible_thumbnails()

    def _load_visible_thumbnails(self):
        """Start thumbnail loaders only for cards currently within (or near) the
        scroll viewport, instead of every file at once — keeps startup fast on
        large folders. Called after every grid rebuild and on scroll."""
        if not self._media_files:
            return
        cols = self._cols()
        row_h = CARD_H + GRID_SPACING
        scroll_y = self._scroll.verticalScrollBar().value()
        viewport_h = self._scroll.viewport().height()
        first_row = max(0, scroll_y // row_h - 1)
        last_row = (scroll_y + viewport_h) // row_h + 1
        first_idx = first_row * cols
        last_idx = (last_row + 1) * cols

        for i, mf in enumerate(self._media_files):
            if i < first_idx:
                continue
            if i > last_idx:
                break
            key = str(mf.path)
            if key in self._thumb_requested:
                continue
            self._thumb_requested.add(key)
            loader = ThumbnailLoader(mf.path, preview=False)
            loader.signals.ready.connect(self._on_thumb_ready)
            self._pool.start(loader)

    def _apply_filter(self):
        fid = self._filter_group.checkedId()
        tag = {
            _FILTER_UNREVIEWED: "new",
            _FILTER_DONE: "done",
            _FILTER_TO_DELETE: "toDelete",
            _FILTER_EDITED: "edited",
        }.get(fid)
        if tag is not None:
            self._media_files = [m for m in self._all_media_files if m.folder_tag == tag]
        else:
            self._media_files = list(self._all_media_files)
        self._rebuild_grid()

    def _update_filter_counts(self):
        counts = {"new": 0, "done": 0, "toDelete": 0, "edited": 0}
        for m in self._all_media_files:
            if m.folder_tag in counts:
                counts[m.folder_tag] += 1
        self._filter_group.button(_FILTER_UNREVIEWED).setText(f"Non revus ({counts['new']})")
        self._filter_group.button(_FILTER_DONE).setText(f"Traités ({counts['done']})")
        self._filter_group.button(_FILTER_EDITED).setText(f"Édités ({counts['edited']})")
        self._filter_group.button(_FILTER_TO_DELETE).setText(f"À effacer ({counts['toDelete']})")
        self._filter_group.button(_FILTER_ALL).setText(f"Tous ({len(self._all_media_files)})")

    def refresh_filter(self):
        self._update_filter_counts()
        self._apply_filter()

    def show_filter(self, tag: str):
        """Switch the visible filter to a folder tag ('new'/'done'/'toDelete'/
        'edited') or 'all'. Used e.g. to reveal a freshly edited image."""
        fid = {
            "new": _FILTER_UNREVIEWED, "done": _FILTER_DONE,
            "toDelete": _FILTER_TO_DELETE, "edited": _FILTER_EDITED,
            "all": _FILTER_ALL,
        }.get(tag, _FILTER_ALL)
        self._filter_group.button(fid).setChecked(True)
        self._apply_filter()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def _on_resize_settled(self):
        # TODO: for very large folders, the scalable fix is to virtualize the
        # grid (QListView/IconMode + model) so only visible rows materialize.
        if self._cols() == self._last_cols:
            # Column count unchanged — the layout already reflows on its own;
            # just make sure newly-visible cards still get their thumbnails.
            self._load_visible_thumbnails()
            return
        self._rebuild_grid()

    # ------------------------------------------------------------------
    def load_files(self, media_files: list[MediaFile]):
        for card in self._cards.values():
            self._grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected = None
        self._marked.clear()
        self._update_selection_bar()
        self._thumb_requested.clear()
        self._all_media_files = media_files
        self._update_filter_counts()

        # If nothing lives in a managed subfolder (new/done/toDelete), "Non revus"
        # would show an empty grid even though files exist — default to "Tous" instead.
        managed_present = any(mf.folder_tag != "other" for mf in media_files)
        default_filter = _FILTER_UNREVIEWED if managed_present else _FILTER_ALL
        self._filter_group.button(default_filter).setChecked(True)

        for mf in media_files:
            card = ThumbnailCard(mf)
            card.clicked.connect(self._on_card_clicked)
            self._cards[str(mf.path)] = card

        # Thumbnails are loaded lazily for visible cards only (see _load_visible_thumbnails),
        # triggered by _apply_filter -> _rebuild_grid below — keeps startup fast on large folders.
        self._apply_filter()

    def _on_thumb_ready(self, path_str: str, pixmap: QPixmap):
        card = self._cards.get(path_str)
        if card:
            card.set_pixmap(pixmap)

    def _on_card_clicked(self, media: MediaFile, ctrl_held: bool = False):
        if ctrl_held:
            self._toggle_marked(media)
            return
        if self._selected:
            self._selected.set_selected(False)
        card = self._cards.get(str(media.path))
        if card:
            card.set_selected(True)
            self._selected = card
        self.media_selected.emit(media)

    def select_media(self, media: MediaFile):
        self._on_card_clicked(media)

    # --- Multi-selection (Ctrl+clic) for batch rejection ----------------
    def _toggle_marked(self, media: MediaFile):
        key = str(media.path)
        card = self._cards.get(key)
        if not card:
            return
        if key in self._marked:
            del self._marked[key]
            card.set_marked(False)
        else:
            self._marked[key] = media
            card.set_marked(True)
        self._update_selection_bar()

    def clear_marked(self):
        for key in list(self._marked):
            card = self._cards.get(key)
            if card:
                card.set_marked(False)
        self._marked.clear()
        self._update_selection_bar()

    def _update_selection_bar(self):
        count = len(self._marked)
        if count:
            self._selection_label.setText(
                f"{count} fichier{'s' if count != 1 else ''} sélectionné{'s' if count != 1 else ''}"
            )
            self._selection_bar.show()
        else:
            self._selection_bar.hide()

    def _on_reject_selection_clicked(self):
        if self._marked:
            self.batch_reject_requested.emit(list(self._marked.values()))

    def remove_media(self, path: Path):
        key = str(path)
        card = self._cards.pop(key, None)
        if card:
            self._grid.removeWidget(card)
            card.deleteLater()
            if self._selected is card:
                self._selected = None
        if self._marked.pop(key, None) is not None:
            self._update_selection_bar()
        self._thumb_requested.discard(key)
        self._all_media_files = [m for m in self._all_media_files if str(m.path) != key]
        self._media_files = [m for m in self._media_files if str(m.path) != key]
        self._update_filter_counts()
        self._rebuild_grid()

    def update_card_path(self, old_path: Path, new_path: Path):
        old_key, new_key = str(old_path), str(new_path)
        card = self._cards.pop(old_key, None)
        if card:
            self._cards[new_key] = card
        marked_media = self._marked.pop(old_key, None)
        if marked_media is not None:
            self._marked[new_key] = marked_media
        if old_key in self._thumb_requested:
            self._thumb_requested.discard(old_key)
            self._thumb_requested.add(new_key)
