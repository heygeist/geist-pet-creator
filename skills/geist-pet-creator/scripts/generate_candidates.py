#!/usr/bin/env python3
"""Draw Pet art through the External Image Provider (OpenRouter), at every phase.

`--action` picks the phase, and the phases do not work alike:

  concept-sheet   one call, many concepts on a grid, no canonical base yet
  canonical-base  the identity lock itself, at sprite scale
  <state>         source frames, one call each

One frame, one call. A frame strip has to be sliced, and slicing is the only way
a part of the Pet lands in the next cell, so no frame is ever drawn as a strip.
Every frame call carries the canonical base and the previous frame as references,
so the identity lock travels with the request.

A concept sheet is deliberately the exception. It is a grid and it does get cut
up, but a cell never becomes a frame -- it becomes Image 1 of a canonical-base
call, with the canonical-base gate in front of it. A clipped crop shows up as a
poor reference; the same slip in a frame strip would reach the spritesheet. The
grid is also the whole point: cells drawn in one call share scale, weight and
lighting, and cells drawn separately do not.

One transform, one run. Scale is decided once and applied unchanged to every
frame, so a pose never decides how big the Pet is.

The API key comes from OPENROUTER_API_KEY in the environment and never enters
the Pet source bundle.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from geist_grid import CELL_HEIGHT, CELL_WIDTH, FRAME_COUNTS
from geist_house import (
    FAILED_MOOD,
    FLAT_FIELD,
    FRAMING,
    HOUSE_FORM,
    LEGLESS_BODY,
    LEGLESS_MOTION,
    MIN_PASSING_CELLS,
    MOTION_STATES,
    NEVER_TRANSFERS,
    SIGNATURE_MOTION,
    SMOOTH_LOOP,
    cell_id,
    house_style_path,
    layout_for,
)
from geist_manifest import read_manifest
from geist_pixels import ALPHA_THRESHOLD, alpha_bbox, clear_transparent_rgb, component_count, data_uri
import geist_registration as registration
from geist_spend import KIND_VERIFY, MODE_SUPERVISED, MODES, SpendLedger

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# The provider is a deployment choice, not an assumption baked into the code.
# Point OPENROUTER_BASE_URL (or --base-url) at a local mock to exercise this
# path without spending, or at a broker that holds the credential itself.
_BASE_URL_OVERRIDE: str | None = None


def set_base_url(url: str | None) -> None:
    global _BASE_URL_OVERRIDE
    _BASE_URL_OVERRIDE = url.rstrip("/") if url else None


def base_url() -> str:
    if _BASE_URL_OVERRIDE:
        return _BASE_URL_OVERRIDE
    return os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def is_default_provider() -> bool:
    return base_url() == DEFAULT_BASE_URL


def endpoint() -> str:
    return f"{base_url()}/images"


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def send_credential_to(url: str) -> bool:
    """Decide whether this run's key may travel to this endpoint.

    OpenRouter itself: yes, that is whose key it is. A loopback address: yes,
    that is the broker case, and the credential never leaves the machine. Any
    other host: no.

    The accident this prevents is mundane and quiet. A key left exported from an
    earlier setup, plus OPENROUTER_BASE_URL pointed somewhere else, and a real
    credential walks to a third party inside an Authorization header. Refusing
    costs a redirected run its auth; forwarding costs the key.
    """
    if url.rstrip("/") == DEFAULT_BASE_URL:
        return True
    return (urllib.parse.urlparse(url).hostname or "") in LOOPBACK_HOSTS


_WARNED_ABOUT: set[str] = set()


def warn_credential_withheld(url: str) -> None:
    """Say it once per endpoint. Silence here would look like a bug."""
    if url in _WARNED_ABOUT:
        return
    _WARNED_ABOUT.add(url)
    print(
        f"OPENROUTER_API_KEY is set but {url} is neither OpenRouter nor loopback, "
        "so the credential is being withheld. If that endpoint needs auth, it should "
        "hold its own.",
        file=sys.stderr,
    )


DEFAULT_MODEL = "openai/gpt-image-2"
# Confirmed usable by a live request, which is the only test that settles it.
# GET /api/v1/models does NOT list every usable model -- openai/gpt-image-2 and
# x-ai/grok-imagine-image-2.0 are both absent from it and both answer requests.
# Treat that endpoint as a hint, never as proof a model is missing.
#
# Only openai/gpt-5-image and openai/gpt-5-image-mini return true alpha unaided.
# Everything else needs the chroma-key path, and openai/gpt-image-2 additionally
# rejects output_format/background outright, so membership here is not a promise
# of transparency. Maintainers must re-measure pins with authorized fixtures and
# record sanitized release evidence before changing this table.
KNOWN_MODELS = (
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "openai/gpt-image-2",
    "x-ai/grok-imagine-image-2.0",
)

# How each model delivers a transparent frame. Keyed on the model id, because
# that is what the fact belongs to: a config flag would let a bundle quietly ask
# for something the provider cannot do and pay a full draw to find out.
#
#   "native"      returns real alpha when asked. One paid call per frame.
#   "chroma"      has no alpha path. Ask for a flat green field on the FIRST
#                 call and key it out here. Still one paid call per frame.
#   "chroma-bare" chroma, and the model answers HTTP 400 for
#                 output_format/background rather than ignoring them, so neither
#                 field is sent.
#
# Measured 2026-08-12. Sanitized release evidence belongs in the repository's
# root evidence/ directory rather than in the installed skill.
#
# Optimism is not free here. openai/gpt-image-2 is the default and is
# "chroma-bare", so asking it for transparency first bought a rejected
# round-trip AND a paid opaque draw that was discarded every time -- every frame
# drawn twice. On the Karate Crown Guardian build, 2 frames cost 4 calls /
# $0.101 before this table and 2 calls / $0.059 after.
#
# A model absent from this table keeps the optimistic path -- ask, verify, fall
# back -- which is the right behaviour while the capability is genuinely
# unknown. Add an entry only after a cost-capped authorized measurement.
ALPHA_PATHS: dict[str, str] = {
    "google/gemini-3.1-flash-lite-image": "chroma",
    "google/gemini-3.1-flash-image": "chroma",
    "google/gemini-3-pro-image": "chroma",
    "openai/gpt-5-image-mini": "native",
    "openai/gpt-5-image": "native",
    "openai/gpt-image-2": "chroma-bare",
    "x-ai/grok-imagine-image-2.0": "chroma",
}

# A model earns a place in KNOWN_MODELS by being measured, and the measurement
# that matters most for cost is the alpha path. Catch the omission here rather
# than paying a doubled call per frame to discover it.
_unmeasured = [model for model in KNOWN_MODELS if model not in ALPHA_PATHS]
if _unmeasured:
    raise SystemExit(
        f"KNOWN_MODELS entries with no ALPHA_PATHS entry: {', '.join(_unmeasured)}. "
        f"Measure the alpha path with an authorized fixture and add it, or the model draws "
        f"every frame twice."
    )

# Lanczos resampling spreads an edge by roughly one pixel.
RESAMPLE_BLEED = 1

# How much of the safe box the first frame deliberately leaves empty.
#
# The transform is built from frame 0 and applied unchanged to every later
# frame, so whatever margin frame 0 has is exactly the margin the whole state
# has. Fitting frame 0 tight to the safe box therefore puts it flush against the
# edge, and any later frame that grows -- a jump, a stretch, hair swinging wide
# -- crosses the cell line. Measured: a body scaled tight to a 192x208 cell
# clips on 2% growth.
#
# That is why asking the model for a generous margin cannot fix clipping on its
# own. The margin is on the provider canvas and the transform normalises it
# away. The headroom has to be reserved here, where the scale is decided, and it
# costs no provider calls at all.
#
# 8% buys roughly 15 pixels of vertical growth, which covers the motion range of
# the nine states. Raise it for a Pet whose silhouette swings a long way.
MOTION_HEADROOM = 0.08

# A returned image counts as alpha-capable only when the border is genuinely
# clear and a real share of the canvas is transparent. An opaque image with one
# stray transparent pixel must not pass.
MIN_TRANSPARENT_FRACTION = 0.10
MIN_CLEAR_BORDER_FRACTION = 0.90

# Backdrops a chroma run can ask for, and why there is more than one.
#
# `CHROMA_KEY` was pure green and nothing else, hardcoded, and nothing consulted
# the Pet before choosing it. FuseSprout's body is #9FC351. Five of six `review`
# frames keyed; the sixth came back opaque, took the state with it, and cost
# $0.14. A green Pet, a magenta Pet or a blue one each carried a silent tax that
# fired unpredictably, and when it fired it was a total loss -- the frame is not
# recoverable, because the background is baked into the art.
#
# So the backdrop is chosen per bundle, from the canonical base, by picking the
# candidate furthest from the colours the Pet actually uses. Blue and cyan are in
# the table and will almost never win: the house form puts a thick sky-blue
# outline on every Pet, so they score badly for all of them. They are here so
# that the choice is made by measurement rather than by a table that quietly
# encodes one assumption, which is the failure this replaces.
KEY_COLOURS: dict[str, tuple[int, int, int]] = {
    "green": (0, 255, 0),
    "magenta": (255, 0, 255),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
}
GREEN_KEY = KEY_COLOURS["green"]
KEY_TOLERANCE = 72

# How much clearance a backdrop needs from the Pet's nearest colour before it is
# safe. Sitting at exactly KEY_TOLERANCE means the key eats the body; this is the
# margin above that, in the same |dR|+|dG|+|dB| units the keyer measures in.
KEY_SAFE_MARGIN = 120


def chroma_suffix(key: tuple[int, int, int]) -> str:
    """The background instruction for one keying colour.

    Exactly one background suffix is appended to every frame prompt, by
    generate_frame, so a prompt can never ask for a transparent background and a
    coloured one in the same breath. It carries FLAT_FIELD: an unkeyed panel
    behind the character reads as art to the keyer and cost a redraw on
    2026-08-12.
    """
    name = next((label for label, value in KEY_COLOURS.items() if value == key), "green")
    hexcode = "#%02X%02X%02X" % key
    return (
        f" Place the character on a background of pure {name} ({hexcode}). {FLAT_FIELD} "
        f"Keep the {name} clear of the character and use no {name} in the character itself."
    )


# Kept as a module constant because eval_providers.py measures the green path and
# should keep measuring exactly what it always did.
CHROMA_SUFFIX = chroma_suffix(GREEN_KEY)
TRANSPARENT_SUFFIX = f" Use a fully transparent background. {FLAT_FIELD}"

SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|[A-Za-z0-9_\-]{40,})")

CONCEPT_SHEET = "concept-sheet"
CANONICAL_BASE = "canonical-base"
PRE_FRAME_ACTIONS = (CONCEPT_SHEET, CANONICAL_BASE)
ACTIONS = (*PRE_FRAME_ACTIONS, *sorted(FRAME_COUNTS))

# The one state that is drawn by moving pixels rather than by asking a provider.
MIRROR_OF = "running-left"
MIRROR_SOURCE = "running-right"

# Ceilings sized per action, because an eight-frame state and a one-call sheet
# are not the same accident. A sheet run under the state ceiling has no real
# guard: a mistyped flag would keep drawing until something else noticed.
#
# `None` for the image cap means "derive it from --variants", since a
# canonical-base run scales with how many options were asked for.
ACTION_CEILINGS: dict[str, tuple[int | None, float]] = {
    CONCEPT_SHEET: (1, 0.10),
    CANONICAL_BASE: (None, 0.25),
}
FRAME_CEILINGS = (24, 3.0)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass
class ProviderConfig:
    provider: str = "openrouter"
    model: str = DEFAULT_MODEL
    output_format: str = "png"
    background: str = "transparent"
    resolution: str | None = None
    aspect_ratio: str | None = None
    quality: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def request_body(self, prompt: str, references: list[str]) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "prompt": prompt, "n": 1}
        # Several models answer HTTP 400 for output_format/background rather
        # than ignoring them, which makes them unreachable if these are always
        # sent. Setting either to None drops it and routes the request through
        # the chroma-key path instead.
        if self.output_format is not None:
            body["output_format"] = self.output_format
        if self.background is not None:
            body["background"] = self.background
        for key in ("resolution", "aspect_ratio", "quality"):
            value = getattr(self, key)
            if value:
                body[key] = value
        body.update(self.extra)
        if references:
            body["input_references"] = [
                {"type": "image_url", "image_url": {"url": reference}} for reference in references
            ]
        return body


def load_config(bundle: Path, override_model: str | None) -> ProviderConfig:
    path = bundle / "imagegen.json"
    raw: dict[str, Any] = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        guard_against_secrets(path, raw)

    provider = raw.get("provider", "openrouter")
    if provider != "openrouter":
        raise SystemExit(f"imagegen.json names provider '{provider}'; this script speaks openrouter only")

    known = {"provider", "model", "output_format", "background", "resolution", "aspect_ratio", "quality"}
    check_model(override_model or raw.get("model", DEFAULT_MODEL), path)
    config = ProviderConfig(
        provider=provider,
        model=override_model or raw.get("model", DEFAULT_MODEL),
        output_format=raw.get("output_format", "png"),
        background=raw.get("background", "transparent"),
        resolution=raw.get("resolution"),
        aspect_ratio=raw.get("aspect_ratio"),
        quality=raw.get("quality"),
        # A leading underscore marks a note for the reader, so it stays out of
        # the request body. Anything else is passed through to the provider.
        extra={
            key: value for key, value in raw.items() if key not in known and not key.startswith("_")
        },
    )
    if config.background == "transparent" and config.output_format not in {"png", "webp"}:
        raise SystemExit("a transparent background needs output_format png or webp")
    return config


CATALOG_TRAP = """
Do NOT "verify" a model id against GET /api/v1/models and repin on the result.
That listing is INCOMPLETE. Measured 2026-08-12: openai/gpt-image-2,
qwen/qwen-image-3-pro and x-ai/grok-imagine-image-2.0 are all absent from it,
authenticated and unauthenticated, and all three answer real requests.
openai/gpt-image-2 is this skill's measured default.

