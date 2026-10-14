"""What turns a photo into the vector that the image model gives for it.

The app must treat the photo that a player takes exactly as the pipeline
treats the reference photos (SPEC §6.3): the choices made here, the square of
224 px, how a photo is brought to it and how its colours are scaled, are the
ones to mirror on the phone.
"""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnxruntime
from PIL import Image, ImageOps

# The side, in pixels, of the square that the model reads: 16 patches of 14.
SIDE = 224
# The size of the vector that the model gives for a photo.
DIMENSIONS = 384
# The colours are scaled with the statistics of ImageNet, as when the model was trained.
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
# How a photo that is not square is brought to a square: by keeping its centre,
# or by keeping everything and distorting it.
FRAMINGS = ("crop", "squash")
# One photo at a time, as on the phone: the model with weights on 8 bits scales
# its numbers over the whole batch it is given, so that the vector of a photo
# would depend on the other photos of its batch (cosine of 0.989 with the
# vector of the same photo alone).
BATCH_SIZE = 1

type Pixels = np.ndarray
type Vectors = np.ndarray


def open_photo(path: Path) -> Image.Image:
    """Read a photo upright and in colour."""
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def frame(image: Image.Image, framing: str) -> Image.Image:
    """Bring a photo to the square that the model reads."""
    if framing not in FRAMINGS:
        raise ValueError(f"Unknown framing {framing!r}")
    if framing == "crop":
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side))
    return image.resize((SIDE, SIDE), Image.Resampling.BICUBIC)


def to_pixels(image: Image.Image) -> Pixels:
    """Scale the colours of a framed photo: 3 planes of SIDE by SIDE numbers."""
    values = np.asarray(image, dtype=np.float32) / 255.0
    return ((values - MEAN) / STD).transpose(2, 0, 1)


def open_model(path: Path) -> onnxruntime.InferenceSession:
    """Load an exported model, to run on the processor for the same result everywhere."""
    return onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def embed(model: onnxruntime.InferenceSession, pixels: Pixels) -> Vectors:
    """Give the vectors, of length 1, of a batch of prepared photos."""
    return model.run(None, {"pixels": pixels.astype(np.float32)})[0]


def embed_photos(
    model: onnxruntime.InferenceSession, paths: Sequence[Path], framing: str
) -> Vectors:
    """Give the vectors of the photos, one line each, in their order."""
    vectors = []
    for start in range(0, len(paths), BATCH_SIZE):
        batch = paths[start : start + BATCH_SIZE]
        pixels = np.stack([to_pixels(frame(open_photo(p), framing)) for p in batch])
        vectors.append(embed(model, pixels))
    if not vectors:
        return np.empty((0, DIMENSIONS), dtype=np.float32)
    return np.concatenate(vectors)
