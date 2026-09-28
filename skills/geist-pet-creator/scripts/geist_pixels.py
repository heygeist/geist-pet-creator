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

# Below this many pixels a blob is antialiasing noise rather than a mark. Shared
# by everything that counts components, so a speck the audit ignores cannot be a
# speck pre-flight vetoes on.
MIN_COMPONENT_AREA = 12


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


def ink_components(
    mask: bytearray, width: int, height: int, min_area: int = MIN_COMPONENT_AREA
) -> list[dict[str, object]]:
    """4-connected components of a 0/1 mask, largest first, tiny specks dropped.

    This lives here rather than in the auditor because two callers now need it
    and they need it for opposite reasons. The auditor counts components on
    finished art to rank a frame's suspicion, after every call is paid for. The
    generator counts them on frame 0, where the same number is worth money: a
    detached mark is an extra component, and detached marks are the defect that
    drew 13 frames across two states and kept none of them on 2026-08-12.

    Entries carry their pixel indices as well as area and bbox, because the
    auditor's stray-fragment repair erases them one pixel at a time.
    """
    seen = bytearray(width * height)
    found: list[dict[str, object]] = []
    for start in range(width * height):
        if not mask[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        pixels: list[int] = []
        while stack:
            index = stack.pop()
            pixels.append(index)
            x = index % width
            y = index // width
            if x > 0 and mask[index - 1] and not seen[index - 1]:
                seen[index - 1] = 1
                stack.append(index - 1)
            if x < width - 1 and mask[index + 1] and not seen[index + 1]:
                seen[index + 1] = 1
                stack.append(index + 1)
            if y > 0 and mask[index - width] and not seen[index - width]:
                seen[index - width] = 1
                stack.append(index - width)
            if y < height - 1 and mask[index + width] and not seen[index + width]:
                seen[index + width] = 1
                stack.append(index + width)
        if len(pixels) < min_area:
            continue
        xs = [index % width for index in pixels]
        ys = [index // width for index in pixels]
        found.append(
            {
                "area": len(pixels),
                "bbox": [min(xs), min(ys), max(xs) + 1, max(ys) + 1],
                "pixels": pixels,
            }
        )
    found.sort(key=lambda component: -component["area"])
    return found


def component_count(image: Image.Image, min_area: int = MIN_COMPONENT_AREA) -> int:
    """How many separate marks are visible in a frame.

    A Pet is one component plus whatever its parts genuinely detach into. Any
    number above what the canonical base shows is a floating mark: a speed line,
    a spark, a dropped limb, or a face glyph that came back in pieces.
    """
    return len(ink_components(alpha_mask(image), image.width, image.height, min_area))


def data_uri(image: Image.Image) -> str:
    """Embed an image in a review page or a provider request."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
