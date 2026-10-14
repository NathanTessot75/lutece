from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from lutece_pipeline import vision

RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


def flag() -> Image.Image:
    """A photo twice as wide as high: red, green over its middle half, blue."""
    image = Image.new("RGB", (400, 200), GREEN)
    image.paste(RED, (0, 0, 100, 200))
    image.paste(BLUE, (300, 0, 400, 200))
    return image


def test_crop_keeps_the_centre_and_squash_keeps_everything() -> None:
    cropped = vision.frame(flag(), "crop")
    assert cropped.size == (vision.SIDE, vision.SIDE)
    assert {cropped.getpixel((0, 100)), cropped.getpixel((223, 100))} == {GREEN}

    squashed = vision.frame(flag(), "squash")
    assert squashed.size == (vision.SIDE, vision.SIDE)
    assert squashed.getpixel((5, 100)) == RED
    assert squashed.getpixel((112, 100)) == GREEN
    assert squashed.getpixel((218, 100)) == BLUE

    # A photo higher than wide is cropped the same way, top and bottom.
    upright = vision.frame(flag().rotate(90, expand=True), "crop")
    assert {upright.getpixel((100, 0)), upright.getpixel((100, 223))} == {GREEN}
    with pytest.raises(ValueError, match="Unknown framing 'pad'"):
        vision.frame(flag(), "pad")


def test_colours_are_scaled_as_the_model_was_trained() -> None:
    white = vision.to_pixels(Image.new("RGB", (vision.SIDE, vision.SIDE), "white"))
    assert white.shape == (3, vision.SIDE, vision.SIDE)
    assert white.dtype == np.float32
    # One plane per colour: (1 - mean) / deviation of each.
    assert white[:, 0, 0] == pytest.approx([2.249, 2.429, 2.640], abs=1e-3)
    black = vision.to_pixels(Image.new("RGB", (vision.SIDE, vision.SIDE), "black"))
    assert black[:, 10, 10] == pytest.approx([-2.118, -2.036, -1.804], abs=1e-3)
    red = vision.to_pixels(Image.new("RGB", (vision.SIDE, vision.SIDE), RED))
    assert red[0, 0, 0] > 0 > red[1, 0, 0]


def test_photo_is_read_upright_and_in_colour(tmp_path: Path) -> None:
    # A phone held upright stores the photo lying down, with a note to turn it.
    lying = Image.new("L", (40, 20), 128)
    note = lying.getexif()
    note[0x0112] = 6
    lying.save(tmp_path / "photo.jpg", exif=note)
    photo = vision.open_photo(tmp_path / "photo.jpg")
    assert photo.size == (20, 40)
    assert photo.mode == "RGB"
