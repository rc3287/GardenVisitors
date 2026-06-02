from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QButtonGroup, QGroupBox, QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from core.media import MediaFile, ANIMALS, QUALITY_VALUES, QUALITY_LABELS


class ScaledPreview(QLabel):
    """QLabel that scales its pixmap to fill available space while keeping aspect ratio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source: QPixmap | None = None

    def set_source(self, pixmap: QPixmap | None):
        self._source = pixmap
        self._refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        if self._source and not self._source.isNull():
            scaled = self._source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)
        else:
            self.setPixmap(QPixmap())


class TagPanel(QWidget):
    rename_requested = pyqtSignal(object, str, str)  # MediaFile, animal, quality

    def __init__(self, parent=None):
        super().__init__(parent)
        self._media: MediaFile | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Preview
        self.preview = ScaledPreview()
        self.preview.setMinimumHeight(280)
        self.preview.setStyleSheet(
            "background-color: #181825; border-radius: 12px; color: #585B70; font-size: 15px;"
        )
        self.preview.setText("Sélectionnez un fichier")
        root.addWidget(self.preview, stretch=1)

        # Date label
        self.date_label = QLabel()
        self.date_label.setObjectName("dim")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.date_label)

        # Animal selection
        animal_box = QGroupBox("Animal")
        animal_layout = QHBoxLayout(animal_box)
        animal_layout.setSpacing(6)
        self._animal_group = QButtonGroup(self)
        for i, name in enumerate(ANIMALS):
            rb = QRadioButton(name)
            self._animal_group.addButton(rb, i)
            animal_layout.addWidget(rb)
        animal_layout.addStretch()
        root.addWidget(animal_box)

        # Quality selection
        quality_box = QGroupBox("Qualité")
        quality_layout = QHBoxLayout(quality_box)
        quality_layout.setSpacing(6)
        self._quality_group = QButtonGroup(self)
        for i, label in enumerate(QUALITY_LABELS):
            rb = QRadioButton(label)
            self._quality_group.addButton(rb, i)
            quality_layout.addWidget(rb)
        quality_layout.addStretch()
        root.addWidget(quality_box)

        # New name preview
        self.new_name_label = QLabel()
        self.new_name_label.setObjectName("accent")
        self.new_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.new_name_label.setWordWrap(True)
        root.addWidget(self.new_name_label)

        # Action buttons
        btn_row = QHBoxLayout()
        self.open_btn = QPushButton("Ouvrir")
        self.open_btn.setObjectName("secondary")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._on_open)
        self.rename_btn = QPushButton("Renommer")
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.open_btn)
        btn_row.addWidget(self.rename_btn)
        root.addLayout(btn_row)

        self._animal_group.idClicked.connect(self._update_new_name)
        self._quality_group.idClicked.connect(self._update_new_name)

    def load_media(self, media: MediaFile, pixmap: QPixmap | None = None):
        self._media = media
        self.date_label.setText(media.display_date)
        self.open_btn.setEnabled(True)

        # Reset radio selections without triggering callbacks
        self._animal_group.setExclusive(False)
        for b in self._animal_group.buttons():
            b.setChecked(False)
        self._animal_group.setExclusive(True)

        self._quality_group.setExclusive(False)
        for b in self._quality_group.buttons():
            b.setChecked(False)
        self._quality_group.setExclusive(True)

        self.new_name_label.setText(f"Fichier actuel : {media.path.name}")
        self.rename_btn.setEnabled(False)

        if pixmap and not pixmap.isNull():
            self.preview.set_source(pixmap)
            self.preview.setText("")
        else:
            self.preview.set_source(None)
            self.preview.setText("▶ Vidéo" if media.is_video else "Chargement…")

    def update_preview_pixmap(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self.preview.set_source(pixmap)
            self.preview.setText("")

    def _update_new_name(self, _id: int):
        if not self._media:
            return
        a_btn = self._animal_group.checkedButton()
        q_btn = self._quality_group.checkedButton()
        if a_btn and q_btn:
            animal = ANIMALS[self._animal_group.id(a_btn)]
            quality = QUALITY_VALUES[self._quality_group.id(q_btn)]
            self.new_name_label.setText(
                f"→ {self._media.build_new_name(animal, quality)}"
            )
            self.rename_btn.setEnabled(True)
        else:
            self.rename_btn.setEnabled(False)

    def _on_rename(self):
        if not self._media:
            return
        a_btn = self._animal_group.checkedButton()
        q_btn = self._quality_group.checkedButton()
        if not a_btn or not q_btn:
            return
        animal = ANIMALS[self._animal_group.id(a_btn)]
        quality = QUALITY_VALUES[self._quality_group.id(q_btn)]
        self.rename_requested.emit(self._media, animal, quality)

    def _on_open(self):
        if not self._media:
            return
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._media.path)))
