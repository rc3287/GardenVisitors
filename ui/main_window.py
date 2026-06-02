from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QFileDialog, QStatusBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QAction, QPixmap

from core.media import MediaFile, scan_folder
from core.thumbnail import ThumbnailLoader
from ui.gallery import GalleryWidget
from ui.tag_panel import TagPanel
from ui import themes

DEFAULT_FOLDER = Path(r"C:\Users\Renau\OneDrive\Caméra jardin")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GardenVisitors")
        self.resize(1300, 820)
        self._theme = "dark"
        self._media: list[MediaFile] = []
        self._current: MediaFile | None = None
        self._preview_cache: dict[str, QPixmap] = {}
        self._pool = QThreadPool.globalInstance()

        self._build_ui()
        self._build_menu()
        self._apply_theme()

        if DEFAULT_FOLDER.exists():
            self._load_folder(DEFAULT_FOLDER)

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)

        self.gallery = GalleryWidget()
        self.gallery.media_selected.connect(self._on_select)
        self._splitter.addWidget(self.gallery)

        self.tag_panel = TagPanel()
        self.tag_panel.rename_requested.connect(self._on_rename)
        self._splitter.addWidget(self.tag_panel)

        self._splitter.setSizes([460, 840])
        layout.addWidget(self._splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)

    def _build_menu(self):
        mb = self.menuBar()

        file_m = mb.addMenu("Fichier")
        open_a = QAction("Ouvrir dossier…", self)
        open_a.setShortcut("Ctrl+O")
        open_a.triggered.connect(self._open_dialog)
        file_m.addAction(open_a)
        file_m.addSeparator()
        quit_a = QAction("Quitter", self)
        quit_a.setShortcut("Ctrl+Q")
        quit_a.triggered.connect(self.close)
        file_m.addAction(quit_a)

        view_m = mb.addMenu("Affichage")
        dark_a = QAction("Thème sombre", self)
        dark_a.triggered.connect(lambda: self._set_theme("dark"))
        view_m.addAction(dark_a)
        light_a = QAction("Thème clair", self)
        light_a.triggered.connect(lambda: self._set_theme("light"))
        view_m.addAction(light_a)

    def _apply_theme(self):
        self.setStyleSheet(themes.DARK if self._theme == "dark" else themes.LIGHT)

    def _set_theme(self, theme: str):
        self._theme = theme
        self._apply_theme()

    # ------------------------------------------------------------------
    def _open_dialog(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier", str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self._load_folder(Path(folder))

    def _load_folder(self, folder: Path):
        self._status.showMessage(f"Chargement de {folder} …")
        self._preview_cache.clear()
        self._media = scan_folder(folder)
        self.gallery.load_files(self._media)
        n = len(self._media)
        self._status.showMessage(
            f"{n} fichier{'s' if n != 1 else ''} chargé{'s' if n != 1 else ''}"
        )

    # ------------------------------------------------------------------
    def _on_select(self, media: MediaFile):
        self._current = media
        cached = self._preview_cache.get(str(media.path))
        self.tag_panel.load_media(media, cached)
        if not cached:
            self._load_preview(media)

    def _load_preview(self, media: MediaFile):
        loader = ThumbnailLoader(media.path, preview=True)
        loader.signals.ready.connect(self._on_preview_ready)
        self._pool.start(loader)

    def _on_preview_ready(self, path_str: str, pixmap: QPixmap):
        self._preview_cache[path_str] = pixmap
        if self._current and str(self._current.path) == path_str:
            self.tag_panel.update_preview_pixmap(pixmap)

    # ------------------------------------------------------------------
    def _on_rename(self, media: MediaFile, animal: str, quality: str):
        old_path = media.path
        try:
            new_path = media.rename(animal, quality)
        except FileExistsError as e:
            QMessageBox.warning(self, "Erreur", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de renommer :\n{e}")
            return

        self.gallery.update_card_path(old_path, new_path)

        cached = self._preview_cache.pop(str(old_path), None)
        if cached:
            self._preview_cache[str(new_path)] = cached

        self.tag_panel.load_media(media, self._preview_cache.get(str(new_path)))
        self._status.showMessage(f"Renommé → {new_path.name}")
