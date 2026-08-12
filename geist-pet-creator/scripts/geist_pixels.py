#!/usr/bin/env python3
"""Alpha primitives for Geist Pet frames.

Every script needs the same handful of operations on an RGBA frame: decide
which pixels count as visible, find what they bound, clear residue, and hand an
image to a review page. They live here once so the alpha threshold has a single
home and a speed-up pays back in every caller.

Operations run through Pillow's C paths rather than Python pixel loops.
"""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageChops, ImageFilter

# A pixel counts as visible above this alpha. Written once; imported everywhere.
ALPHA_THRESHOLD = 8

# Above this alpha a pixel is solid, so it cannot be chroma-key antialiasing.
OPAQUE_THRESHOLD = 245


def solid(image: Image.Image, threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    """An `L` image: 255 where the frame is visible, 0 where it is not."""
    return image.getchannel("A").point(lambda value: 255 if value > threshold else 0)


def alpha_mask(image: Image.Image, threshold: int = ALPHA_THRESHOLD) -> bytearray:
    """A flat 0/1 mask, for component analysis that needs index arithmetic."""
    return bytearray(image.getchannel("A").point(lambda value: 1 if value > threshold else 0).tobytes())


def alpha_bbox(image: Image.Image, threshold: int = ALPHA_THRESHOLD) -> tuple[int, int, int, int] | None:
    """Bounds of the visible pixels, or None when nothing is visible."""
    return solid(image, threshold).getbbox()


def boundary_mask(image: Image.Image, threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    """Visible pixels that touch a non-visible pixel.

    Eroding the visible region and subtracting leaves exactly its inner edge,
    which is what "boundary" has to mean for a fringe ratio to be meaningful.
    """
    visible = solid(image, threshold)
    return ImageChops.subtract(visible, visible.filter(ImageFilter.MinFilter(3)))


def count(mask: Image.Image) -> int:
    """Number of set pixels in an `L` mask produced by this module."""
    return mask.histogram()[255]


def clear_transparent_rgb(image: Image.Image) -> Image.Image:
    """Zero the colour channels of fully transparent pixels."""
    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    keep = alpha.point(lambda value: 255 if value else 0)
    blank = Image.new("L", rgba.size, 0)
    return Image.merge(
        "RGBA",
        (
            Image.composite(red, blank, keep),
            Image.composite(green, blank, keep),
            Image.composite(blue, blank, keep),
            alpha,
        ),
    )


def transparent_rgb_residue(image: Image.Image) -> int:
    """How many fully transparent pixels still carry colour."""
    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    transparent = alpha.point(lambda value: 255 if value == 0 else 0)
    coloured = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(
        lambda value: 255 if value else 0
    )
    return count(ImageChops.multiply(transparent, coloured))


def data_uri(image: Image.Image) -> str:
    """Embed an image in a review page or a provider request."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
