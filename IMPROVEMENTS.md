# GardenVisitors — Implementation Prompt (for Claude Sonnet)

You are working on **GardenVisitors**, a personal Windows desktop app (PyQt6, Python) for reviewing, tagging, and batch-renaming wildlife trail-camera footage from a garden camera. The owner reviews photos/videos, picks an animal label + a quality rating, and the app renames the file into a structured format and files it away.

## Repository layout (~1,600 lines)
- `main.py` — entry point, creates `QApplication` + `MainWindow`
- `core/media.py` — `MediaFile` class, `scan_folder()`, filename parsing (regex + EXIF date fallback), rename + conflict-versioning. Constants: `ANIMALS`, `QUALITY_VALUES`, `QUALITY_LABELS`, `VIDEO_EXTS`, `IMAGE_EXTS`, `_MANAGED_SUBFOLDERS = {"new","done","toDelete"}`
- `core/thumbnail.py` — `ThumbnailLoader(QRunnable)` + `ThumbnailSignals`, async thumbnail/preview generation via `QThreadPool`; `THUMB_W=160 THUMB_H=120 PREVIEW_MAX=1200`
- `ui/main_window.py` — `MainWindow`, orchestrates gallery ↔ tag panel, owns rename/delete/batch-reject/navigation and a `_preview_cache` dict
- `ui/gallery.py` — `GalleryWidget` (filter bar with live per-folder counts, scrollable grid of `ThumbnailCard`, multi-select + batch reject via Ctrl+click, lazy thumbnail loading on scroll)
- `ui/tag_panel.py` — `TagPanel` (prev/next nav, stacked image/video preview with `VideoPreview` + `ClickableSlider`, `QDateTimeEdit`, animal/quality radio groups, editable proposed-filename `QLineEdit`, Renommer/Rejeter buttons, `AddAnimalDialog`)
- `ui/themes.py` — `DARK` / `LIGHT` QSS stylesheets
- `build.bat` — Windows PyInstaller build

## Data model / workflow
Root folder contains three subfolders: `new/` (unreviewed) → reviewed files are renamed to `YYYYMMDD-HHMMSS-animal-quality[-(N)].EXT` and moved to `done/`, or moved to `toDelete/` via "Rejeter" (soft delete). `scan_folder` scans those three subdirs if present, else falls back to the root. `MediaFile.folder_tag` returns `"new"|"done"|"toDelete"|"other"`. Animals: `renard, chat, raton-laveur, hérisson, autre` (+ runtime-added custom ones). Quality: q1/q2/q3 with labels `★ Faible / ★★ Bonne / ★★★ Excellente`.

## HARD CONSTRAINTS — do not violate
1. **The UI is in French.** All new user-facing labels, dialogs, tooltips, status messages must be in French. Code/comments may be English.
2. **Windows file-handle lock:** before any file rename/move, the `QMediaPlayer` source must be released. `VideoPreview.stop()` already does `player.stop(); player.setSource(QUrl())`. Any new code path that moves a media file must ensure the player is stopped first. Do not regress this.
3. **Never use `objectName("secondary")` on a button narrower than ~80px** — the base `QPushButton` QSS sets `padding: 8px 24px` and `#secondary` doesn't override it, so the label clips to zero width. Use `objectName("nav")` (`padding: 6px 4px`) for small/square buttons.
4. **Build output must stay out of the OneDrive-synced project dir** — don't touch `build.bat`'s `%TEMP%` paths.
5. Single-user personal tool: no auth, telemetry, network, or multi-user concerns.
6. Keep new dependencies to zero if possible (PyQt6, Pillow, opencv-python are already present). `QSettings` is part of PyQt6 — prefer it over adding config libraries.

## Tasks — implement all eight. Work through them in this order; keep each as a focused, self-reviewable change.

### 1. Keyboard-driven review loop (`ui/tag_panel.py`)
Make the whole review loop runnable from the keyboard without losing the existing mouse behavior.
- Add `QShortcut`s (or a `keyPressEvent`) scoped to `TagPanel`:
  - Number keys `1`–`9` → check the animal radio at that position (1-based; ignore if out of range).
  - Quality → **`F1`/`F2`/`F3`** → q1/q2/q3 (avoid conflicting with the animal digit keys).
  - `Entrée`/`Return` → trigger Renommer (only if `rename_btn` is enabled).
  - `Suppr`/`Delete` → trigger Rejeter (only if `delete_btn` is enabled).
  - `←` / `→` → emit `prev_requested` / `next_requested`.
