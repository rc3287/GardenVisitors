from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QRadioButton, QButtonGroup, QGroupBox, QPushButton, QSlider,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.media import MediaFile, ANIMALS, QUALITY_VALUES, QUALITY_LABELS


class ScaledPreview(QLabel):
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


class VideoPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._video = QVideoWidget()
        self._video.setStyleSheet("background-color: #000000; border-radius: 8px;")
        layout.addWidget(self._video, stretch=1)

        controls = QHBoxLayout()
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedWidth(40)
        self._play_btn.clicked.connect(self._toggle_play)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.sliderMoved.connect(self._seek)

        self._time_label = QLabel("0:00")
        self._time_label.setObjectName("dim")
        self._time_label.setFixedWidth(40)

        controls.addWidget(self._play_btn)
        controls.addWidget(self._slider, stretch=1)
        controls.addWidget(self._time_label)
        layout.addLayout(controls)

        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)

        self._duration = 0

    def load(self, path):
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._play_btn.setText("▶")
        self._slider.setValue(0)
        self._time_label.setText("0:00")

    def stop(self):
        self._player.stop()
        self._player.setSource(QUrl())  # release the file handle

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _seek(self, value: int):
        if self._duration:
            self._player.setPosition(int(value * self._duration / 1000))

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    def _on_position(self, ms: int):
        if self._duration:
            self._slider.setValue(int(ms * 1000 / self._duration))
        secs = ms // 1000
        self._time_label.setText(f"{secs // 60}:{secs % 60:02d}")

    def _on_duration(self, ms: int):
        self._duration = ms


class TagPanel(QWidget):
    rename_requested = pyqtSignal(object, str, str)  # MediaFile, animal, quality

    def __init__(self, parent=None):
        super().__init__(parent)
        self._media: MediaFile | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Stacked preview: page 0 = image, page 1 = video
        self._stack = QStackedWidget()
        self._stack.setMinimumHeight(280)

        self._img_preview = ScaledPreview()
        self._img_preview.setStyleSheet(
            "background-color: #181825; border-radius: 12px; color: #585B70; font-size: 15px;"
        )
        self._img_preview.setText("Sélectionnez un fichier")

        self._vid_preview = VideoPreview()

        self._stack.addWidget(self._img_preview)   # index 0
        self._stack.addWidget(self._vid_preview)   # index 1
        root.addWidget(self._stack, stretch=1)

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
        self.rename_btn = QPushButton("Renommer")
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.rename_btn)
        root.addLayout(btn_row)

        self._animal_group.idClicked.connect(self._update_new_name)
        self._quality_group.idClicked.connect(self._update_new_name)

    def load_media(self, media: MediaFile, pixmap: QPixmap | None = None):
        self._media = media
        self.date_label.setText(media.display_date)

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

        if media.is_video:
            self._vid_preview.load(media.path)
            self._stack.setCurrentIndex(1)
        else:
            self._vid_preview.stop()
            self._stack.setCurrentIndex(0)
            if pixmap and not pixmap.isNull():
                self._img_preview.set_source(pixmap)
                self._img_preview.setText("")
            else:
                self._img_preview.set_source(None)
                self._img_preview.setText("Chargement…")

    def update_preview_pixmap(self, pixmap: QPixmap):
        if self._media and not self._media.is_video and pixmap and not pixmap.isNull():
            self._img_preview.set_source(pixmap)
            self._img_preview.setText("")

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
        # Release any open file handle before renaming
        self._vid_preview.stop()
        animal = ANIMALS[self._animal_group.id(a_btn)]
        quality = QUALITY_VALUES[self._quality_group.id(q_btn)]
        self.rename_requested.emit(self._media, animal, quality)