This mistake has been made repeatedly, and it makes things worse: sessions have
repinned working bundles onto openai/gpt-5.4-image-2, which rejects the
transparency parameters this pipeline sends. A confident-looking catalog check
returning the wrong answer is exactly why this message exists.

The only test that settles whether a model works is a live request:

    with_openrouter_key.sh <isolated-python> generate_candidates.py \\
        --verify-model MODEL_ID

It is billable and answers definitively. Obtain authority for the total test-run
ceiling before using it or changing any pin.
"""


def check_model(model: str, path: Path) -> None:
    """Reject an unknown pin, and say why the obvious verification is wrong.

    A bundle's imagegen.json is data that travels between machines, so it can
    name anything. Catching it here fails on a cheap local read rather than at
    the provider, mid-run, after money has been spent.
    """
    if model in KNOWN_MODELS:
        return
    raise SystemExit(
        f"{path} pins model '{model}', which is not in KNOWN_MODELS.\n\n"
        f"Verified working ids:\n  " + "\n  ".join(KNOWN_MODELS) + "\n"
        f"{CATALOG_TRAP}"
    )


def verify_model_live(model: str) -> None:
    """Settle a model id the only way that is authoritative: ask the provider.

    Prints what actually happened -- reachable, rejected, or unknown -- so nobody
    has to infer existence from a catalog that omits working models.
    """
    print(f"live request to {endpoint()} for {model} ...", flush=True)
    config = ProviderConfig(model=model, output_format=None, background=None)
    try:
        payload = call_provider(config, "a small red circle on a plain background", [], retries=0)
    except SystemExit as error:
        detail = str(error)
        if "404" in detail or "no endpoints" in detail.lower():
            raise SystemExit(f"{model}: NOT REACHABLE -- {detail}") from None
        raise SystemExit(f"{model}: request failed -- {detail}") from None
    cost = float((payload.get("usage") or {}).get("cost") or 0.0)

    # A probe writes no candidate packet, so the ledger is the only place this
    # ~$0.01 is ever visible. It belongs to no bundle, so the home ledger takes
    # it alone.
    probe = SpendLedger(model=model, mode=None, kind=KIND_VERIFY, endpoint=endpoint())
    probe.record(cost, note="--verify-model probe")

    listed = model in KNOWN_MODELS
    print(f"{model}: REACHABLE. total test-run cost ${cost:.5f}.")
    print(f"  in KNOWN_MODELS: {listed}")
    if not listed:
        print("  It works but is not pinned as known. Add it to KNOWN_MODELS if you want it,")
        print("  and record a cost-capped authorized measurement before making it a default.")
    for warning in probe.warnings:
        print(f"  warning: {warning}")


def guard_against_secrets(path: Path, raw: dict[str, Any]) -> None:
    """Keep the key in the environment, where the bundle cannot carry it away."""
    for key, value in raw.items():
        if not isinstance(value, str):
            continue
        if "key" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            raise SystemExit(f"{path} holds '{key}'; put the API key in OPENROUTER_API_KEY instead")
        if SECRET_PATTERN.fullmatch(value.strip()):
            raise SystemExit(f"{path} value for '{key}' looks like an API key; put it in OPENROUTER_API_KEY instead")


def api_key() -> str:
    """Resolve the credential, or establish that this run does not carry one.

    Against OpenRouter directly a key is mandatory. Against a non-default base
    URL it is not: that endpoint is a broker holding the credential itself, or a
    mock that wants no credential at all. Sending a key we were never given, or
    demanding one the deployment deliberately withholds, would both be wrong.
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key and is_default_provider():
        raise SystemExit(
            "no credential. On macOS run through scripts/with_openrouter_key.sh, which reads the "
            "key from the login keychain. Otherwise export OPENROUTER_API_KEY, or point "
            "OPENROUTER_BASE_URL at a broker that holds the credential."
        )
    return key


def credential_source() -> str:
    """Name the path that supplied the credential, so a quiet demotion shows.

    The wrapper sets a marker. Without it the key came from a bare environment
    variable, which is the documented fallback and is fine -- but someone who
    believes they are on the hardened path should be able to see that they are
    not, rather than finding out from a leaked key later.
    """
    if os.environ.get("GEIST_CREDENTIAL_SOURCE"):
        return os.environ["GEIST_CREDENTIAL_SOURCE"]
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return "none"
    return "environment"


# --------------------------------------------------------------------------- #
# Spend guard
# --------------------------------------------------------------------------- #


class SpendGuard:
    """Bound a run before it bounds itself. 3 variants x 9 states x per-frame is
    171 calls, and nothing else in the pipeline notices that."""

    def __init__(self, max_images: int, max_cost_usd: float, ledger: SpendLedger | None = None) -> None:
        self.max_images = max_images
        self.max_cost_usd = max_cost_usd
        self.images = 0
        self.cost = 0.0
        self.ledger = ledger

    def check(self) -> None:
        if self.images >= self.max_images:
            raise SystemExit(f"stopped at the --max-images ceiling of {self.max_images}")
        if self.cost >= self.max_cost_usd:
            raise SystemExit(f"stopped at the --max-cost-usd ceiling of ${self.max_cost_usd:.2f}")

    def record(self, cost: float) -> None:
        self.images += 1
        self.cost += cost
        if self.ledger is not None:
            # Appended here, not with the packet. This is the moment the money was
            # spent, and a run that dies at the next ceiling check writes no
            # packet at all -- that spend would otherwise be invisible.
            self.ledger.record(cost)

    def as_dict(self) -> dict[str, Any]:
        return {
            "images": self.images,
            "cost_usd": round(self.cost, 6),
            "max_images": self.max_images,
            "max_cost_usd": self.max_cost_usd,
        }


# --------------------------------------------------------------------------- #
# One transform for the whole run
# --------------------------------------------------------------------------- #


