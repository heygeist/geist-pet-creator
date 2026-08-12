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
    HOUSE_FORM,
    MIN_PASSING_CELLS,
    NEVER_TRANSFERS,
    cell_id,
    house_style_path,
    layout_for,
)
from geist_manifest import read_manifest
from geist_pixels import alpha_bbox, clear_transparent_rgb, data_uri
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
# of transparency. Measured 2026-08-12; run eval_providers.py to re-measure.
#
# The qwen models are deliberately absent. Alibaba's filter rejects recognisable
# reference art with "Input data is suspected of being involved in IP
# infringement", which makes them unusable for derived Pets -- the case this
# skill exists to serve.
KNOWN_MODELS = (
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "openai/gpt-image-2",
    "x-ai/grok-imagine-image-2.0",
)

# Lanczos resampling spreads an edge by roughly one pixel.
RESAMPLE_BLEED = 1

# A returned image counts as alpha-capable only when the border is genuinely
# clear and a real share of the canvas is transparent. An opaque image with one
# stray transparent pixel must not pass.
MIN_TRANSPARENT_FRACTION = 0.10
MIN_CLEAR_BORDER_FRACTION = 0.90

CHROMA_SUFFIX = (
    " Place the character on a flat, uniform chroma-key background of pure green (#00FF00). "
    "Keep the green clear of the character and use no green in the character itself."
)
CHROMA_KEY = (0, 255, 0)
KEY_TOLERANCE = 72

SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|[A-Za-z0-9_\-]{40,})")

CONCEPT_SHEET = "concept-sheet"
CANONICAL_BASE = "canonical-base"
PRE_FRAME_ACTIONS = (CONCEPT_SHEET, CANONICAL_BASE)
ACTIONS = (*PRE_FRAME_ACTIONS, *sorted(FRAME_COUNTS))

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
openai/gpt-image-2 is this skill's default and draws frames for ~$0.023 each.

This mistake has been made repeatedly, and it makes things worse: sessions have
repinned working bundles onto openai/gpt-5.4-image-2, which rejects the
transparency parameters this pipeline sends. A confident-looking catalog check
returning the wrong answer is exactly why this message exists.

The only test that settles whether a model works is a live request:

    scripts/with_openrouter_key.sh python3 scripts/generate_candidates.py \\
        --verify-model MODEL_ID

It costs about $0.01 and answers definitively. Use it before changing any pin.
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
    print(f"{model}: REACHABLE. cost ${cost:.5f}.")
    print(f"  in KNOWN_MODELS: {listed}")
    if not listed:
        print("  It works but is not pinned as known. Add it to KNOWN_MODELS if you want it,")
        print("  and measure it with eval_providers.py before making it a default.")
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

    @classmethod
    def from_reference(cls, image: Image.Image, safe_padding: int) -> "CellTransform":
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
        scale = min((CELL_WIDTH - margin) / body_width, (CELL_HEIGHT - margin) / body_height)
        centre_x = (left + right) / 2
        centre_y = (top + bottom) / 2
        return cls(
            scale=scale,
            offset_x=round(CELL_WIDTH / 2 - centre_x * scale),
            offset_y=round(CELL_HEIGHT / 2 - centre_y * scale),
            source_size=image.size,
        )

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


