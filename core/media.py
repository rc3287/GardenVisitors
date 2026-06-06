import re
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image
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
                exif = img._getexif()
            if not exif:
                return
            dt_str = exif.get(36867)  # DateTimeOriginal
            if dt_str:
                try:
                    self.datetime_obj = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    pass
            subsec = exif.get(37521)  # SubSecTimeOriginal
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
            base = self.path.stem

        if self.subsec:
            base = f"{base}-{self.subsec}"

        name = f"{base}-{animal}-{quality}"

        if not self.subsec and self.version:
            name = f"{name} ({self.version})"

        if dup > 0:
            name = f"{name} ({dup})"

        return name + self.path.suffix

    def build_unique_name(self, animal: str, quality: str) -> str:
        dup = 0
        while True:
            candidate = self.path.parent / self.build_new_name(animal, quality, dup)
            if not candidate.exists() or candidate == self.path:
                return candidate.name
            dup += 1

    def rename(self, animal: str, quality: str) -> Path:
        return self.rename_to(self.build_unique_name(animal, quality))

    def rename_to(self, new_name: str) -> Path:
        new_path = self.path.parent / new_name
        if new_path.exists() and new_path != self.path:
            raise FileExistsError(f"Le fichier existe déjà : {new_name}")
        self.path.rename(new_path)
        self.path = new_path
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
    for f in folder.iterdir():
        if f.is_file() and f.suffix.upper() in all_exts:
            files.append(MediaFile(f))
    files.sort(key=lambda m: m.sort_key())
    return files