@dataclass
class CellTransform:
    """Scale and placement from provider canvas into one 192x208 cell.

    Built once from the first frame and applied unchanged to every later frame.
    Fitting each frame to its own bounding box instead would let a crouched pose
    come out larger than a standing one, which is the scale popping the QA
    rubric rejects.
    """

    scale: float
    offset_x: int
    offset_y: int
    source_size: tuple[int, int]
    headroom: float = MOTION_HEADROOM

    @classmethod
    def from_reference(
        cls, image: Image.Image, safe_padding: int, headroom: float = MOTION_HEADROOM
    ) -> "CellTransform":
        bbox = alpha_bbox(image)
        if not bbox:
            raise SystemExit("reference frame has no visible pixels; cannot derive a cell transform")
        left, top, right, bottom = bbox
        body_width = max(1, right - left)
        body_height = max(1, bottom - top)
        # Lanczos softens an edge by about a pixel, and a soft pixel still counts
        # as visible. Reserve that pixel so the reference frame clears its own
        # padding check rather than reporting itself as a misfit.
        margin = (safe_padding + RESAMPLE_BLEED) * 2
        fitted = min((CELL_WIDTH - margin) / body_width, (CELL_HEIGHT - margin) / body_height)
        # Frame 0 sits back from the safe box by `headroom` so the frames that
        # follow it -- drawn under this same transform -- have somewhere to grow.
        scale = fitted * (1.0 - headroom)
        centre_x = (left + right) / 2
        centre_y = (top + bottom) / 2
        return cls(
            scale=scale,
            offset_x=round(CELL_WIDTH / 2 - centre_x * scale),
            offset_y=round(CELL_HEIGHT / 2 - centre_y * scale),
            source_size=image.size,
            headroom=headroom,
        )

    def growth_allowance(self, cell: Image.Image, safe_padding: int) -> dict[str, Any]:
        """How much this body can still grow before it touches the cell line.

        The number the character bible could only describe in prose. A base
        whose allowance is near zero will fight every motion state, and the one
        moment when swapping it is free is the canonical-base review.
        """
        bbox = alpha_bbox(cell)
        if not bbox:
            return {"width_pct": 0.0, "height_pct": 0.0, "limited_by": "no visible pixels"}
        left, top, right, bottom = bbox
        body_width = max(1, right - left)
        body_height = max(1, bottom - top)
        width_pct = (CELL_WIDTH - 2 * safe_padding) / body_width - 1.0
        height_pct = (CELL_HEIGHT - 2 * safe_padding) / body_height - 1.0
        return {
            "width_pct": round(width_pct * 100, 1),
            "height_pct": round(height_pct * 100, 1),
            "limited_by": "height" if height_pct <= width_pct else "width",
        }

    def apply(self, image: Image.Image) -> Image.Image:
        scaled = image.resize(
            (max(1, round(image.width * self.scale)), max(1, round(image.height * self.scale))),
            Image.LANCZOS,
        )
        cell = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
        cell.paste(scaled, (self.offset_x, self.offset_y))
        return clear_transparent_rgb(cell)

    def fit_report(self, cell: Image.Image, safe_padding: int) -> dict[str, Any]:
        """Whether the body landed inside safe padding under the shared transform."""
        bbox = alpha_bbox(cell)
        if not bbox:
            return {"fits": False, "reason": "no visible pixels after transform"}
        left, top, right, bottom = bbox
        inside = (
            left >= safe_padding
            and top >= safe_padding
            and right <= CELL_WIDTH - safe_padding
            and bottom <= CELL_HEIGHT - safe_padding
        )
        return {
            "fits": inside,
            "bbox": [left, top, right, bottom],
            "reason": None if inside else "body reaches outside safe padding under the run transform",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "scale": round(self.scale, 6),
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "source_size": list(self.source_size),
            "motion_headroom": round(self.headroom, 4),
        }


# --------------------------------------------------------------------------- #
# Provider call
# --------------------------------------------------------------------------- #


def image_reference(path: Path) -> str:
    with Image.open(path) as opened:
        return data_uri(opened.convert("RGBA"))


def call_provider(config: ProviderConfig, prompt: str, references: list[str], retries: int = 2) -> dict[str, Any]:
    body = config.request_body(prompt, references)
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/heygeist/geist-pet-creator",
        "X-Title": "geist-pet-creator",
    }
    key = api_key()
    if key and send_credential_to(base_url()):
        headers["Authorization"] = f"Bearer {key}"
    elif key:
        warn_credential_withheld(base_url())
    request = urllib.request.Request(
        endpoint(),
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:400]
            last = RuntimeError(f"HTTP {error.code}: {detail}")
            if error.code not in {408, 429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError) as error:  # noqa: PERF203
            last = error
        if attempt < retries:
            time.sleep(2 ** attempt)
    raise SystemExit(f"image request failed: {last}")


def decode_image(payload: dict[str, Any]) -> tuple[Image.Image, float]:
    data = payload.get("data") or []
    if not data or "b64_json" not in data[0]:
        raise SystemExit(f"provider returned no image: {json.dumps(payload)[:400]}")
    raw = base64.b64decode(data[0]["b64_json"])
    with Image.open(io.BytesIO(raw)) as opened:
        image = opened.convert("RGBA")
    cost = float((payload.get("usage") or {}).get("cost") or 0.0)
    return image, cost


# --------------------------------------------------------------------------- #
# Transparency: request, verify, fall back
# --------------------------------------------------------------------------- #


def alpha_is_real(image: Image.Image) -> bool:
    alpha = image.getchannel("A")
    width, height = image.size
    pixels = alpha.tobytes()
    transparent = sum(1 for value in pixels if value < 16)
    if transparent / len(pixels) < MIN_TRANSPARENT_FRACTION:
        return False

    border: list[int] = []
    border.extend(pixels[0:width])
    border.extend(pixels[(height - 1) * width : height * width])
    for y in range(height):
        border.append(pixels[y * width])
        border.append(pixels[y * width + width - 1])
    clear = sum(1 for value in border if value < 16)
    return clear / len(border) >= MIN_CLEAR_BORDER_FRACTION


def is_key_fringe(pixel: tuple[int, int, int], key: tuple[int, int, int]) -> bool:
    """Whether a pixel is the desaturated halo a chroma background leaves.

    The test used to name green directly. It is the same test for any keying
    colour once it is stated as what it always meant: a pixel belongs to the
    fringe when every channel the key saturates is strong AND clearly beats every
    channel the key leaves at zero. For green that is exactly the old
    `green > 150 and green > red * 1.5 and green > blue * 1.5`.

    It is a function rather than three lines inside the keyer because
    `choose_chroma_key` has to ask the same question before spending anything.
    This test, not the distance test, is what makes a backdrop dangerous: cyan
    sits 137 away from the house form's sky-blue outline -- comfortably past the
    72 tolerance -- and still erases it, because a sky blue is exactly "green and
    blue both strong, red weak".
    """
    high = [channel for channel in range(3) if key[channel] >= 128]
    low = [channel for channel in range(3) if key[channel] < 128]
    if not high or not low:
        return False
    strongest = min(pixel[channel] for channel in high)
    return strongest > 150 and all(strongest > pixel[channel] * 1.5 for channel in low)