def key_out_chroma(image: Image.Image) -> Image.Image:
    """Remove a flat chroma background and the desaturated fringe it leaves."""
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    out = bytearray(len(data) // 3 * 4)
    key_r, key_g, key_b = CHROMA_KEY
    for index in range(0, len(data), 3):
        red, green, blue = data[index], data[index + 1], data[index + 2]
        distance = abs(red - key_r) + abs(green - key_g) + abs(blue - key_b)
        base = index // 3 * 4
        if distance <= KEY_TOLERANCE or (green > 150 and green > red * 1.5 and green > blue * 1.5):
            continue  # stays fully transparent, RGB left at zero
        out[base] = red
        out[base + 1] = green
        out[base + 2] = blue
        out[base + 3] = 255
    return Image.frombytes("RGBA", image.size, bytes(out))


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


def generate_frame(
    config: ProviderConfig,
    prompt: str,
    references: list[str],
    guard: SpendGuard,
    require_alpha: bool = True,
) -> tuple[Image.Image, dict[str, Any]]:
    """Draw one image on the provider canvas. Placement happens later, once.

    `require_alpha` is False only for a concept sheet, which asked for paper.
    Running the transparency check on it would see an opaque image, conclude the
    provider ignored a parameter that was never sent, and spend a second call
    keying out a background the sheet is supposed to have.
    """

    def once(active: ProviderConfig, text: str) -> tuple[Image.Image, float]:
        guard.check()
        payload = call_provider(active, text, references)
        image, cost = decode_image(payload)
        guard.record(cost)
        return image, cost

    alpha_path = "native"
    try:
        image, cost = once(config, prompt)
    except SystemExit as error:
        # Some models reject `output_format`/`background` outright instead of
        # ignoring them -- openai/gpt-image-2 answers "background: not
        # supported. Accepted: auto, opaque". Dropping the fields makes the
        # model reachable, and the chroma path below supplies the transparency
        # those fields were asking for. Without this the whole model is
        # unusable, which is a worse outcome than one extra call.
        if "400" not in str(error) or "parameter" not in str(error).lower():
            raise
        config = ProviderConfig(
            provider=config.provider,
            model=config.model,
            output_format=None,
            background=None,
            resolution=config.resolution,
            aspect_ratio=config.aspect_ratio,
            quality=config.quality,
            extra=config.extra,
        )
        image, cost = once(config, prompt)
        alpha_path = "params-dropped"

    if not require_alpha:
        alpha_path = "opaque by request"
    elif not alpha_is_real(image):
        # The provider ignored `background: transparent`, or never accepted it,
        # so ask for a flat chroma background and key it out here instead.
        image, cost = once(config, prompt + CHROMA_SUFFIX)
        image = key_out_chroma(image)
        alpha_path = "chroma-key fallback" if alpha_path == "native" else "params-dropped+chroma-key"

    provenance = {
        "provider": config.provider,
        "model": config.model,
        "endpoint": endpoint(),
        "requested_background": config.background,
        "requested_output_format": config.output_format,
        "alpha_path": alpha_path,
        "credential_source": credential_source(),
        "usage_cost_usd": round(cost, 6),
        "run_cost_usd": round(guard.cost, 6),
        "images_this_run": guard.images,
    }
    return image, provenance


# --------------------------------------------------------------------------- #
# Candidate packets
# --------------------------------------------------------------------------- #


def build_prompt(bundle: Path, state: str, index: int, frame_count: int, variant_intent: str, extra: str) -> str:
    manifest = read_manifest(bundle / "character-bible.md")
    return (
        f"Draw frame {index} of {frame_count} for the `{state}` sprite action of this Pet.\n"
        f"The attached images are the identity lock: image 1 is the canonical base, "
        f"image 2 is the previous approved frame of this same action.\n"
        f"Keep the silhouette, proportions, palette, face landmarks, props and scale identical to them.\n"
        f"Motion read: {variant_intent}\n"
        f"Compose the whole body inside the frame with clear margin on all four sides. "
        f"Transparent background. One character only, no shadow, no ground marks, no detached effects, "
        f"no text.{manifest.prompt_block()}\n"
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
        f"whole body inside the frame with clear margin on all four sides, transparent "
        f"background, one character only, no shadow, no ground marks, no detached effects, "
        f"no text.\n"
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


def write_packet(
    bundle: Path,
    candidate_id: str,
    state: str,
    frames: list[tuple[int, Image.Image]],
    prompt: str,
    provenance: list[dict[str, Any]],
    transform: CellTransform,
    variant_intent: str,
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
            {
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
                "generation_mode": "External Image Provider",
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
        transform = CellTransform.from_reference(raw, args.safe_padding)
        sprite = transform.apply(raw)
        fit = transform.fit_report(sprite, args.safe_padding)
        if not fit["fits"]:
            misfits.append({"candidate": f"canonical-base-{letter}", **fit})

        record["reference_count"] = len(references)
        record["fits_safe_padding"] = fit["fits"]
        candidate_id = f"canonical-base-{letter}"
        packet = write_base_packet(
            bundle, candidate_id, raw, sprite, transform, prompt, record, input_images, intent
        )
        candidate_ids.append(candidate_id)
        packets.append(str(packet))

    return {
        "action": CANONICAL_BASE,
        "candidate_ids": candidate_ids,
        "packets": packets,
        "from_approved_cell": from_cell,
        "candidates_outside_safe_padding": misfits,
        "next": (
            "pre-screen each candidate, then render qa/canonical-base-review.html and ask the "
            "human to choose one id before copying it to sources/canonical-base.png"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", help="Path to PetName.pet source bundle")
    parser.add_argument("--verify-model", metavar="MODEL_ID",
                        help="Settle whether a model id actually works, with one live "
                             "request (~$0.01). The catalog listing is incomplete and "
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
                        help="Runaway-loop guardrail, not a spend control: a value this run "
                             "passes to itself. Defaults per action -- $3.00 for a sprite "
                             "action, near 2x a measured 57-frame pass, since the 2026-08-12 "
                             "eval put openai/gpt-image-2 at ~$1.33 a pass. The real ceiling "
                             "is the credit limit on the OpenRouter key, which is enforced "
                             "server-side and outside this process's reach.")
    parser.add_argument("--mode", choices=MODES, default=MODE_SUPERVISED,
                        help="Decision mode this run belongs to. 'supervised' means a human picks "
                             "the candidate; 'auto' means full automation picks it. Recorded on "
                             "every ledger line, so a Pet whose frames nobody chose stays visible "
                             "as one months later.")
    parser.add_argument("--safe-padding", type=int, default=6)
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

    candidate_id = f"{action}-{args.variant}"
    ledger.candidate_id = candidate_id
    produced: list[tuple[int, Image.Image]] = []
    provenance: list[dict[str, Any]] = []
    transform: CellTransform | None = None
    previous: Image.Image | None = None
    first_prompt = ""
    misfits: list[dict[str, Any]] = []

    for index in indices:
        ledger.frame = index
        references = [canonical_uri]
        if previous is not None:
            references.append(data_uri(previous))
        else:
            earlier = bundle / "frames" / action / f"{max(0, index - 1):02d}.png"
            if index > 0 and earlier.is_file():
                references.append(image_reference(earlier))

        prompt = build_prompt(bundle, action, index, frame_count, args.variant_intent, args.extra_prompt)
        first_prompt = first_prompt or prompt
        raw, record = generate_frame(config, prompt, references, guard)

        # Scale is decided once, by the first frame, and never revisited.
        if transform is None:
            transform = CellTransform.from_reference(raw, args.safe_padding)
        cell = transform.apply(raw)

        fit = transform.fit_report(cell, args.safe_padding)
        if not fit["fits"]:
            misfits.append({"frame": index, **fit})

        record["frame"] = index
        record["reference_count"] = len(references)
        record["fits_safe_padding"] = fit["fits"]
        provenance.append(record)
        produced.append((index, cell))
        previous = cell

    assert transform is not None
    packet = write_packet(
        bundle, candidate_id, action, produced, first_prompt, provenance, transform, args.variant_intent
    )

    print(
        json.dumps(
            {
                "ok": True,
                "mode": "External Image Provider",
                "decision_mode": args.mode,
                "action": action,
                "candidate_id": candidate_id,
                "packet": str(packet),
                "state": action,
                "frames": [index for index, _image in produced],
                "model": config.model,
                "cell_transform": transform.as_dict(),
                "alpha_paths": sorted({record["alpha_path"] for record in provenance}),
                "frames_outside_safe_padding": misfits,
                "spend": guard.as_dict(),
                "ledger": ledger.as_dict(),
                "next": (
                    f"pre-screen the packet, then render qa/{action}-review.html "
                    "and ask the human to choose a candidate id"
                    if args.mode == MODE_SUPERVISED else
                    f"pre-screen the packet, render qa/{action}-review.html as the record, then "
                    "promote it by the tie-break ladder and log the decision in qa/approvals.json"
                ),
            },
            indent=2,
        )
    )
    for warning in ledger.warnings:
        print(f"warning: {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()
