from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QFileDialog, QStatusBar, QMessageBox,
)
from PyQt6.QtCore import Qt, QThreadPool, QSettings
from PyQt6.QtGui import QAction, QPixmap

from core.media import MediaFile, scan_folder, VIDEO_EXTS, IMAGE_EXTS
from core.thumbnail import ThumbnailLoader
from ui.gallery import GalleryWidget
from ui.tag_panel import TagPanel
from ui.editor import EditorDialog
from ui import themes

DEFAULT_FOLDER = Path(r"C:\Users\Renau\OneDrive\Caméra jardin")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GardenVisitors")
        self._settings = QSettings("GardenVisitors", "GardenVisitors")
        self._theme = self._settings.value("theme", "dark")
        self._media: list[MediaFile] = []
        self._current: MediaFile | None = None
        self._preview_cache: dict[str, QPixmap] = {}
        self._last_action: list[tuple[Path, Path]] | None = None  # (current_path, original_path)
        self._pool = QThreadPool.globalInstance()

        self._build_ui()
        self._build_menu()
        self._apply_theme()
        self._restore_geometry()

        folder = self._startup_folder()
        if folder is not None:
            self._load_folder(folder)

    # ------------------------------------------------------------------
    def _startup_folder(self) -> Path | None:
        saved = self._settings.value("last_folder")
        if saved:
            path = Path(saved)
            if path.exists():
                return path
        return DEFAULT_FOLDER if DEFAULT_FOLDER.exists() else None

    def _restore_geometry(self):
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1300, 820)
        sizes = self._settings.value("window/splitter_sizes")
        if sizes:
            try:
                self._splitter.setSizes([int(s) for s in sizes])
            except (TypeError, ValueError):
                pass

    def closeEvent(self, event):
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/splitter_sizes", self._splitter.sizes())
        super().closeEvent(event)

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
        self.gallery.batch_reject_requested.connect(self._on_batch_reject)
        self._splitter.addWidget(self.gallery)

        self.tag_panel = TagPanel()
        self.tag_panel.rename_requested.connect(self._on_rename)
        self.tag_panel.delete_requested.connect(self._on_delete)
        self.tag_panel.edit_requested.connect(self._on_edit)
        self.tag_panel.prev_requested.connect(self._on_prev)
        self.tag_panel.next_requested.connect(self._on_next)
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

        edit_m = mb.addMenu("Édition")
        self._undo_action = QAction("Annuler", self)
        self._undo_action.setShortcut("Ctrl+Z")
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(self._on_undo)
        edit_m.addAction(self._undo_action)

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
        self._settings.setValue("theme", theme)

    # ------------------------------------------------------------------
    def _open_dialog(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier", str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if folder:
            self._load_folder(Path(folder))

    def _maybe_offer_setup(self, folder: Path):
        """If the folder has no managed subfolders but contains loose media
        files directly inside it, offer once to create 'new/' and move them
        in. Opt-in only — never moves files without confirmation."""
        if any((folder / sub).exists() for sub in ("new", "done", "toDelete")):
            return

        all_exts = VIDEO_EXTS | IMAGE_EXTS
        loose = [
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.upper() in all_exts
        ]
        if not loose:
            return

        asked = self._settings.value("setup_offer_asked", [])
        if isinstance(asked, str):
            asked = [asked] if asked else []
        folder_str = str(folder)
        if folder_str in asked:
            return
        asked.append(folder_str)
        self._settings.setValue("setup_offer_asked", asked)

        reply = QMessageBox.question(
            self, "Organiser le dossier",
            f"Ce dossier contient {len(loose)} fichier{'s' if len(loose) != 1 else ''} média "
            "sans la structure 'new / done / toDelete'.\n\n"
            "Créer le dossier 'new' et y déplacer ces fichiers ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        new_dir = folder / "new"
        new_dir.mkdir(exist_ok=True)
        errors = []
        for f in loose:
            try:
                f.rename(new_dir / f.name)
            except OSError as e:
                errors.append(f"{f.name} : {e}")
        if errors:
            QMessageBox.warning(
                self, "Erreurs",
                "Certains fichiers n'ont pas pu être déplacés :\n" + "\n".join(errors),
            )

    def _load_folder(self, folder: Path):
        self._status.showMessage(f"Chargement de {folder} …")
        self._settings.setValue("last_folder", str(folder))
        self._preview_cache.clear()
        self._maybe_offer_setup(folder)
        self._media = scan_folder(folder)
        self.gallery.load_files(self._media)
        counts = {"new": 0, "done": 0, "toDelete": 0, "edited": 0, "other": 0}
        for m in self._media:
            counts[m.folder_tag] = counts.get(m.folder_tag, 0) + 1
        parts = []
        if counts["new"]:
            parts.append(f"{counts['new']} non revu{'s' if counts['new'] != 1 else ''}")
        if counts["done"]:
            parts.append(f"{counts['done']} traité{'s' if counts['done'] != 1 else ''}")
        if counts["edited"]:
            parts.append(f"{counts['edited']} édité{'s' if counts['edited'] != 1 else ''}")
        if counts["toDelete"]:
            parts.append(f"{counts['toDelete']} à effacer")
        if counts["other"]:
            parts.append(f"{counts['other']} autre{'s' if counts['other'] != 1 else ''}")
        total = len(self._media)
        summary = " · ".join(parts) if parts else "aucun fichier"
        self._status.showMessage(f"{total} fichier{'s' if total != 1 else ''} — {summary}")

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

    def _on_edit(self, media: MediaFile):
        if not media.is_image:
            return
        try:
            dialog = EditorDialog(media, self)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir l'éditeur :\n{e}")
            return
        if dialog.exec() == EditorDialog.DialogCode.Accepted and dialog.saved_path:
            # Re-scan so the new edited/ file appears with correct folder_tag/counts.
            self._preview_cache.clear()
            self._media = scan_folder(media._get_root())
            self.gallery.load_files(self._media)
            # Reveal the new edited image and select it.
            self.gallery.show_filter("edited")
            new_media = next((m for m in self._media if m.path == dialog.saved_path), None)
            if new_media is not None:
                self.gallery.select_media(new_media)
            self._status.showMessage(f"Image améliorée enregistrée → edited/{dialog.saved_path.name}")

    def _on_preview_ready(self, path_str: str, pixmap: QPixmap):
        self._preview_cache[path_str] = pixmap
        if self._current and str(self._current.path) == path_str:
            self.tag_panel.update_preview_pixmap(pixmap)

    # ------------------------------------------------------------------
    def _on_prev(self):
        if self._current is None:
            return
        visible = self.gallery.visible_media
        idx = next((i for i, m in enumerate(visible) if m is self._current), -1)
        if idx > 0:
            self.gallery.select_media(visible[idx - 1])

    def _on_next(self):
        if self._current is None:
            return
        visible = self.gallery.visible_media
        idx = next((i for i, m in enumerate(visible) if m is self._current), -1)
        if idx < len(visible) - 1:
            self.gallery.select_media(visible[idx + 1])

    def _on_rename(self, media: MediaFile, new_name: str):
        old_path = media.path
        try:
            new_path = media.rename_to(new_name)
        except FileExistsError as e:
            QMessageBox.warning(self, "Conflit de nom", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de renommer :\n{e}")
            return

        self._record_action([(new_path, old_path)])
        old_idx = self._index_in_visible(media)

        self.gallery.update_card_path(old_path, new_path)
        self._preview_cache_move(old_path, new_path)
        self.gallery.refresh_filter()

        self._advance_after_action(media, old_idx)
        self._status.showMessage(f"Renommé → {new_path.name}")

    def _on_delete(self, media: MediaFile):
        reply = QMessageBox.question(
            self, "Rejeter",
            f"Déplacer vers le dossier 'toDelete' :\n{media.path.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        old_path = media.path
        old_idx = self._index_in_visible(media)

        try:
            new_path = media.move_to_delete_folder()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de déplacer :\n{e}")
            return

        self._record_action([(new_path, old_path)])

        self._preview_cache.pop(str(old_path), None)
        self.gallery.update_card_path(old_path, new_path)
        self.gallery.refresh_filter()

        self._advance_after_action(media, old_idx)
        self._status.showMessage(f"Déplacé vers toDelete → {new_path.name}")

    def _on_batch_reject(self, media_list: list[MediaFile]):
        if not media_list:
            return
        count = len(media_list)
        reply = QMessageBox.question(
            self, "Rejeter la sélection",
            f"Déplacer {count} fichier{'s' if count != 1 else ''} vers le dossier 'toDelete' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        current_in_batch = self._current in media_list
        old_idx = self._index_in_visible(self._current) if current_in_batch else 0

        moved = 0
        errors = []
        action_pairs = []
        for media in media_list:
            old_path = media.path
            try:
                new_path = media.move_to_delete_folder()
            except Exception as e:
                errors.append(f"{old_path.name} : {e}")
                continue
            action_pairs.append((new_path, old_path))
            self._preview_cache.pop(str(old_path), None)
            self.gallery.update_card_path(old_path, new_path)
            moved += 1

        self._record_action(action_pairs)
        self.gallery.clear_marked()
        self.gallery.refresh_filter()

        if current_in_batch:
            new_visible = self.gallery.visible_media
            new_idx = next((i for i, m in enumerate(new_visible) if m is self._current), None)
            if new_idx is not None:
                self.tag_panel.load_media(self._current, self._preview_cache.get(str(self._current.path)))
            else:
                self._navigate_after_removal(old_idx, new_visible)

        if errors:
            QMessageBox.warning(
                self, "Erreurs",
                f"{moved} fichier{'s' if moved != 1 else ''} déplacé{'s' if moved != 1 else ''}.\n"
                "Échecs :\n" + "\n".join(errors),
            )
        self._status.showMessage(
            f"{moved} fichier{'s' if moved != 1 else ''} rejeté{'s' if moved != 1 else ''} → toDelete"
        )

    def _index_in_visible(self, media: MediaFile | None) -> int:
        if media is None:
            return 0
        visible = self.gallery.visible_media
        return next((i for i, m in enumerate(visible) if m is media), 0)

    def _advance_after_action(self, media: MediaFile, old_idx: int):
        """After `media` moves out of its old slot (rename/reject), select the
        next visible item, stay on it if it's still visible (now last in view),
        or jump to the nearest remaining item if it left the active filter."""
        new_visible = self.gallery.visible_media
        new_idx = next((i for i, m in enumerate(new_visible) if m is media), None)

        if new_idx is not None and new_idx < len(new_visible) - 1:
            self.gallery.select_media(new_visible[new_idx + 1])
        elif new_idx is not None:
            self.tag_panel.load_media(media, self._preview_cache.get(str(media.path)))
        else:
            self._navigate_after_removal(old_idx, new_visible)

    def _navigate_after_removal(self, old_idx: int, visible: list[MediaFile]):
        if visible:
            nav_idx = min(old_idx, len(visible) - 1)
            self.gallery.select_media(visible[nav_idx])
        else:
            self._current = None
            self.tag_panel.clear()

    # ------------------------------------------------------------------
    def _record_action(self, pairs: list[tuple[Path, Path]]):
        """Remember the last reversible move(s) — (current_path, original_path)
        — for single-level Ctrl+Z undo. A new action overwrites the previous one."""
        self._last_action = pairs if pairs else None
        self._undo_action.setEnabled(bool(self._last_action))

    def _on_undo(self):
        if not self._last_action:
            return
        pairs = self._last_action
        self._record_action([])
        self.tag_panel.stop_video()

        restored = 0
        errors = []
        for current_path, original_path in pairs:
            media = next((m for m in self._media if m.path == current_path), None)
            if media is None:
                errors.append(f"{current_path.name} : fichier introuvable")
                continue
            if original_path.exists() and original_path != current_path:
                errors.append(f"{original_path.name} : un fichier existe déjà à cet emplacement")
                continue
            try:
                media.path.rename(original_path)
            except OSError as e:
                errors.append(f"{current_path.name} : {e}")
                continue
            self._preview_cache_move(current_path, original_path)
            self.gallery.update_card_path(media.path, original_path)
            media.path = original_path
            restored += 1

        self.gallery.refresh_filter()

        if errors:
            QMessageBox.warning(
                self, "Annulation partielle",
                f"{restored} fichier{'s' if restored != 1 else ''} restauré{'s' if restored != 1 else ''}.\n"
                "Non annulés :\n" + "\n".join(errors),
            )
        self._status.showMessage(
            f"Annulé — {restored} fichier{'s' if restored != 1 else ''} restauré{'s' if restored != 1 else ''}"
        )

    def _preview_cache_move(self, old_path: Path, new_path: Path):
        cached = self._preview_cache.pop(str(old_path), None)
        if cached:
            self._preview_cache[str(new_path)] = cached
