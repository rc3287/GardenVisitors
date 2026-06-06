from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
    QRadioButton, QButtonGroup, QGroupBox, QPushButton, QSlider,
    QDialog, QLineEdit, QDialogButtonBox, QDateTimeEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QDateTime, QDate, QTime
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from core.media import MediaFile, ANIMALS, QUALITY_VALUES, QUALITY_LABELS


class AddAnimalDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter un animal")
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Nom de l'animal :"))
        self._input = QLineEdit()
        self._input.setPlaceholderText("ex: lapin")
        layout.addWidget(self._input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._input.returnPressed.connect(self.accept)

    def animal_name(self) -> str:
        return self._input.text().strip().lower()


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
        self._player.play()

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
    rename_requested = pyqtSignal(object, str)  # MediaFile, new_filename
    delete_requested = pyqtSignal(object)             # MediaFile
    prev_requested = pyqtSignal()
    next_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._media: MediaFile | None = None
        self._animal_names: list[str] = list(ANIMALS)
        self._loading = False
        self._last_animal_id: int | None = None
        self._last_quality_id: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Navigation + stacked preview
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)

        self._prev_btn = QPushButton("←")
        self._prev_btn.setObjectName("nav")
        self._prev_btn.setFixedWidth(36)
        self._prev_btn.clicked.connect(self.prev_requested)
        nav_row.addWidget(self._prev_btn)

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
        nav_row.addWidget(self._stack, stretch=1)

        self._next_btn = QPushButton("→")
        self._next_btn.setObjectName("nav")
        self._next_btn.setFixedWidth(36)
        self._next_btn.clicked.connect(self.next_requested)
        nav_row.addWidget(self._next_btn)

        root.addLayout(nav_row, stretch=1)

        # Date / time (editable)
        dt_row = QHBoxLayout()
        dt_row.addWidget(QLabel("Date / Heure :"))
        self._datetime_edit = QDateTimeEdit()
        self._datetime_edit.setDisplayFormat("dd/MM/yyyy  HH:mm:ss")
        self._datetime_edit.setCalendarPopup(True)
        self._datetime_edit.setEnabled(False)
        self._datetime_edit.dateTimeChanged.connect(self._on_datetime_changed)
        dt_row.addWidget(self._datetime_edit, stretch=1)
        root.addLayout(dt_row)

        # Animal selection
        animal_box = QGroupBox("Animal")
        self._animal_layout = QHBoxLayout(animal_box)
        self._animal_layout.setSpacing(6)
        self._animal_group = QButtonGroup(self)
        for i, name in enumerate(self._animal_names):
            rb = QRadioButton(name)
            self._animal_group.addButton(rb, i)
            self._animal_layout.addWidget(rb)

        add_animal_btn = QPushButton("+")
        add_animal_btn.setObjectName("nav")
        add_animal_btn.setFixedSize(28, 28)
        add_animal_btn.setToolTip("Ajouter un animal")
        add_animal_btn.clicked.connect(self._add_animal)
        self._animal_layout.addWidget(add_animal_btn)
        self._animal_layout.addStretch()
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

        # Current filename (read-only)
        cur_row = QHBoxLayout()
        cur_lbl = QLabel("Actuel :")
        cur_lbl.setObjectName("dim")
        cur_lbl.setFixedWidth(62)
        self._current_name_label = QLabel()
        self._current_name_label.setObjectName("dim")
        self._current_name_label.setWordWrap(True)
        cur_row.addWidget(cur_lbl)
        cur_row.addWidget(self._current_name_label, stretch=1)
        root.addLayout(cur_row)

        # Proposed filename (editable)
        prop_row = QHBoxLayout()
        prop_lbl = QLabel("Nouveau :")
        prop_lbl.setFixedWidth(62)
        self._proposed_edit = QLineEdit()
        self._proposed_edit.setPlaceholderText("Sélectionnez animal et qualité…")
        self._proposed_edit.textChanged.connect(self._on_proposed_changed)
        prop_row.addWidget(prop_lbl)
        prop_row.addWidget(self._proposed_edit, stretch=1)
        root.addLayout(prop_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self.rename_btn = QPushButton("Renommer")
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(self.rename_btn)

        btn_row.addStretch()

        self.delete_btn = QPushButton("Rejeter")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self.delete_btn)

        root.addLayout(btn_row)

        self._animal_group.idClicked.connect(self._update_new_name)
        self._quality_group.idClicked.connect(self._update_new_name)

    # ------------------------------------------------------------------
    def load_media(self, media: MediaFile, pixmap: QPixmap | None = None):
        # Persist selections from the previous file
        prev_animal = self._animal_group.checkedId()
        prev_quality = self._quality_group.checkedId()
        if prev_animal >= 0:
            self._last_animal_id = prev_animal
        if prev_quality >= 0:
            self._last_quality_id = prev_quality

        self._media = media

        self._loading = True
        if media.datetime_obj:
            dt = media.datetime_obj
        else:
            dt = datetime.now()
            media.datetime_obj = dt
        qdt = QDateTime(
            QDate(dt.year, dt.month, dt.day),
            QTime(dt.hour, dt.minute, dt.second),
        )
        self._datetime_edit.setDateTime(qdt)
        self._datetime_edit.setEnabled(True)
        self._loading = False

        self._animal_group.setExclusive(False)
        for b in self._animal_group.buttons():
            b.setChecked(False)
        if self._last_animal_id is not None:
            btn = self._animal_group.button(self._last_animal_id)
            if btn:
                btn.setChecked(True)
        self._animal_group.setExclusive(True)

        self._quality_group.setExclusive(False)
        for b in self._quality_group.buttons():
            b.setChecked(False)
        if self._last_quality_id is not None:
            btn = self._quality_group.button(self._last_quality_id)
            if btn:
                btn.setChecked(True)
        self._quality_group.setExclusive(True)

        self._current_name_label.setText(media.path.name)
        self._proposed_edit.clear()   # textChanged → rename_btn disabled
        self.delete_btn.setEnabled(True)
        self._update_new_name(0)  # fills proposed_edit if selections are restored

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

    # ------------------------------------------------------------------
    def _on_datetime_changed(self, qdt: QDateTime):
        if self._loading or not self._media:
            return
        d = qdt.date()
        t = qdt.time()
        self._media.datetime_obj = datetime(
            d.year(), d.month(), d.day(),
            t.hour(), t.minute(), t.second(),
        )
        self._update_new_name(0)

    def _add_animal(self):
        dialog = AddAnimalDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = dialog.animal_name()
            if not name or name in self._animal_names:
                return
            self._animal_names.append(name)
            rb = QRadioButton(name)
            new_id = len(self._animal_names) - 1
            self._animal_group.addButton(rb, new_id)
            # Insert before the "+" button and stretch (last 2 items)
            self._animal_layout.insertWidget(self._animal_layout.count() - 2, rb)
            rb.setChecked(True)
            self._update_new_name(new_id)

    def _on_proposed_changed(self, text: str):
        self.rename_btn.setEnabled(bool(text.strip()) and self._media is not None)

    def _update_new_name(self, _id: int):
        if not self._media:
            return
        a_btn = self._animal_group.checkedButton()
        q_btn = self._quality_group.checkedButton()
        if a_btn and q_btn:
            animal = self._animal_names[self._animal_group.id(a_btn)]
            quality = QUALITY_VALUES[self._quality_group.id(q_btn)]
            self._proposed_edit.setText(self._media.build_unique_name(animal, quality))
            # rename_btn state handled by _on_proposed_changed via textChanged

    def _on_rename(self):
        if not self._media:
            return
        new_name = self._proposed_edit.text().strip()
        if not new_name:
            return
        self._vid_preview.stop()
        self.rename_requested.emit(self._media, new_name)

    def _on_delete(self):
        if not self._media:
            return
        self._vid_preview.stop()
        self.delete_requested.emit(self._media)

    def clear(self):
        self._media = None
        self._vid_preview.stop()
        self._stack.setCurrentIndex(0)
        self._img_preview.set_source(None)
        self._img_preview.setText("Sélectionnez un fichier")
        self._datetime_edit.setEnabled(False)
        self._current_name_label.clear()
        self._proposed_edit.clear()   # textChanged → rename_btn disabled
        self.delete_btn.setEnabled(False)
        self._animal_group.setExclusive(False)
        for b in self._animal_group.buttons():
            b.setChecked(False)
        self._animal_group.setExclusive(True)
        self._quality_group.setExclusive(False)
        for b in self._quality_group.buttons():
            b.setChecked(False)
        self._quality_group.setExclusive(True)
