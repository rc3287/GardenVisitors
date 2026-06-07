import re
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ExifTags
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

ANIMALS = ["renard", "chat", "raton-laveur", "hérisson", "autre"]
QUALITY_VALUES = ["q1", "q2", "q3"]
QUALITY_LABELS = ["★ Faible", "★★ Bonne", "★★★ Excellente"]

VIDEO_EXTS = {".MP4", ".AVI", ".MOV", ".MKV"}
IMAGE_EXTS = {".JPG", ".JPEG", ".PNG", ".BMP"}

# Matches the canonical format: Jardin-YYYYMMDD-HHMMSS[ (N)]
_FILENAME_RE = re.compile(
    r"^Jardin-(\d{8})-(\d{6})(?:\s*\((\d+)\))?",
    re.IGNORECASE,
)
# Fallback: any YYYYMMDD-HHMMSS anywhere in the stem
_DATE_FALLBACK_RE = re.compile(r"(\d{8})-(\d{6})")
# Renamed files always end with -q1, -q2, or -q3 before the extension
_RENAMED_RE = re.compile(r"-q[123]$", re.IGNORECASE)

_MANAGED_SUBFOLDERS = {"new", "done", "toDelete", "edited"}
# Order matters for scan_folder iteration / status display
_SUBFOLDER_ORDER = ("new", "done", "toDelete", "edited")


class MediaFile:
    def __init__(self, path: Path):
        self.path = path
        self.suffix = path.suffix.upper()
        self.is_video = self.suffix in VIDEO_EXTS
        self.is_image = self.suffix in IMAGE_EXTS

        self.date_str: str | None = None
        self.time_str: str | None = None
        self.version: str | None = None
        self.subsec: str | None = None
        self.datetime_obj: datetime | None = None

        self._parse_filename()
        if self.is_image:
            self._extract_exif()

    def _parse_filename(self):
        stem = self.path.stem
        m = _FILENAME_RE.match(stem)
        if m:
            self.date_str, self.time_str, self.version = m.group(1), m.group(2), m.group(3)
        else:
            fb = _DATE_FALLBACK_RE.search(stem)
            if fb:
                self.date_str, self.time_str = fb.group(1), fb.group(2)
        if self.date_str and self.time_str:
            try:
                self.datetime_obj = datetime.strptime(
                    f"{self.date_str}{self.time_str}", "%Y%m%d%H%M%S"
                )
            except ValueError:
                pass

    def _extract_exif(self):
        if not PIL_AVAILABLE:
            return
        try:
            with Image.open(self.path) as img:
                exif = img.getexif()
                # DateTimeOriginal/SubSecTimeOriginal live in the Exif sub-IFD,
                # not the top-level IFD0 — the public getexif() doesn't merge it.
                exif_ifd = exif.get_ifd(ExifTags.IFD.Exif) if exif else {}
            dt_str = exif_ifd.get(36867)  # DateTimeOriginal
            if dt_str:
                try:
                    self.datetime_obj = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
            subsec = exif_ifd.get(37521)  # SubSecTimeOriginal
            if subsec:
                s = str(subsec).strip()
                self.subsec = (s[:2] if len(s) >= 2 else s.zfill(2)) if s else None
        except Exception:
            pass

    def sort_key(self):
        return (
            self.datetime_obj or datetime.min,
            self.subsec or "",
            self.version or "0",
        )

    def build_new_name(self, animal: str, quality: str, dup: int = 0) -> str:
        if self.datetime_obj:
            base = self.datetime_obj.strftime("%Y%m%d-%H%M%S")
        elif self.date_str and self.time_str:
            base = f"{self.date_str}-{self.time_str}"
        else:
            base = datetime.now().strftime("%Y%m%d-%H%M%S")

        name = f"{base}-{animal}-{quality}"

        if dup > 0:
            name = f"{name} ({dup})"

        return name + self.path.suffix

    def _get_root(self) -> Path:
        if self.path.parent.name in _MANAGED_SUBFOLDERS:
            return self.path.parent.parent
        return self.path.parent

    @property
    def folder_tag(self) -> str:
        name = self.path.parent.name
        return name if name in _MANAGED_SUBFOLDERS else "other"

    def build_unique_name(self, animal: str, quality: str) -> str:
        root = self._get_root()
        dest = root / "done"
        if not dest.exists():
            dest = self.path.parent  # fallback: same folder
        dup = 0
        while True:
            candidate = self.build_new_name(animal, quality, dup)
            target = dest / candidate
            if not target.exists() or target == self.path:
                return candidate
            dup += 1

    def rename(self, animal: str, quality: str) -> Path:
        return self.rename_to(self.build_unique_name(animal, quality))

    def rename_to(self, new_name: str) -> Path:
        root = self._get_root()
        done_dir = root / "done"
        done_dir.mkdir(exist_ok=True)
        new_path = done_dir / new_name
        if new_path.exists() and new_path != self.path:
            raise FileExistsError(f"Le fichier existe déjà : {new_name}")
        self.path.rename(new_path)
        self.path = new_path
        return new_path

    def move_to_delete_folder(self) -> Path:
        root = self._get_root()
        del_dir = root / "toDelete"
        del_dir.mkdir(exist_ok=True)
        stem, suffix = self.path.stem, self.path.suffix
        new_path = del_dir / self.path.name
        n = 1
        while new_path.exists() and new_path != self.path:
            new_path = del_dir / f"{stem} ({n}){suffix}"
            n += 1
        self.path.rename(new_path)
        self.path = new_path
        return new_path

    def save_edited(self, pil_image) -> Path:
        """Write an enhanced copy into <root>/edited/ — non-destructive: the
        original file is never touched. Conflict-versioned with a ' (N)' suffix.
        Returns the new path. `pil_image` is a PIL.Image."""
        root = self._get_root()
        edited_dir = root / "edited"
        edited_dir.mkdir(exist_ok=True)

        stem, suffix = self.path.stem, self.path.suffix
        new_path = edited_dir / self.path.name
        n = 1
        while new_path.exists():
            new_path = edited_dir / f"{stem} ({n}){suffix}"
            n += 1

        img = pil_image
        if suffix.upper() in (".JPG", ".JPEG"):
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(new_path, quality=95)
        else:
            img.save(new_path)
        return new_path

    @property
    def is_renamed(self) -> bool:
        return bool(_RENAMED_RE.search(self.path.stem))

    @property
    def display_date(self) -> str:
        if self.datetime_obj:
            return self.datetime_obj.strftime("%d/%m/%Y %H:%M:%S")
        return "Date inconnue"


def scan_folder(folder: Path) -> list[MediaFile]:
    all_exts = VIDEO_EXTS | IMAGE_EXTS
    files = []
    subdirs = [folder / sub for sub in _SUBFOLDER_ORDER if (folder / sub).exists()]
    scan_dirs = subdirs if subdirs else [folder]
    for d in scan_dirs:
        for f in d.iterdir():
            if f.is_file() and f.suffix.upper() in all_exts:
                files.append(MediaFile(f))
    files.sort(key=lambda m: m.sort_key())
    return files