- Selecting an animal/quality via keyboard must run the same path as a click (update the proposed name via `_update_new_name`).
- Don't let these shortcuts fire while the user is typing in `_proposed_edit` or `_datetime_edit` (check focus, or use `Qt.ShortcutContext.WidgetWithChildrenShortcut` appropriately, but ensure typing a filename still works).
- Add a small French tooltip or a "Raccourcis" hint somewhere unobtrusive (e.g. a status tip), documenting the keys.
- **Acceptance:** a file can be fully processed with `<animal digit>` → `<F-key>` → `Entrée`, and prev/next works with arrows, with no mouse.

### 2. Persist settings + custom animals (`ui/main_window.py`, `ui/tag_panel.py`)
Use `QSettings("GardenVisitors", "GardenVisitors")` (INI or native — your choice, keep it simple). Persist and restore:
- **Theme** (`MainWindow._theme`) — currently hardcoded `"dark"`. Load on startup, save in `_set_theme`.
- **Last opened folder** — save in `_load_folder`; on startup, prefer the saved folder, falling back to `DEFAULT_FOLDER` if the saved one doesn't exist.
- **Window geometry + splitter sizes** — save in `closeEvent`, restore in `__init__`.
- **Custom animal list** (`TagPanel._animal_names`) — currently lost on restart. Load the saved list in `TagPanel.__init__` (merge with built-in `ANIMALS`, no duplicates, preserve built-ins first), and save whenever `_add_animal` adds one.
- **Acceptance:** add "lapin", switch to light theme, resize window, restart → lapin is still present, theme is light, geometry restored, last folder reopened.

### 3. Fix the "no subfolders" empty-gallery trap (`ui/gallery.py`, `core/media.py`/`ui/main_window.py`)
Currently `load_files` always checks the **"Non revus"** (`new`) filter by default. If the scanned folder has no `new/done/toDelete` subdirs, every file has `folder_tag == "other"` and the gallery renders **empty** while the status bar reports "X autres" — looks broken.
- In `GalleryWidget.load_files`: after building `_all_media_files`, detect whether any file has a managed `folder_tag` (`new/done/toDelete`). If **none** do (i.e. everything is `"other"`), default the checked filter to **"Tous"** instead of "Non revus".
- Additionally, expose `"other"` files: the four current filters never show `"other"` except under "Tous". That's acceptable as long as the default lands on "Tous" in this case.
- **Optional but preferred:** if loose files exist directly in the root (no subfolders), show a one-time French confirmation dialog offering to create `new/` and move the loose files into it. Make this opt-in (Yes/No), never automatic.
- **Acceptance:** opening a flat folder of camera files shows all of them immediately, not an empty grid.

### 4. Disk thumbnail cache + smarter video frame (`core/thumbnail.py`)
- **Disk cache:** cache generated *gallery* thumbnails (the `preview=False` path) to disk under `%LOCALAPPDATA%\GardenVisitors\thumbs\`. Cache key = hash of `absolute_path + "|" + str(mtime)`. On `run()`, if a cached PNG exists for the current key, load and emit it instead of re-decoding. Write the PNG after generating. Invalidate naturally via mtime in the key (stale entries simply stop being hit; don't bother pruning for now). The big `preview=True` path does **not** need disk caching.
- **Smarter video frame:** in `_load_video_frame`, before `read()`, seek ~1 second in (`cap.set(cv2.CAP_PROP_POS_MSEC, 1000)`); if that read fails, fall back to frame 0. Trail-cam first frames are frequently black.
- **Refactor:** the scale-to-size block is duplicated verbatim in `_load_image` and `_load_video_frame`; extract a `_scale(pix: QPixmap) -> QPixmap` helper that honors the `self.preview` flag.
- **Acceptance:** second launch on the same folder is visibly faster (no cv2 re-extraction); video thumbnails show a real frame, not black.

### 5. Grid rebuild performance on resize (`ui/gallery.py`)
`resizeEvent → _rebuild_grid` currently fires on every pixel of a window drag and re-lays-out every card each time.
- Debounce: route `resizeEvent` through a single-shot `QTimer` (~100 ms) so a rebuild happens once after the drag settles.
- Skip work when nothing changed: track the last column count from `_cols()`; if it's unchanged after a resize, do not rebuild the grid (the layout already reflows within the same column count).
- Keep lazy thumbnail loading correct after debounced rebuilds (`_load_visible_thumbnails` must still run).
- Do **not** attempt the full `QListView`/model virtualization rewrite in this pass — just the debounce + column-count guard. (Leave a brief `# TODO:` comment noting virtualization as the scalable long-term fix.)
- **Acceptance:** dragging the window edge no longer causes visible lag/flicker on a folder of a few hundred files.