def key_out_chroma(image: Image.Image, key: tuple[int, int, int] = GREEN_KEY) -> Image.Image:
    """Remove a flat chroma background and the desaturated fringe it leaves."""
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    out = bytearray(len(data) // 3 * 4)
    key_r, key_g, key_b = key
    for index in range(0, len(data), 3):
        pixel = (data[index], data[index + 1], data[index + 2])
        red, green, blue = pixel
        distance = abs(red - key_r) + abs(green - key_g) + abs(blue - key_b)
        base = index // 3 * 4
        if distance <= KEY_TOLERANCE or is_key_fringe(pixel, key):
            continue  # stays fully transparent, RGB left at zero
        out[base] = red
        out[base + 1] = green
        out[base + 2] = blue
        out[base + 3] = 255
    return Image.frombytes("RGBA", image.size, bytes(out))


def choose_chroma_key(canonical: Image.Image) -> dict[str, Any]:
    """The backdrop furthest from this Pet's own colours, decided once per bundle.

    Scores every candidate by the nearest visible pixel of the canonical base, in
    the same |dR|+|dG|+|dB| units the keyer thresholds on, and takes the largest
    of those minimums. That is the right statistic and not the obvious one: an
    average distance would happily pick a backdrop the Pet only touches on its
    outline, and the outline is the part whose loss is most visible.

    Distance alone is not enough, because it is not the only way the keyer
    deletes a pixel. A candidate that would catch ANY of the Pet's colours in its
    fringe test is scored zero and cannot win, however far away it measures. Cyan
    is the case that proves it: it sits 137 from the house form's sky-blue
    outline, twice the 72 tolerance, and would erase that outline on every frame.

    Colours are sampled from the base rather than declared in the character
    bible, because the bible states intent and the provider draws what it draws.
    The palette that matters is the one in the pixels every later frame is
    counted against.
    """
    visible = canonical.convert("RGBA")
    alpha = visible.getchannel("A")
    rgb = visible.convert("RGB")
    # Quantising to a 32-level cube collapses antialiasing and JPEG noise into
    # the colours a human would name, and turns this into a few hundred
    # comparisons rather than a few hundred thousand.
    palette: set[tuple[int, int, int]] = set()
    for (red, green, blue), opacity in zip(rgb.getdata(), alpha.getdata()):
        if opacity > ALPHA_THRESHOLD:
            palette.add((red // 32 * 32 + 16, green // 32 * 32 + 16, blue // 32 * 32 + 16))

    scored: dict[str, int] = {}
    for label, candidate in KEY_COLOURS.items():
        if any(is_key_fringe(colour, candidate) for colour in palette):
            scored[label] = 0
            continue
        scored[label] = min(
            (
                abs(red - candidate[0]) + abs(green - candidate[1]) + abs(blue - candidate[2])
                for red, green, blue in palette
            ),
            default=765,
        )

    label = max(scored, key=lambda name: scored[name])
    clearance = scored[label]
    return {
        "key": KEY_COLOURS[label],
        "name": label,
        "clearance": clearance,
        "scores": scored,
        "safe": clearance >= KEY_TOLERANCE + KEY_SAFE_MARGIN,
    }


def opaque(config: ProviderConfig, aspect_ratio: str | None = None) -> ProviderConfig:
    """The same config, asking for an ordinary opaque image.

    A concept sheet wants warm off-white paper: the negative space between cells
    is what keeps the mascots readable, and the cells become reference images
    rather than frames, so there is nothing that needs alpha.
    """
    return ProviderConfig(
        provider=config.provider,
        model=config.model,
        output_format=config.output_format,
        background=None,
        resolution=config.resolution,
        aspect_ratio=aspect_ratio or config.aspect_ratio,
        quality=config.quality,
        extra=config.extra,
    )


def drop_transparency_params(config: ProviderConfig, keep_output_format: bool) -> ProviderConfig:
    """The same config without the fields a chroma run has no use for.

    `background` always goes: a chroma run is asking for a flat green field, not
    for alpha. `output_format` stays wherever the model tolerates it, because a
    lossy default puts compression noise around the green edge and the key-out
    leaves a halo where that noise was.
    """
    return ProviderConfig(
        provider=config.provider,
        model=config.model,
        output_format=config.output_format if keep_output_format else None,
        background=None,
        resolution=config.resolution,
        aspect_ratio=config.aspect_ratio,
        quality=config.quality,
        extra=config.extra,
    )


def generate_frame(
    config: ProviderConfig,
    prompt: str,
    references: list[str],
    guard: SpendGuard,
    require_alpha: bool = True,
    chroma_key: tuple[int, int, int] = GREEN_KEY,
) -> tuple[Image.Image, dict[str, Any]]:
    """Draw one image on the provider canvas. Placement happens later, once.

    The model's entry in ALPHA_PATHS decides how transparency is asked for, so a
    model with no alpha path spends one call rather than two. A model absent
    from the table is asked optimistically and checked, which is what an unknown
    capability deserves.

    `require_alpha` is False only for a concept sheet, which asked for paper.
    Running the transparency check on it would see an opaque image, conclude the
    provider ignored a parameter that was never sent, and spend a second call
    keying out a background the sheet is supposed to have.

    `chroma_key` is the backdrop `choose_chroma_key` picked for this bundle. It
    defaults to green so that the two phases drawn before a canonical base exists
    keep the behaviour they have always had -- there is no Pet to be the same
    colour as yet.
    """
    suffix = chroma_suffix(chroma_key)

    def once(active: ProviderConfig, text: str) -> tuple[Image.Image, float]:
        guard.check()
        payload = call_provider(active, text, references)
        image, cost = decode_image(payload)
        guard.record(cost)
        return image, cost

    declared = ALPHA_PATHS.get(config.model)
    bare = declared == "chroma-bare"
    chroma_first = require_alpha and declared in {"chroma", "chroma-bare"}

    if chroma_first:
        active = drop_transparency_params(config, keep_output_format=not bare)
        text = prompt + suffix
        alpha_path = "params-dropped+chroma-key" if bare else "chroma-key"
    elif not require_alpha:
        # The caller already asked for paper, so only the fields this model
        # rejects outright still need dropping. The sheet prompt names its own
        # background, so no suffix goes on it.
        active = drop_transparency_params(config, keep_output_format=False) if bare else config
        text = prompt
        alpha_path = "opaque by request"
    else:
        active = config
        text = prompt + TRANSPARENT_SUFFIX
        alpha_path = "native"

    try:
        image, cost = once(active, text)
    except SystemExit as error:
        # Some models reject `output_format`/`background` outright instead of
        # ignoring them -- openai/gpt-image-2 answers "background: not
        # supported. Accepted: auto, opaque". Dropping the fields makes the
        # model reachable rather than losing the run. Reaching this branch for a
        # model that IS in ALPHA_PATHS means the entry disagrees with the
        # provider, so the recorded path says so and the entry needs
        # re-measuring.
        if "400" not in str(error) or "parameter" not in str(error).lower():
            raise
        active = drop_transparency_params(active, keep_output_format=False)
        image, cost = once(active, text)
        alpha_path = f"params-dropped+{alpha_path}"

    if chroma_first:
        image = key_out_chroma(image, chroma_key)
    elif require_alpha and not alpha_is_real(image):
        # An unknown model that ignored `background: transparent`, or a table
        # entry gone stale. Ask for a flat chroma field and key it out here.
        text = prompt + suffix
        image, cost = once(drop_transparency_params(active, keep_output_format=True), text)
        image = key_out_chroma(image, chroma_key)
        alpha_path = f"{alpha_path}+chroma-key"

    provenance = {
        "provider": config.provider,
        "model": config.model,
        "endpoint": endpoint(),
        "requested_background": active.background,
        "requested_output_format": active.output_format,
        "alpha_path": alpha_path,
        "alpha_path_source": "table" if declared else "probed",
        # Beside alpha_path, because they are the same fact: how this frame got
        # its transparency. A frame that keyed badly is diagnosed from the pair.
        "chroma_key": list(chroma_key) if "chroma" in alpha_path else None,
        # What was actually sent, so prompt.md and the packet cannot disagree
        # with the request about which background was asked for.
        "background_instruction": text[len(prompt):].strip(),
        "credential_source": credential_source(),
        "run_cost_usd": round(guard.cost, 6),
        "images_this_run": guard.images,
    }
    return image, provenance


# --------------------------------------------------------------------------- #
# Candidate packets
# --------------------------------------------------------------------------- #


def build_prompt(bundle: Path, state: str, index: int, frame_count: int, variant_intent: str, extra: str) -> str:
    """The frame prompt.

    It carries the house-form rules the run will be judged against, because
    every one of them used to live only in SKILL.md prose. The background line
    is deliberately absent: generate_frame appends the one the model's alpha
    path actually needs.
    """
    manifest = read_manifest(bundle / "character-bible.md")
    # Every state is legless, so every prompt says so. The four whose name pulls
    # towards legs get the longer version, which also says what to move instead.
    movement = LEGLESS_MOTION if state in MOTION_STATES else LEGLESS_BODY
    # `failed` is sad in every frame; every other state carries its own mood in
    # the variant intent, so only `failed` gets an imposed mood block.
    mood = f"{FAILED_MOOD}\n" if state == "failed" else ""
    return (
        f"Draw frame {index} of {frame_count} for the `{state}` sprite action of this Pet.\n"
        f"The attached images are the identity lock: image 1 is the canonical base, "
        f"image 2 is the previous approved frame of this same action.\n"
        f"Keep the silhouette, proportions, palette, face landmarks, props and scale identical to them.\n"
        f"Motion read: {variant_intent}\n"
        f"{mood}"
        f"{SIGNATURE_MOTION}\n"
        f"{SMOOTH_LOOP}\n"
        f"{movement}\n"
        f"{FRAMING}\n"
        f"One character only, and no text, letters or numbers anywhere."
        f"{manifest.prompt_block()}\n"
        f"{extra}"
    ).strip()


def read_locks(path: Path) -> list[str]:
    """One identity lock per cell, in row-major order.

    Accepts a JSON array of strings, or of objects carrying a `text` field, so a
    file written for the review page can be handed straight to the generator.
    Order is the contract: element 4 describes `cell-04`, and nothing downstream
    re-sorts it.
    """
    if not path.is_file():
        raise SystemExit(f"--locks-file {path} does not exist")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"--locks-file {path} is not valid JSON: {error}") from error
    if not isinstance(raw, list) or not raw:
        raise SystemExit(f"--locks-file {path} must hold a non-empty JSON array")

    locks: list[str] = []
    for position, entry in enumerate(raw, start=1):
        text = entry.get("text") if isinstance(entry, dict) else entry
        if not isinstance(text, str) or not text.strip():
            raise SystemExit(f"--locks-file {path} entry {position} has no usable text")
        locks.append(text.strip())
    return locks


def build_sheet_prompt(locks: list[str], columns: int, rows: int, derived: bool, extra: str) -> str:
    """The concept-sheet prompt.

    Identity locks are numbered and row-major because that numbering is the only
    thing tying a human's "I choose cell-04" to the concept they meant. The order
    is stated twice on purpose -- once as a layout instruction, once as the
    numbering of the locks themselves.
    """
    numbered = "\n".join(f"  {position}. {text}" for position, text in enumerate(locks, start=1))
    if derived:
        roles = (
            "Image 1 is the identity reference. Image 2 is the house-style reference. "
            "Image 2 wins on any conflict. Do not edit or reproduce either image."
        )
    else:
        roles = (
            "Image 1 is the house-style reference and wins on any conflict. "
            "Do not edit or reproduce it."
        )

    return (
        f"Use case: stylized-concept\n"
        f"Asset type: concept sheet for choosing a Geist Pet\n"
        f"Input images: {roles}\n"
        f"Primary request: Draw {len(locks)} different Geist Pet mascot concepts, exactly one per "
        f"cell, on an invisible {columns}-column by {rows}-row grid read left to right, top to "
        f"bottom. Translate each concept into a compact rounded non-human Geist companion, never "
        f"a miniature figure of a source character.\n"
        f"Shared Geist identity: {HOUSE_FORM}\n"
        f"Identity locks, one per cell in that exact order:\n{numbered}\n"
        f"Scene/backdrop: plain warm off-white paper; invisible grid; generous negative space "
        f"between cells; no dividers, no rules, no frames, no cell borders\n"
        f"Style/medium: flat colour fills, even outline weight, no gradients, no texture, no "
        f"shadows, no gloss, no screentone, no painterly marks, no 3D\n"
        f"Composition/framing: exactly one centred full-body mascot per cell, equal visual scale "
        f"and equal baseline across every cell, ample padding inside each cell, nothing cropped, "
        f"no mascot crossing into a neighbouring cell, front or soft three-quarter view\n"
        f"Constraints: every mascot keeps the shared Geist identity above; cells may differ in "
        f"silhouette, headwear, one attached prop and colour accents, and may differ in nothing "
        f"else\n"
        f"Avoid: any text, letters, numbers, labels, captions or watermarks anywhere on the "
        f"image; {NEVER_TRANSFERS}\n"
        f"{extra}"
    ).strip()


def build_base_prompt(bundle: Path, variant_intent: str, from_cell: bool, derived: bool, extra: str) -> str:
    """The canonical-base prompt: one Pet, at sprite scale, as the identity lock."""
    manifest = read_manifest(bundle / "character-bible.md")
    if from_cell:
        subject = (
            "Image 1 is an approved concept cell for this Pet. Redraw that exact character at "
            "sprite scale, keeping its silhouette, headwear, props, colours and expression."
        )
    elif derived:
        subject = (
            "Image 1 is the identity reference. Translate it into a Geist companion rather than "
            "drawing a miniature figure of it."
        )
    else:
        subject = "Invent the Pet described below as a Geist companion."

    house_role = "Image 2 is the house-style reference and wins on any conflict."
    return (
        f"Use case: stylized-concept\n"
        f"Asset type: canonical base for a Geist Pet -- the identity lock every later frame is "
        f"drawn against\n"
        f"Input images: {subject} {house_role} Do not edit or reproduce either image.\n"
        f"Shared Geist identity: {HOUSE_FORM}\n"
        f"Variant intent: {variant_intent}\n"
        f"Composition/framing: one centred full-body character, front or soft three-quarter view, "
        f"the whole body and every prop well inside the canvas with an even clear margin of at "
        f"least 15% of the canvas on all four sides, one character only, and no text, letters "
        f"or numbers anywhere.\n"
        f"Keep it simple enough to survive redrawing in nine animation states at 192x208: a base "
        f"that only reads at full resolution will lose its identity by the third state."
        f"{manifest.prompt_block()}\n"
        f"Avoid: {NEVER_TRANSFERS}\n"
        f"{extra}"
    ).strip()


def write_sheet_packet(
    bundle: Path,
    candidate_id: str,
    sheet: Image.Image,
    locks: list[str],
    columns: int,
    rows: int,
    aspect_ratio: str,
    prompt: str,
    provenance: list[dict[str, Any]],
    input_images: list[dict[str, str]],
) -> Path:
    """Write the concept-sheet packet.

    Per-cell verdicts start `pending` rather than absent, so a sheet that reaches
    a human without being pre-screened is visibly unscreened instead of quietly
    looking fine. `grid` is what the cropper reads to cut cells, so it records
    what was actually requested.
    """
    packet = bundle / "sources" / "candidates" / candidate_id
    packet.mkdir(parents=True, exist_ok=True)
    sheet.save(packet / "candidate.png")

    (packet / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    (packet / "inputs.json").write_text(
        json.dumps({"input_images": input_images, "mode": "External Image Provider"}, indent=2) + "\n",
        encoding="utf-8",
    )

    cells = [
        {
            "cell_id": cell_id(position),
            "status": "pending",
            "checks": {},
            "notes": "",
        }
        for position in range(1, len(locks) + 1)
    ]
    ids = ", ".join(cell["cell_id"] for cell in cells)
    (packet / "candidate-context.json").write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "target": {
                    "kind": "concept-sheet",
                    "destination": f"sources/candidates/{candidate_id}/cells/",
                },
                "generated_file": f"sources/candidates/{candidate_id}/candidate.png",
                "prompt_file": f"sources/candidates/{candidate_id}/prompt.md",
                "prompt_text": prompt,
                "generation_mode": "External Image Provider",
                "grid": {
                    "columns": columns,
                    "rows": rows,
                    "cell_count": len(locks),
                    "aspect_ratio": aspect_ratio,
                },
                "identity_locks": [
                    {"cell_id": cell_id(position), "text": text}
                    for position, text in enumerate(locks, start=1)
                ],
                "provenance": provenance,
                "agent_pre_screen": {"status": "pending", "cells": cells},
                "human_review": {
                    "status": "pending",
                    "question": f"Choose one or more cells by id from the concept sheet: {ids}.",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return packet


def write_base_packet(
    bundle: Path,
    candidate_id: str,
    raw: Image.Image,
    sprite: Image.Image,
    transform: CellTransform,
    prompt: str,
    provenance: dict[str, Any],
    input_images: list[dict[str, str]],
    variant_intent: str,
) -> Path:
    """Write one canonical-base candidate.

    Both scales are kept. `candidate.png` is what the human judges and what gets
    promoted; `sprite-scale.png` is the same art at 192x208, which is the size
    the naming test actually has to survive.
    """
    packet = bundle / "sources" / "candidates" / candidate_id
    packet.mkdir(parents=True, exist_ok=True)
    raw.save(packet / "candidate.png")
    sprite.save(packet / "sprite-scale.png")
    sprite.save(packet / "contact-sheet.png")

    (packet / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    (packet / "inputs.json").write_text(
        json.dumps(
            {
                "input_images": input_images,
                "mode": "External Image Provider",
                "cell_transform": transform.as_dict(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (packet / "candidate-context.json").write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "target": {
                    "kind": "canonical-base",
                    "destination": "sources/canonical-base.png",
                },
                "generated_file": f"sources/candidates/{candidate_id}/candidate.png",
                "prompt_file": f"sources/candidates/{candidate_id}/prompt.md",
                "prompt_text": prompt,
                "generation_mode": "External Image Provider",
                "cell_transform": transform.as_dict(),
                "provenance": [provenance],
                "variant_intent": variant_intent,
                "agent_pre_screen": {"status": "pending", "checks": {}, "notes": ""},
                "human_review": {
                    "status": "pending",
                    "question": "Choose one canonical-base candidate for sources/canonical-base.png.",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return packet


def stash_frame(
    bundle: Path,
    candidate_id: str,
    index: int,
    raw: Image.Image,
    cell: Image.Image,
    record: dict[str, Any],
) -> None:
    """Put one frame on disk the moment the provider answers for it.

    Frames used to land only when `write_packet` ran, which is after the whole
    state. Anything that stopped the run in between -- a ceiling, a Ctrl-C, an
    agent killing the run to fix a defect it had just seen -- destroyed every
    frame already drawn and billed. That cost 3 paid `failed` frames on
    FarWatcher for nothing.

    Both forms are kept, because they answer different questions. The cell is
    what a reviewer looks at. The **raw** provider frame is what a resumed run
    has to have: the final registration rebuilds every cell from the raws so the
    art is resampled once rather than twice, and a cell cannot be un-fitted back
    into one.

    `provenance.jsonl` is appended per frame for the same reason `geist_spend`
    appends a ledger line per call rather than per packet -- a run that dies
    still has to be able to say what it bought.
    """
    packet = bundle / "sources" / "candidates" / candidate_id
    frame_dir = packet / "frames"
    raw_dir = packet / "raw"
    frame_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    cell.save(frame_dir / f"{index:02d}.png")
    raw.save(raw_dir / f"{index:02d}.png")
    with (packet / "provenance.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")


def write_packet(
    bundle: Path,
    candidate_id: str,
    state: str,
    frames: list[tuple[int, Image.Image]],
    prompt: str,
    provenance: list[dict[str, Any]],
    transform: CellTransform,
    variant_intent: str,
    inputs: dict[str, Any] | None = None,
    generation_mode: str = "External Image Provider",
) -> Path:
    packet = bundle / "sources" / "candidates" / candidate_id
    frame_dir = packet / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    for index, image in frames:
        image.save(frame_dir / f"{index:02d}.png")

    sheet = Image.new("RGBA", (CELL_WIDTH * len(frames), CELL_HEIGHT), (0, 0, 0, 0))
    for column, (_index, image) in enumerate(frames):
        sheet.alpha_composite(image, (column * CELL_WIDTH, 0))
    sheet.save(packet / "contact-sheet.png")
    frames[0][1].save(packet / "candidate.png")

    (packet / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    (packet / "inputs.json").write_text(
        json.dumps(
            inputs
            or {
                "input_images": ["sources/canonical-base.png", "previous frame of this action"],
                "mode": "External Image Provider",
                "cell_transform": transform.as_dict(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (packet / "candidate-context.json").write_text(
        json.dumps(
            {
                "candidate_id": candidate_id,
                "target": {
                    "kind": "sprite-action",
                    "state": state,
                    "destination": f"frames/{state}/",
                    "frames": [index for index, _image in frames],
                },
                "generated_file": f"sources/candidates/{candidate_id}/contact-sheet.png",
                "prompt_file": f"sources/candidates/{candidate_id}/prompt.md",
                "prompt_text": prompt,
                "generation_mode": generation_mode,
                "cell_transform": transform.as_dict(),
                "provenance": provenance,
                "variant_intent": variant_intent,
                "agent_pre_screen": {"status": "pending", "checks": {}, "notes": ""},
                "human_review": {
                    "status": "pending",
                    "question": f"Choose one {state} variant for frames/{state}/.",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return packet


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


# How many frames a state draws before the mechanical checks get a veto.
#
# Every failed run on the Karate Crown Guardian build was five to eight frames
# of a defect that was already in frame 0 or frame 1 -- and it cost the whole
# state anyway, because nothing looked until the state was finished. Two frames
# is enough to see clipping, an unkeyed background, and a body that changes
# size, which are the three that repeat.
#
# The size check is the exception and no longer expires with this window. It is
# the one check whose evidence only accumulates: a state cannot drift on frame 1
# because there is nothing to drift from. `review` drifted to 1.46x across frames
# 2-5 on FuseSprout with nothing stopping it, because the veto had already gone
# quiet. Measuring is free; only drawing costs.
PREFLIGHT_FRAMES = 2

# How far past its declared `SIZE_BUDGET` a frame may sit, in LINEAR size against
# the running median, before it stops being the same character moving and starts
# being a different drawing.
#
# The veto is deliberately looser than the budget, because the budget is now
# ENFORCED for free. `geist_registration.normalise_size` scales a stray frame
# back onto the state median at no cost, so vetoing everything outside the budget
# would burn a state to avoid a resample. What the slack marks is where a
# resample stops being cheap: past it the correction is large enough to soften
# the outline visibly, and the frame is better redrawn than rescued.
#
# 1.18 keeps the case this check was built on. A `waiting` repair came back at
# 0.54x frame 0's bbox area -- 0.73 linear -- and was killed at frame 1, saving
# four frames of spend. It is still killed here. The four states that drifted
# 1.32x to 1.46x in AREA spread sit at about 1.10 linear against their median,
# inside the slack, and are now silently normalised instead of redrawn: that is
# the $0.33 the report priced.
PREFLIGHT_SIZE_SLACK = 1.18


def size_allowance(state: str) -> float:
    """The linear ratio to the running median at which pre-flight vetoes.

    `SIZE_BUDGET` is declared as a SPREAD -- largest area over smallest -- so a
    frame may sit `budget ** 0.25` from the median in linear size before it has
    used the whole allowance, and the slack is what it may have on top.
    """
    return registration.size_budget_for(state) ** 0.25 * PREFLIGHT_SIZE_SLACK


def frame_problems(
    cell: Image.Image,
    fit: dict[str, Any],
    state: str,
    areas: list[int],
    base_components: int | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Mechanical defects in one finished cell, split by how hard they stop a run.

    Returns `(fatal, preflight, standing)`. **Fatal** ends the state at whatever
    frame it appears on. **Pre-flight** ends it only while the veto window is
    still open, so a marginal frame late in a state stays reportable and
    deterministically repairable instead of throwing away the frames already paid
    for. **Standing** never expires: it is the band where the free repair would
    itself damage the art, so a late frame there is not rescuable and the
    remaining calls would buy nothing.

    `areas` is every alpha area drawn so far in this state INCLUDING this cell,
    and the ruler is their median. Frame 0 used to be the ruler, which
    contradicted the principle `geist_registration` states in its own docstring
    -- *a frame 0 is a pose; a median over the state is the Pet* -- and left the
    generator registering against one thing and judging drift against another.
    Alpha area rather than the bounding rectangle, for the same reason: a raised
    arm adds a few percent of area and fifteen percent of bbox height.

    Nothing here needs a human or a provider call. What it cannot see is
    anatomy: a state that draws legs fits, keys out and holds its area
    perfectly. Legs are the prompt's job — `geist_house.LEGLESS_BODY`.
    """
    fatal: list[str] = []
    preflight: list[str] = []
    standing: list[str] = []

    # Fatal, because the background is baked into the art. On frame 0 it is
    # worse than one bad frame: alpha_bbox then covers the whole canvas, the
    # derived scale shrinks that canvas into one cell, and every remaining frame
    # of the state inherits the wrong scale.
    if not alpha_is_real(cell):
        fatal.append("background did not key out: the cell is largely opaque or its border is not clear")

    if not fit["fits"]:
        preflight.append(f"body reaches outside safe padding, bbox {fit.get('bbox')}")

    # A detached mark is an extra connected component, and that is the whole
    # check. `running-right` frame 0 came back with 2-4 blue speed streaks
    # floating beside the Pet; pre-flight passed it because streaks break no
    # geometry and key out fine, and 13 frames across two states were drawn and
    # discarded for $0.29 -- the largest single line of waste on FarWatcher. The
    # prompt that caused it is fixed, but a prompt fix is not a check, and this
    # runs on art that is already paid for.
    if base_components:
        found = component_count(cell)
        if found > base_components:
            preflight.append(
                f"{found} separate marks in the cell against {base_components} in the canonical base: "
                f"{found - base_components} floating beside the Pet"
            )

    if len(areas) >= 2:
        median = statistics.median(areas)
        area = areas[-1]
        if median > 0 and area > 0:
            linear = (area / median) ** 0.5
            allowed = size_allowance(state)
            if not (1 / allowed) <= linear <= allowed:
                standing.append(
                    f"body is {linear:.2f}x the state's running median size, past the "
                    f"{allowed:.2f}x this state's SIZE_BUDGET allows"
                )
    return fatal, preflight, standing


def parse_frame_range(spec: str | None, frame_count: int) -> list[int]:
    if not spec:
        return list(range(frame_count))
    wanted: list[int] = []
    for chunk in spec.split(","):
        if "-" in chunk:
            low, high = chunk.split("-", 1)
            wanted.extend(range(int(low), int(high) + 1))
        else:
            wanted.append(int(chunk))
    return [index for index in sorted(set(wanted)) if 0 <= index < frame_count]


def parse_grid(spec: str | None, cells: int) -> tuple[int, int, str]:
    """The grid for this sheet: the table's, unless the caller overrode it."""
    columns, rows, aspect_ratio = layout_for(cells)
    if not spec:
        return columns, rows, aspect_ratio
    try:
        left, right = spec.lower().split("x", 1)
        columns, rows = int(left), int(right)
    except ValueError as error:
        raise SystemExit(f"--grid takes COLUMNSxROWS, for example 3x2; got '{spec}'") from error
    if columns * rows < cells:
        raise SystemExit(f"--grid {spec} has {columns * rows} cells, too few for {cells} concepts")
    return columns, rows, aspect_ratio


def run_concept_sheet(args: argparse.Namespace, bundle: Path, config: ProviderConfig, guard: SpendGuard) -> dict[str, Any]:
    """One call, many concepts, no canonical base.

    This runs before an identity lock exists, so the house-style reference is the
    only thing defending the house form. A derived sheet adds the source as
    Image 1; an original cast sends no Image 1 at all, because there is no source
    to hold on to.
    """
    locks = read_locks(Path(args.locks_file).expanduser().resolve())
    columns, rows, aspect_ratio = parse_grid(args.grid, len(locks))
    if args.cells and args.cells != len(locks):
        raise SystemExit(
            f"--cells {args.cells} disagrees with --locks-file, which holds {len(locks)} locks. "
            f"The lock list is the cell list; drop --cells or fix the file."
        )

    input_images: list[dict[str, str]] = []
    references: list[str] = []
    derived = bool(args.identity_image)
    if derived:
        identity = Path(args.identity_image).expanduser().resolve()
        if not identity.is_file():
            raise SystemExit(f"--identity-image {identity} does not exist")
        references.append(image_reference(identity))
        input_images.append({"path": str(identity), "role": "identity reference"})

    house = house_style_path(bundle)
    references.append(image_reference(house))
    input_images.append({"path": str(house), "role": "house-style reference"})

    candidate_id = args.candidate_id or "concept-sheet-01"
    if guard.ledger is not None:
        guard.ledger.candidate_id = candidate_id

    prompt = build_sheet_prompt(locks, columns, rows, derived, args.extra_prompt)
    sheet, record = generate_frame(
        opaque(config, aspect_ratio), prompt, references, guard, require_alpha=False
    )
    record["reference_count"] = len(references)

    packet = write_sheet_packet(
        bundle, candidate_id, sheet, locks, columns, rows, aspect_ratio, prompt, [record], input_images
    )
    return {
        "action": CONCEPT_SHEET,
        "candidate_id": candidate_id,
        "packet": str(packet),
        "grid": {"columns": columns, "rows": rows, "cell_count": len(locks), "aspect_ratio": aspect_ratio},
        "sheet_size": list(sheet.size),
        "derived": derived,
        "next": (
            f"pre-screen every cell and write its verdict into candidate-context.json, then render "
            f"qa/concept-sheet-review.html and ask the human to choose cell ids. Redraw the sheet "
            f"only if fewer than {MIN_PASSING_CELLS} cells pass."
        ),
    }


def run_mirror(args: argparse.Namespace, bundle: Path) -> dict[str, Any]:
    """`running-left` from the approved `running-right` row. No provider call.

    The skill has always said `running-left` is the same cycle flipped, and
    nothing enforced it: `running-left` is an ordinary member of FRAME_COUNTS,
    so `--action running-left` drew eight frames through the provider and no
    one was told. Drawing it independently also loses the guarantee the flip
    gives for free -- that the two directions are the same character.
    """
    source_dir = bundle / "frames" / MIRROR_SOURCE
    frame_count = FRAME_COUNTS[MIRROR_SOURCE]
    if frame_count != FRAME_COUNTS[MIRROR_OF]:
        raise SystemExit(
            f"{MIRROR_SOURCE} has {frame_count} frames and {MIRROR_OF} wants "
            f"{FRAME_COUNTS[MIRROR_OF]}; a mirror cannot bridge that. Draw {MIRROR_OF} with "
            f"--independent-left, or fix the row spec in geist_grid.py."
        )
    sources = [source_dir / f"{index:02d}.png" for index in range(frame_count)]
    missing = [path.name for path in sources if not path.is_file()]
    if missing:
        raise SystemExit(
            f"{MIRROR_OF} mirrors the approved {MIRROR_SOURCE} row, and "
            f"frames/{MIRROR_SOURCE}/ is missing {', '.join(missing)}. Approve {MIRROR_SOURCE} "
            f"first, or pass --independent-left to draw {MIRROR_OF} through the provider instead."
        )

    produced: list[tuple[int, Image.Image]] = []
    for index, path in enumerate(sources):
        with Image.open(path) as opened:
            flipped = opened.convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
        produced.append((index, flipped))

    candidate_id = f"{MIRROR_OF}-{args.variant}"
    operation = f"horizontal flip of every approved frames/{MIRROR_SOURCE}/NN.png"
    packet = write_packet(
        bundle,
        candidate_id,
        MIRROR_OF,
        produced,
        operation,
        [{"frame": index, "operation": "FLIP_LEFT_RIGHT", "source": f"frames/{MIRROR_SOURCE}/{index:02d}.png"}
         for index, _image in produced],
        CellTransform(scale=1.0, offset_x=0, offset_y=0, source_size=(CELL_WIDTH, CELL_HEIGHT)),
        operation,
        inputs={
            "input_images": [f"frames/{MIRROR_SOURCE}/{index:02d}.png" for index in range(frame_count)],
            "mode": "Deterministic",
            "operation": "PIL Image.FLIP_LEFT_RIGHT",
        },
        generation_mode="Deterministic",
    )
    return {
        "action": MIRROR_OF,
        "candidate_id": candidate_id,
        "packet": str(packet),
        "frames": [index for index, _image in produced],
        "frames_requested": frame_count,
        "mirrored_from": MIRROR_SOURCE,
        "provider_calls": 0,
        "spend": {"images": 0, "cost_usd": 0.0},
        "next": (
            f"render qa/{MIRROR_OF}-review.html and get the mirror approved like any other "
            f"candidate. It is a deterministic operation, so a failure here is a "
            f"{MIRROR_SOURCE} problem."
        ),
    }


def run_canonical_base(args: argparse.Namespace, bundle: Path, config: ProviderConfig, guard: SpendGuard) -> dict[str, Any]:
    """The identity lock itself. No canonical base is attached, because this is it."""
    from_cell = bool(args.cell_image)
    input_images: list[dict[str, str]] = []
    references: list[str] = []

    if from_cell:
        cell = Path(args.cell_image)
        cell = cell if cell.is_absolute() else (bundle / cell)
        cell = cell.expanduser().resolve()
        if not cell.is_file():
            raise SystemExit(f"--cell-image {cell} does not exist; crop it with crop_gallery_cells.py first")
        references.append(image_reference(cell))
        input_images.append({"path": str(cell), "role": "approved concept cell"})
    elif args.identity_image:
        identity = Path(args.identity_image).expanduser().resolve()
        if not identity.is_file():
            raise SystemExit(f"--identity-image {identity} does not exist")
        references.append(image_reference(identity))
        input_images.append({"path": str(identity), "role": "identity reference"})

    house = house_style_path(bundle)
    references.append(image_reference(house))
    input_images.append({"path": str(house), "role": "house-style reference"})

    packets: list[str] = []
    candidate_ids: list[str] = []
    misfits: list[dict[str, Any]] = []
    allowances: dict[str, Any] = {}
    for offset in range(args.variants):
        letter = chr(ord("a") + offset)
        if guard.ledger is not None:
            guard.ledger.candidate_id = f"canonical-base-{letter}"
        intent = args.variant_intent if args.variants == 1 else f"{args.variant_intent} (variant {letter.upper()})"
        prompt = build_base_prompt(bundle, intent, from_cell, bool(args.identity_image), args.extra_prompt)
        raw, record = generate_frame(config, prompt, references, guard)

        # Each base variant is its own character, so each gets its own transform.
        # The shared-transform rule exists to stop one animation run's poses from
        # rescaling each other; it has nothing to say across separate candidates.
        transform = CellTransform.from_reference(raw, args.safe_padding, args.motion_headroom)
        sprite = transform.apply(raw)
        fit = transform.fit_report(sprite, args.safe_padding)
        if not fit["fits"]:
            misfits.append({"candidate": f"canonical-base-{letter}", **fit})

        record["reference_count"] = len(references)
        record["fits_safe_padding"] = fit["fits"]
        # What this silhouette will have to move inside for all 57 later frames.
        # A base tight on both axes fights every motion state, and this review is
        # the last moment when swapping it costs one call instead of a state.
        record["growth_allowance"] = transform.growth_allowance(sprite, args.safe_padding)
        candidate_id = f"canonical-base-{letter}"
        packet = write_base_packet(
            bundle, candidate_id, raw, sprite, transform, prompt, record, input_images, intent
        )
        candidate_ids.append(candidate_id)
        packets.append(str(packet))
        allowances[candidate_id] = record["growth_allowance"]

    return {
        "action": CANONICAL_BASE,
        "candidate_ids": candidate_ids,
        "packets": packets,
        "from_approved_cell": from_cell,
        "candidates_outside_safe_padding": misfits,
        "motion_headroom": round(args.motion_headroom, 4),
        "growth_allowance": allowances,
        "next": (
            "pre-screen each candidate, then render qa/canonical-base-review.html and ask the "
            "human to choose one id before copying it to sources/canonical-base.png. Read "
            "growth_allowance while choosing: it is how far each silhouette can grow inside the "
            "cell, and a base tight on both axes will fight all 57 later frames."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", help="Path to PetName.pet source bundle")
    parser.add_argument("--verify-model", metavar="MODEL_ID",
                        help="Settle whether a model id actually works, with one live "
                             "billable request. The catalog listing is incomplete and "
                             "must not be used for this. Exits after reporting.")
    parser.add_argument("--action", choices=ACTIONS,
                        help="Phase to draw: concept-sheet, canonical-base, or a sprite action")
    parser.add_argument("--state", choices=sorted(FRAME_COUNTS),
                        help="Deprecated alias for --action, kept so existing commands keep working")
    parser.add_argument("--variant", default="a", help="Variant letter; becomes part of the candidate id")
    parser.add_argument("--variant-intent", default="restrained, readable motion", help="How this variant should move")
    parser.add_argument("--frames", help="Frame indices to generate, e.g. 0-5 or 2,4; defaults to the whole state")
    parser.add_argument("--model", choices=KNOWN_MODELS, help="Override the model in imagegen.json")
    parser.add_argument("--max-images", type=int,
                        help="Hard ceiling on provider calls this run; defaults per action")
    parser.add_argument("--max-cost-usd", type=float,
                        help="Runaway-loop guardrail, not a spend control. Defaults per action; "
                             "obtain authority for the total run ceiling before calling the "
                             "provider. The provider-side credit limit remains the final hard "
                             "ceiling outside this process.")
    parser.add_argument("--mode", choices=MODES, default=MODE_SUPERVISED,
                        help="Decision mode this action belongs to. 'supervised' means a human picks "
                             "the candidate; 'auto' means Quick or Full Automation picks it. Recorded on "
                             "every ledger line, so a Pet whose frames nobody chose stays visible "
                             "as one months later.")
    parser.add_argument("--safe-padding", type=int, default=6)
    parser.add_argument("--motion-headroom", type=float, default=MOTION_HEADROOM,
                        help="Fraction of the safe box the first frame leaves empty so later "
                             "frames of the same state have room to grow. The transform is built "
                             "from frame 0 and applied unchanged to the rest, so a tight fit here "
                             "clips every frame that moves. Raise it for a silhouette that swings "
                             # argparse %-interpolates help text, so a literal percent sign has
                             # to arrive doubled or --help raises instead of printing.
                             f"a long way; default {MOTION_HEADROOM * 100:.0f}%%.")
    parser.add_argument("--extra-prompt", default="", help="Appended to every prompt")
    parser.add_argument("--base-url", help="Provider base URL. Defaults to OPENROUTER_BASE_URL, "
                        "then OpenRouter. Point at a broker or a local mock to keep the "
                        "credential out of this process.")

    sheet_group = parser.add_argument_group("concept-sheet")
    sheet_group.add_argument("--locks-file", help="JSON array of identity locks, one per cell, row-major")
    sheet_group.add_argument("--cells", type=int, help="Cell count; must agree with --locks-file")
    sheet_group.add_argument("--grid", help="Override the grid as COLUMNSxROWS, for example 3x2")
    sheet_group.add_argument("--identity-image", help="Image 1 for a derived sheet or base; omit for an original cast")
    sheet_group.add_argument("--candidate-id", help="Packet id; defaults to concept-sheet-01")

    parser.add_argument("--independent-left", action="store_true",
                        help=f"Draw {MIRROR_OF} through the provider instead of mirroring the "
                             f"approved {MIRROR_SOURCE} row. Costs a full state and drops the "
                             f"guarantee the flip gives free -- that both directions are the same "
                             f"character. Use it only when a human asked for independent "
                             f"left-facing art.")

    base_group = parser.add_argument_group("canonical-base")
    base_group.add_argument("--cell-image", help="Approved concept cell to render at sprite scale, as Image 1")
    base_group.add_argument("--variants", type=int,
                            help="How many base candidates to draw; defaults to 1 after a sheet, 3 without one")

    args = parser.parse_args()

    set_base_url(args.base_url)

    if args.verify_model:
        api_key()
        verify_model_live(args.verify_model)
        return

    if args.action and args.state and args.action != args.state:
        raise SystemExit(f"--action {args.action} and --state {args.state} disagree; --state is just an alias")
    action = args.action or args.state
    if args.state and not args.action:
        print("--state is deprecated; use --action instead", file=sys.stderr)
    if not args.bundle or not action:
        raise SystemExit("bundle and --action are required unless --verify-model is given")

    bundle = Path(args.bundle).expanduser().resolve()

    # The flip needs no credential, no config and no ceiling, so it runs before
    # any of that is resolved.
    if action == MIRROR_OF and not args.independent_left:
        print(json.dumps({"ok": True, "mode": "Deterministic", "decision_mode": args.mode,
                          **run_mirror(args, bundle)}, indent=2))
        return

    if action == CONCEPT_SHEET and not args.locks_file:
        raise SystemExit(
            "--action concept-sheet needs --locks-file: one identity lock per cell, row-major. "
            "A sheet drawn without written locks has nothing tying cell-04 to a concept."
        )
    if args.variants is None:
        # A sheet already showed the human their options and they already chose,
        # so the base run just renders that choice at sprite scale. With no sheet,
        # nothing has previewed this gate yet, so it owes the normal three.
        args.variants = 1 if args.cell_image else 3
    if args.variants < 1:
        raise SystemExit("--variants must be at least 1")

    default_images, default_cost = ACTION_CEILINGS.get(action, FRAME_CEILINGS)
    if default_images is None:
        default_images = args.variants * 2  # room for one transparency retry each
    max_images = args.max_images if args.max_images is not None else default_images
    max_cost = args.max_cost_usd if args.max_cost_usd is not None else default_cost

    config = load_config(bundle, args.model)
    api_key()  # fail before any work when the environment is not set up
    ledger = SpendLedger(
        model=config.model,
        mode=args.mode,
        action=action,
        bundle=bundle,
        provider=config.provider,
        endpoint=endpoint(),
    )
    guard = SpendGuard(max_images, max_cost, ledger)

    if action in PRE_FRAME_ACTIONS:
        runner = run_concept_sheet if action == CONCEPT_SHEET else run_canonical_base
        result = runner(args, bundle, config, guard)
        print(
            json.dumps(
                {"ok": True, "mode": "External Image Provider", "decision_mode": args.mode,
                 "model": config.model, **result, "spend": guard.as_dict(),
                 "ledger": ledger.as_dict()},
                indent=2,
            )
        )
        for warning in ledger.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        return

    frame_count = FRAME_COUNTS[action]
    indices = parse_frame_range(args.frames, frame_count)

    # Only the frame path needs the identity lock on disk. The two actions above
    # run before it exists -- one of them is what produces it.
    canonical = bundle / "sources" / "canonical-base.png"
    if not canonical.is_file():
        raise SystemExit("sources/canonical-base.png is the identity lock; approve one before generating frames")
    canonical_uri = image_reference(canonical)

    # Two facts about this Pet, read once from the identity lock, that every
    # frame of every state needs and that nothing used to ask for: which backdrop
    # this Pet can safely be keyed off, and how many separate marks it is
    # legitimately made of.
    with Image.open(canonical) as opened:
        base_image = opened.convert("RGBA")
        chroma = choose_chroma_key(base_image)
        base_components = component_count(base_image)
    if not chroma["safe"] and ALPHA_PATHS.get(config.model) in {"chroma", "chroma-bare"}:
        print(
            f"warning: the best backdrop for this Pet is {chroma['name']}, and it is only "
            f"{chroma['clearance']} from the Pet's nearest colour against a key tolerance of "
            f"{KEY_TOLERANCE}. Frames may key out with holes in them. Consider a canonical base "
            f"whose palette leaves more room, or a model with a native alpha path.",
            file=sys.stderr,
        )

    candidate_id = f"{action}-{args.variant}"
    ledger.candidate_id = candidate_id
    produced: list[tuple[int, Image.Image]] = []
    raws: list[tuple[int, Image.Image]] = []
    provenance: list[dict[str, Any]] = []
    transform: CellTransform | None = None
    previous: Image.Image | None = None
    first_prompt = ""
    misfits: list[dict[str, Any]] = []

    areas: list[int] = []
    aborted: dict[str, Any] | None = None

    for position, index in enumerate(indices):
        ledger.frame = index
        references = [canonical_uri]
        if previous is not None:
            references.append(data_uri(previous))
        elif index > 0:
            # The previous frame, wherever the previous frame actually is. A
            # resumed run has no `previous` in memory, and its earlier frames are
            # not in `frames/` either -- they are unapproved, sitting in this
            # candidate's own packet where the interrupted run stashed them.
            # Reading the packet first is what makes `--frames 3-7` continue a
            # state rather than restart its identity chain from the base alone.
            for earlier in (
                bundle / "sources" / "candidates" / candidate_id / "frames" / f"{index - 1:02d}.png",
                bundle / "frames" / action / f"{index - 1:02d}.png",
            ):
                if earlier.is_file():
                    references.append(image_reference(earlier))
                    break

        prompt = build_prompt(bundle, action, index, frame_count, args.variant_intent, args.extra_prompt)
        first_prompt = first_prompt or prompt
        raw, record = generate_frame(config, prompt, references, guard, chroma_key=chroma["key"])

        # A provisional transform, good enough to judge a frame by and thrown
        # away once the state is complete. It exists so the pre-flight veto below
        # still fires on frame 2 rather than after eight paid calls -- the real
        # scale needs every frame of the state and cannot be known this early.
        if transform is None:
            transform = CellTransform.from_reference(raw, args.safe_padding, args.motion_headroom)
        cell = transform.apply(raw)
        raws.append((index, raw))

        fit = transform.fit_report(cell, args.safe_padding)
        if not fit["fits"]:
            misfits.append({"frame": index, **fit})

        # Measured on the RAW provider frame, not on the fitted cell. The cell
        # was fitted by a provisional transform derived from frame 0, so a cell
        # area is partly a statement about frame 0 -- which is the dependence
        # this check exists to remove. The raw frame is what the provider
        # actually drew, and it is also what the final registration rebuilds
        # from, so drift is measured on the same pixels that will be corrected.
        anchor = registration.measure(raw)
        if anchor is not None:
            areas.append(anchor.area)

        record["frame"] = index
        record["reference_count"] = len(references)
        record["fits_safe_padding"] = fit["fits"]
        provenance.append(record)
        produced.append((index, cell))
        previous = cell

        # A frame lands on disk the moment the provider answers for it. It used
        # to land when the whole state finished, so stopping a run to fix a
        # defect threw away every frame already paid for -- 3 `failed` frames on
        # FarWatcher, drawn, billed and never written. This is the same argument
        # `geist_spend` already makes for appending a ledger line at the answer
        # rather than at the packet: the art deserves what the receipt gets.
        # The registered rewrite below replaces these; until it runs, the raw
        # draw is what `--frames` can resume from.
        stash_frame(bundle, candidate_id, index, raw, cell, record)

        # The veto, and the whole point of drawing in this order: a prompt that
        # cannot produce a usable frame costs two calls instead of eight.
        fatal, preflight, standing = frame_problems(cell, fit, action, areas, base_components)
        if fatal or standing or (preflight and position < PREFLIGHT_FRAMES):
            aborted = {
                "frame": index,
                "problems": fatal + standing + preflight,
                "stopped_by": "fatal" if fatal else ("size-budget" if standing else "pre-flight"),
            }
            break

    assert transform is not None

    # The state is complete, so the real ruler can finally be applied. The
    # provisional transform above answered "is this frame worth paying for"; this
    # answers "how big is this Pet and where does it sit", and only the finished
    # state can answer it -- a median over every frame is what averages the pose
    # out, and a single frame 0 is the pose.
    #
    # Rebuilt from the RAW provider frames, not from the provisional cells, so
    # the art is resampled once rather than twice.
    registered: dict[str, Any] = {}
    if aborted is None and raws:
        with Image.open(canonical) as opened:
            target = registration.ruler(opened.convert("RGBA"), args.safe_padding, args.motion_headroom)
        anchors = [registration.measure(raw) for _index, raw in raws]
        if all(anchor is not None for anchor in anchors):
            scale = registration.state_scale(anchors, target, args.safe_padding, args.motion_headroom)
            budget = registration.budget_for(action)
            offset_x, offset_y = registration.placement(anchors, target, scale, budget)
            cells = [registration.apply(raw, scale, offset_x, offset_y) for _index, raw in raws]
            drawn_spread = registration.size_spread(cells)
            # Size before position, because normalising a frame's size moves the
            # pixels the translation is about to measure. `state_scale` above
            # already decided how big this state is against the Pet; this decides
            # whether the state holds that size across its own frames, which is a
            # different question with a different cause and needed a second pass.
            cells, resized = registration.normalise_size(cells, action)
            cells, moved = registration.register(cells, action, target)
            produced = [(index, cell) for (index, _raw), cell in zip(raws, cells)]
            transform = CellTransform(
                scale=scale,
                offset_x=offset_x,
                offset_y=offset_y,
                source_size=raws[0][1].size,
                headroom=args.motion_headroom,
            )
            # The provisional transform's verdicts described pixels that no
            # longer exist, so the fit is re-read against what actually shipped.
            misfits = []
            for index, cell in produced:
                fit = transform.fit_report(cell, args.safe_padding)
                if not fit["fits"]:
                    misfits.append({"frame": index, **fit})
            final = [registration.measure(cell) for _index, cell in produced]
            registered = {
                "anchor_x": target.x,
                "anchor_base": target.base,
                "budget": {"horizontal": budget[0], "vertical": budget[1]},
                "size_budget": registration.size_budget_for(action),
                # As drawn, then as shipped. The pair is the evidence: a large
                # first number and a small second one is this pass doing its job,
                # and two large numbers on a budgeted state is the artwork.
                "size_spread_drawn": round(drawn_spread, 4),
                "size_spread_shipped": round(
                    registration.size_spread([cell for _index, cell in produced]), 4
                ),
                "size_vs_canonical_base": round(
                    registration.size_ratio([a for a in final if a is not None], target), 4
                ),
                "frames_resized": resized,
                "frames_moved": moved,
            }

    packet = write_packet(
        bundle, candidate_id, action, produced, first_prompt, provenance, transform, args.variant_intent
    )

    if aborted is not None:
        listed = "; ".join(aborted["problems"])
        next_step = (
            f"{aborted['stopped_by']} stopped this state at frame {aborted['frame']} of "
            f"{len(indices)}: {listed}. Fix the prompt or the canonical base and run the "
            f"state again -- the remaining {len(indices) - len(produced)} frames would have "
            f"carried the same defect. The frames drawn so far are in the packet as evidence."
        )
        if aborted["stopped_by"] == "size-budget":
            next_step += (
                f" A size lock in --extra-prompt is not the fix: it was measured taking one "
                f"state from 1.41x to 1.14x and the next to 0.54x. If `{action}` genuinely "
                f"changes size, declare it in geist_house.SIZE_BUDGET and it is normalised "
                f"for free instead."
            )
    elif args.mode == MODE_SUPERVISED:
        next_step = (
            f"pre-screen the packet, then render qa/{action}-review.html "
            "and ask the human to choose a candidate id"
        )
    else:
        next_step = (
            f"pre-screen the packet, render qa/{action}-review.html as the record, then "
            "promote it by the tie-break ladder and log the decision in qa/approvals.json"
        )

    print(
        json.dumps(
            {
                "ok": aborted is None,
                "mode": "External Image Provider",
                "decision_mode": args.mode,
                "action": action,
                "candidate_id": candidate_id,
                "packet": str(packet),
                "state": action,
                "frames": [index for index, _image in produced],
                "frames_requested": len(indices),
                "model": config.model,
                "cell_transform": transform.as_dict(),
                "registration": registered,
                "alpha_paths": sorted({record["alpha_path"] for record in provenance}),
                "chroma_key": {
                    "name": chroma["name"],
                    "rgb": list(chroma["key"]),
                    "clearance_from_pet": chroma["clearance"],
                    "safe": chroma["safe"],
                    "scores": chroma["scores"],
                },
                "canonical_base_components": base_components,
                "frames_outside_safe_padding": misfits,
                "preflight": aborted
                or {
                    "passed": True,
                    "frames_checked": min(PREFLIGHT_FRAMES, len(produced)),
                    "size_checked": len(produced),
                },
                "spend": guard.as_dict(),
                "ledger": ledger.as_dict(),
                "next": next_step,
            },
            indent=2,
        )
    )
    for warning in ledger.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    # A caller that reads only the exit code must not mistake a vetoed state for
    # a finished one. The JSON is already on stdout, so the packet and the named
    # cause survive the non-zero exit.
    if aborted is not None:
        sys.exit(1)


if __name__ == "__main__":
    main()
