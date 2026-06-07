"""Image enhancement pipeline for GardenVisitors.

Pure, UI-free functions operating on PIL.Image. Light tonal/color ops use
Pillow; the heavy ones (denoise, CLAHE, inpaint, gray-world white balance)
use OpenCV. All adjustments live in the `Adjustments` dataclass; `apply()`
runs them in a fixed, sensible order and skips any op left at its neutral
value so a live preview stays responsive.

Coordinates that must survive preview-vs-full-resolution rendering (crop box,
spot-heal points) are stored as normalized fractions in [0, 1].
"""

from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class Adjustments:
    # Geometry
    rotate: int = 0                 # quarter-turns clockwise: 0/90/180/270
    flip_h: bool = False
    flip_v: bool = False
    crop: tuple | None = None       # (left, top, right, bottom) normalized 0..1

    # One-click
    auto: bool = False              # ImageOps.autocontrast baseline

    # Exposure / tone
    brightness: float = 1.0         # 1.0 neutral
    contrast: float = 1.0           # 1.0 neutral
    gamma: float = 1.0              # 1.0 neutral (<1 lifts shadows)
    clahe: float = 0.0              # 0 off; clipLimit when > 0

    # Color
    white_balance: bool = False     # gray-world auto WB
    temperature: int = 0            # -100 cool .. +100 warm
    saturation: float = 1.0         # 1.0 neutral
    grayscale: bool = False

    # Detail
    sharpen: float = 0.0            # 0 off .. ~2 strong
    denoise: float = 0.0            # 0 off .. ~30 strong

    # Spot-heal: list of (x, y, radius) normalized to image size
    spots: list = field(default_factory=list)

    def is_neutral(self) -> bool:
        return self == Adjustments()

    def copy(self) -> "Adjustments":
        return replace(self, spots=list(self.spots))


# --- PIL <-> OpenCV (BGR) converters --------------------------------------
def _pil_to_cv(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _cv_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))


# --- Individual operations -------------------------------------------------
def _apply_geometry(img: Image.Image, adj: Adjustments) -> Image.Image:
    if adj.rotate:
        # PIL rotates counter-clockwise; negate so positive = clockwise.
        img = img.rotate(-adj.rotate, expand=True)
    if adj.flip_h:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if adj.flip_v:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if adj.crop:
        w, h = img.size
        l, t, r, b = adj.crop
        box = (
            max(0, int(l * w)), max(0, int(t * h)),
            min(w, int(r * w)), min(h, int(b * h)),
        )
        if box[2] > box[0] and box[3] > box[1]:
            img = img.crop(box)
    return img


def _apply_gamma(img: Image.Image, gamma: float) -> Image.Image:
    inv = 1.0 / max(gamma, 0.01)
    lut = [min(255, int((i / 255.0) ** inv * 255 + 0.5)) for i in range(256)]
    return img.point(lut * len(img.getbands()))


def _apply_temperature(img: Image.Image, temp: int) -> Image.Image:
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    arr[..., 0] = np.clip(arr[..., 0] + temp, 0, 255)   # warm up reds
    arr[..., 2] = np.clip(arr[..., 2] - temp, 0, 255)   # cool down blues
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _apply_white_balance(img: Image.Image) -> Image.Image:
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    means = arr.reshape(-1, 3).mean(axis=0)
    gray = float(means.mean())
    scale = gray / np.clip(means, 1e-3, None)
    arr = np.clip(arr * scale, 0, 255)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def _apply_clahe(img: Image.Image, clip: float) -> Image.Image:
    if not CV2_AVAILABLE:
        return img
    bgr = _pil_to_cv(img)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    l = clahe.apply(l)
    return _cv_to_pil(cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR))


def _apply_denoise(img: Image.Image, strength: float) -> Image.Image:
    if not CV2_AVAILABLE:
        return img
    bgr = _pil_to_cv(img)
    out = cv2.fastNlMeansDenoisingColored(bgr, None, strength, strength, 7, 21)
    return _cv_to_pil(out)


def _apply_spots(img: Image.Image, spots: list) -> Image.Image:
    if not CV2_AVAILABLE or not spots:
        return img
    bgr = _pil_to_cv(img)
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for x, y, r in spots:
        cv2.circle(mask, (int(x * w), int(y * h)), max(1, int(r * max(w, h))), 255, -1)
    out = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
    return _cv_to_pil(out)


# --- Pipeline --------------------------------------------------------------
def apply(img: Image.Image, adj: Adjustments) -> Image.Image:
    """Render `img` through the full adjustment pipeline. Returns a new image;
    the input is never mutated. Ops at their neutral value are skipped."""
    img = img.convert("RGB")

    img = _apply_geometry(img, adj)
    img = _apply_spots(img, adj.spots)

    if adj.auto:
        img = ImageOps.autocontrast(img, cutoff=1)
    if adj.white_balance:
        img = _apply_white_balance(img)

    if adj.gamma != 1.0:
        img = _apply_gamma(img, adj.gamma)
    if adj.brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(adj.brightness)
    if adj.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(adj.contrast)
    if adj.clahe > 0:
        img = _apply_clahe(img, adj.clahe)

    if adj.temperature != 0:
        img = _apply_temperature(img, adj.temperature)
    if adj.saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(adj.saturation)
    if adj.grayscale:
        img = img.convert("L").convert("RGB")

    if adj.denoise > 0:
        img = _apply_denoise(img, adj.denoise)
    if adj.sharpen > 0:
        img = img.filter(ImageFilter.UnsharpMask(
            radius=2, percent=int(adj.sharpen * 100), threshold=3,
        ))

    return img


def auto_enhance(img: Image.Image) -> Adjustments:
    """Return a baseline set of adjustments that improves a typical flat /
    low-light frame: autocontrast + a gentle saturation and sharpen bump."""
    return Adjustments(auto=True, saturation=1.15, sharpen=0.4)