### 6. Single-level undo for reject/rename (`ui/main_window.py`)
- After a successful `_on_rename`, `_on_delete`, or `_on_batch_reject`, record what moved as a reversible action: a list of `(current_path, original_path)` pairs plus enough context to refresh the gallery.
- Add an "Annuler" `QAction` (shortcut `Ctrl+Z`) to the **Fichier** (or a new **Édition**) menu. When invoked, move each file back to its original path (guard against the original location now being occupied — show a French warning and skip those), update the gallery card paths + `_preview_cache` keys, call `gallery.refresh_filter()`, and clear the stored action.
- Only one level of undo is required (overwrite the stored action on each new action). Ensure the video player is stopped before the undo moves files (constraint #2).
- **Acceptance:** mis-clicking Rejeter, then Ctrl+Z, restores the file to its prior folder and reselects it.

### 7. De-duplicate post-action navigation (`ui/main_window.py`)
`_on_rename`, `_on_delete`, and `_on_batch_reject` each contain a near-identical block: capture `old_idx` from `gallery.visible_media`, refresh, recompute `new_idx`, then branch to "select next / stay on last / `_navigate_after_removal`".
- Extract a single helper, e.g. `_advance_after_action(media, old_idx)`, and have all three call sites use it. Preserve the current exact behavior (next-if-available, stay-if-last-still-visible, `_navigate_after_removal` if it dropped out of the filter). This is a pure refactor — no behavior change.
- **Acceptance:** navigation after rename/reject/batch-reject behaves identically to before; the three duplicated blocks are gone.

### 8. EXIF correctness (`core/media.py`, and `core/thumbnail.py` for orientation)
- Replace the deprecated private `img._getexif()` (in `MediaFile._extract_exif`) with the public `img.getexif()` (Pillow ≥ 6). Keep the same tag IDs (36867 `DateTimeOriginal`, 37521 `SubSecTimeOriginal`).
- **EXIF orientation:** apply orientation (tag 274) so portrait/rotated JPGs display upright. The cleanest approach: in `ThumbnailLoader._load_image`, when loading via Pillow, call `PIL.ImageOps.exif_transpose(img)` before converting to a `QPixmap`. (If the current image path uses `QPixmap(str(path))` directly, switch the image branch to load via Pillow → transpose → `QImage`/`QPixmap` so orientation is honored consistently for both thumbnail and preview.) Guard with the existing `PIL_AVAILABLE` flag.
- **Acceptance:** a portrait JPG with an orientation tag renders upright in both the gallery card and the large preview; no regression for landscape images.

## General requirements
- Keep changes minimal and idiomatic to the existing code style; match surrounding naming/structure.
- After each task, briefly state what you changed and why, and confirm the relevant acceptance criterion.
- Do not break the existing signal flows (`media_selected`, `rename_requested(MediaFile, str)`, `delete_requested(MediaFile)`, `batch_reject_requested(list)`, `prev_requested`, `next_requested`).
- I run the app on Windows; you're in WSL and can't launch the GUI. Where you can't verify visually, reason carefully about correctness and call out anything I should manually test. If a smoke-import or headless check is feasible (`python -c "import ..."` with `QT_QPA_PLATFORM=offscreen`), run it.
- Don't commit or push unless I ask.

When you're ready, start with task 1 and proceed in order.
