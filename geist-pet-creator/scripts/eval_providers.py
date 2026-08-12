#!/usr/bin/env python3
"""Measure image models on the job this skill actually gives them.

Not on generic prompt following. A Pet is 57 frames of one creature, and 56 of
them are drawn with an approved identity lock attached as a reference image, so
a model that draws beautifully from a bare prompt and drifts the moment you show
it a character is useless here. Every case below therefore sends a reference.

Four cases, three of them identity-hold and one creativity:

  identity hold  An approved Pet's own art goes in as the reference. The model
                 redraws that exact creature in a new pose. Scored on whether
                 the cues survive the pose change.
  creativity     No character reference at all -- only the house-style sheet,
                 plus a physical description of a source the model must render
                 as a new Pet. Never the source's name: a name drags the whole
                 franchise art style in with it, which is the failure mode
                 references/identity-blend.md calls "franchise copy".

Two fallbacks, because most models need one:

  parameter      Some models answer HTTP 400 for output_format/background
                 rather than ignoring them. The request goes again without them.
  chroma-key     Some models accept those fields and return opaque pixels
                 anyway. The request goes again asking for a flat green
                 background, and the green is keyed out here.

Of seven contenders only two return true alpha unaided, so the chroma path is
the normal path, not an edge case. Measured 2026-08-12.

Scoring is two-stage. This script auto-scores the mechanical criteria from
references/qa-rubric.md and renders the silhouette test from
references/identity-blend.md. A human does the naming test and the blend
verdict, in the review page it writes. Identity stays human by design.

The key comes from OPENROUTER_API_KEY and never enters this file or its output.
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from geist_pixels import alpha_bbox, data_uri
from generate_candidates import (
    CHROMA_SUFFIX,
    ProviderConfig,
    alpha_is_real,
    api_key,
    call_provider,
    decode_image,
    endpoint,
    key_out_chroma,
    set_base_url,
)

# --------------------------------------------------------------------------- #
# Contenders
# --------------------------------------------------------------------------- #

# Every id here was confirmed by a live request. GET /api/v1/models lists
# neither openai/gpt-image-2 nor x-ai/grok-imagine-image-2.0, and both answer
# requests, so that endpoint is a hint and never proof a model is missing.
#
# The qwen models were measured and then removed. Alibaba's filter rejected the
# Doraemon reference with "Input data is suspected of being involved in IP
# infringement" -- a provider that refuses your own approved reference art
# cannot serve a skill built around derived Pets, at any price.
CONTENDERS = (
    "google/gemini-3.1-flash-lite-image",
    "google/gemini-3.1-flash-image",
    "google/gemini-3-pro-image",
    "openai/gpt-5-image-mini",
    "openai/gpt-5-image",
    "openai/gpt-image-2",
    "x-ai/grok-imagine-image-2.0",
)

FULL_PET_FRAMES = 57

# References ride along as data URLs, so a 1254x1254 base would inflate every
# request for no gain. The real pipeline's lock is 192x208; this is generous.
REFERENCE_MAX_EDGE = 384

HOUSE_FORM = (
    "One compact rounded legless floating body with a single thick sky-blue outline, "
    "a cream body area, two small ink dot eyes, one tiny mouth, exactly one centred "
    "orange heart on the chest, tiny attached arm nubs, flat fills, no legs, no feet, "
    "no floor and no shadow."
)

PET_DIR = Path.home() / "Desktop/work/geist/pet-design"
SKILL_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def hold_prompt(pose: str) -> str:
    return (
        f"Redraw the exact creature in the attached reference image, unchanged in colour, "
        f"shape, outline, markings and proportion, now {pose}. {HOUSE_FORM} "
        "Centre the character with clear empty space on all four sides."
    )


# The creativity case names no franchise and no character. Everything that makes
# the source recognisable is written as physical description, ranked the way
# identity-blend.md ranks cues: crown cue first, then colour blocks, then one
# prop, then face landmarks.
INVENT_PROMPT = (
    "Draw a new mascot creature in exactly the house style of the attached reference sheet. "
    "Give it: dark brown hair, slightly wavy, falling to just below the ears, with clearly "
    "red-brown tips at the ends; a jagged burn scar on the upper left forehead; a green and "
    "black checkered pattern across the lower body; small rectangular earrings, white with a "
    f"red sun disc. Calm determined expression. {HOUSE_FORM} "
    "Centre the character with clear empty space on all four sides."
)

TEST_CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "doraemon",
        "kind": "identity-hold",
        "reference": PET_DIR / "DoraemonGeist.pet/frames/idle/00.png",
        "prompt": hold_prompt("raising one arm nub in a friendly wave"),
        "cues": "round blue head, cream face, collar and bell, whiskers, red nose",
        "difficulty": "medium",
    },
    {
        "id": "gon-hxh",
        "kind": "identity-hold",
        "reference": PET_DIR / "HunterXHunterGeistConcepts.pet/sources/canonical-base.png",
        "prompt": hold_prompt("raising one arm nub in a friendly wave, still holding its prop"),
        "cues": "green spiky hair, green and red jacket blocks, fishing rod",
        "difficulty": "hard -- one attached prop",
    },
    {
        "id": "vegeta-dbz",
        "kind": "identity-hold",
        "reference": PET_DIR / "DragonBallConcepts.pet/sources/canonical-base.png",
        "prompt": hold_prompt("raising one arm nub in a friendly wave"),
        "cues": "black widow's-peak spiky hair, blue and white armour, gold trim, angry brows",
        "difficulty": "hardest -- spiky hair silhouette",
    },
    {
        "id": "invent-slayer",
        "kind": "creativity",
        "reference": SKILL_ASSETS / "geist-house-style.jpg",
        "prompt": INVENT_PROMPT,
        "cues": "red-tipped dark hair, forehead scar, green/black check, sun-disc earrings",
        "difficulty": "creativity -- no character reference",
    },
)


# --------------------------------------------------------------------------- #
# Spend guard
# --------------------------------------------------------------------------- #


class EvalGuard:
    """Independent of the key's server-side limit, on purpose.

    The key cap stops requests before they reach a provider. This stops the eval
    before a pathological model burns the budget on fallbacks, which is a
    different failure and deserves its own control.
    """

    def __init__(self, max_images: int, max_cost_usd: float) -> None:
        self.max_images = max_images
        self.max_cost_usd = max_cost_usd
        self.images = 0
        self.cost = 0.0

    def check(self) -> None:
        if self.images >= self.max_images:
            raise SystemExit(f"stopped at the --max-images ceiling of {self.max_images}")
        if self.cost >= self.max_cost_usd:
            raise SystemExit(
                f"stopped at the --max-cost-usd ceiling of ${self.max_cost_usd:.2f} "
                f"after {self.images} calls"
            )

    def record(self, cost: float) -> None:
        self.images += 1
        self.cost += cost


# --------------------------------------------------------------------------- #
# Mechanical QA and the silhouette test
# --------------------------------------------------------------------------- #


@dataclass
class Attempt:
    model: str
    case: str
    ok: bool = False
    error: str | None = None
    duration_s: float = 0.0
    cost_usd: float = 0.0
    calls: int = 0
    alpha_path: str = "-"
    width: int = 0
    height: int = 0
    mechanical_pass: bool = False
    reasons: list[str] = field(default_factory=list)
    preview: str | None = None
    silhouette: str | None = None

    def row(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "case": self.case,
            "ok": self.ok,
            "error": self.error,
            "duration_s": round(self.duration_s, 2),
            "cost_usd": round(self.cost_usd, 6),
            "calls": self.calls,
            "alpha_path": self.alpha_path,
            "size": [self.width, self.height],
            "mechanical_pass": self.mechanical_pass,
            "reasons": self.reasons,
        }


def mechanical_score(image: Image.Image) -> tuple[bool, list[str]]:
    """Auto-score what the rubric can check without a human.

    Identity is deliberately absent. Failing here eliminates a candidate before
    it costs anyone their attention; passing earns a human look, not a pass.
    """
    reasons: list[str] = []
    if not alpha_is_real(image):
        reasons.append("no real transparency")

    box = alpha_bbox(image)
    if box is None:
        return False, ["fully transparent: no subject found"]

    left, upper, right, lower = box
    width, height = image.size
    if left <= 0 or upper <= 0 or right >= width or lower >= height:
        reasons.append("subject touches the canvas edge")

    covered = ((right - left) * (lower - upper)) / float(width * height)
    if covered < 0.10:
        reasons.append(f"subject fills only {covered:.0%} of the canvas")
    if covered > 0.95:
        reasons.append(f"subject fills {covered:.0%} of the canvas: no margin")

    return not reasons, reasons


def silhouette_of(image: Image.Image) -> Image.Image:
    """The silhouette test from identity-blend.md, rendered rather than described.

    Fill the sprite solid and the crown cue and prop shape should still say who
    it is. A blend carried only by surface detail fails here and nowhere else.
    """
    alpha = image.getchannel("A")
    solid = Image.new("RGBA", image.size, (0, 0, 0, 0))
    solid.paste(Image.new("RGBA", image.size, (17, 17, 17, 255)), mask=alpha)
    return solid


def thumbnail(image: Image.Image, edge: int = 192) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((edge, edge), Image.LANCZOS)
    return copy


def load_reference(path: Path) -> str:
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    if max(image.size) > REFERENCE_MAX_EDGE:
        image.thumbnail((REFERENCE_MAX_EDGE, REFERENCE_MAX_EDGE), Image.LANCZOS)
    return data_uri(image)


# --------------------------------------------------------------------------- #
# One measurement, with both fallbacks
# --------------------------------------------------------------------------- #


def unsupported_parameter(error: str) -> bool:
    return "400" in error and "parameter" in error.lower()


def measure(model: str, case: dict[str, Any], reference: str, guard: EvalGuard) -> Attempt:
    attempt = Attempt(model=model, case=case["id"])
    prompt = case["prompt"]
    refs = [reference]
    started = time.monotonic()

    def once(config: ProviderConfig, text: str) -> Image.Image:
        guard.check()
        # retries=0: a retry folds provider latency into the duration and makes
        # the number meaningless. A flaky model failing here is a result.
        payload = call_provider(config, text, refs, retries=0)
        image, cost = decode_image(payload)
        guard.record(cost)
        attempt.calls += 1
        attempt.cost_usd += cost
        return image

    try:
        config = ProviderConfig(model=model)
        try:
            image = once(config, prompt)
            attempt.alpha_path = "native"
        except SystemExit as error:
            if "ceiling" in str(error) or not unsupported_parameter(str(error)):
                raise
            # The model rejects output_format/background outright. Drop them and
            # let the chroma path below deal with the opaque result.
            config = ProviderConfig(model=model, output_format=None, background=None)
            image = once(config, prompt)
            attempt.alpha_path = "params-dropped"

        if not alpha_is_real(image):
            image = key_out_chroma(once(config, prompt + CHROMA_SUFFIX))
            attempt.alpha_path = (
                "chroma-key" if attempt.alpha_path == "native" else "params-dropped+chroma"
            )
    except SystemExit as error:
        if "ceiling" in str(error):
            raise
        attempt.duration_s = time.monotonic() - started
        attempt.error = str(error)
        return attempt
    except Exception as error:  # noqa: BLE001 - one model must not end the run
        attempt.duration_s = time.monotonic() - started
        attempt.error = f"{type(error).__name__}: {error}"
        return attempt

    attempt.duration_s = time.monotonic() - started
    attempt.ok = True
    attempt.width, attempt.height = image.size
    attempt.mechanical_pass, attempt.reasons = mechanical_score(image)
    attempt.preview = data_uri(thumbnail(image, 320))
    attempt.silhouette = data_uri(thumbnail(silhouette_of(image), 192))
    return attempt


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def summarise(attempts: list[Attempt]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in dict.fromkeys(a.model for a in attempts):
        mine = [a for a in attempts if a.model == model]
        done = [a for a in mine if a.ok]
        passed = [a for a in done if a.mechanical_pass]
        costs = [a.cost_usd for a in done]
        times = [a.duration_s for a in done]
        median_cost = statistics.median(costs) if costs else 0.0
        rows.append({
            "model": model,
            "returned": f"{len(done)}/{len(mine)}",
            "mechanical_pass": f"{len(passed)}/{len(mine)}",
            "median_s": round(statistics.median(times), 2) if times else None,
            "total_cost_usd": round(sum(costs), 6),
            "median_cost_usd": round(median_cost, 6),
            "projected_pass_usd": round(median_cost * FULL_PET_FRAMES, 4),
            "alpha_paths": sorted({a.alpha_path for a in done}),
            "errors": [a.error for a in mine if a.error],
        })
    rows.sort(key=lambda r: (-int(r["mechanical_pass"].split("/")[0]), r["projected_pass_usd"]))
    return rows


def print_summary(rows: list[dict[str, Any]], guard: EvalGuard) -> None:
    print()
    print(f"{'model':36}{'ret':>5}{'mech':>6}{'med s':>8}{'run $':>9}{'57-frame $':>12}  alpha path")
    print("-" * 104)
    for row in rows:
        median = f"{row['median_s']:.1f}" if row["median_s"] is not None else "-"
        print(f"{row['model']:36}{row['returned']:>5}{row['mechanical_pass']:>6}{median:>8}"
              f"{row['total_cost_usd']:>9.4f}{row['projected_pass_usd']:>12.2f}  "
              f"{','.join(row['alpha_paths']) or '-'}")
    print("-" * 104)
    print(f"{guard.images} provider calls, ${guard.cost:.4f} spent")
    print("\n'57-frame $' projects median measured cost across a full Pet, from four")
    print("frames. Mechanical pass is necessary, not sufficient -- open review.html")
    print("and judge identity before choosing.")


REVIEW_CSS = """
*{box-sizing:border-box}
body{background:#14161a;color:#e6e6e6;font:14px/1.55 -apple-system,BlinkMacSystemFont,sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}
p.note{color:#9aa0a6;margin:0 0 20px;max-width:80ch}
.case{margin:0 0 34px;border-top:1px solid #2a2d33;padding-top:18px}
.case h2{font-size:16px;margin:0 0 2px}
.case .meta{color:#9aa0a6;font-size:13px;margin:0 0 14px}
.grid{display:flex;flex-wrap:wrap;gap:14px}
figure{margin:0;background:#1e2126;border-radius:10px;padding:12px;width:252px}
.pair{display:flex;gap:8px;align-items:flex-start}
.pair img{border-radius:6px;
 background-image:linear-gradient(45deg,#2a2d33 25%,transparent 25%,transparent 75%,#2a2d33 75%),
 linear-gradient(45deg,#2a2d33 25%,transparent 25%,transparent 75%,#2a2d33 75%);
 background-size:14px 14px;background-position:0 0,7px 7px}
.pair img.main{width:152px;height:152px;object-fit:contain}
.pair img.sil{width:64px;height:64px;object-fit:contain;background:#fff}
figcaption{font-size:12px;color:#9aa0a6;margin-top:8px;word-break:break-word}
.marks{margin-top:10px;border-top:1px solid #2a2d33;padding-top:8px;font-size:12px}
.marks label{display:block;margin:5px 0 2px;color:#c9ced6}
.marks select{width:100%;background:#14161a;color:#e6e6e6;border:1px solid #3a3f47;border-radius:5px;padding:4px}
.pass{color:#7ee787}.fail{color:#ff7b72}
.err{color:#ff7b72;font-family:ui-monospace,monospace;font-size:12px}
.bar{position:sticky;top:0;background:#14161a;padding:10px 0 14px;z-index:5;border-bottom:1px solid #2a2d33;margin-bottom:18px}
button{background:#2f6feb;color:#fff;border:0;border-radius:7px;padding:9px 16px;font-size:13px;cursor:pointer}
button:hover{background:#4680f0}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;background:#2a2d33;color:#9aa0a6;margin-left:6px}
"""

REVIEW_JS = """
function copyMarks(){
  const out=[];
  document.querySelectorAll('figure[data-model]').forEach(f=>{
    const a=f.querySelector('.m-aes').value, n=f.querySelector('.m-name').value, b=f.querySelector('.m-blend').value;
    if(a==='-'&&n==='-'&&b==='-') return;
    out.push(f.dataset.case+' | '+f.dataset.model+' | aesthetic='+a+' | naming='+n+' | blend='+b);
  });
  const text = out.length ? 'Eval marks:\\n'+out.join('\\n') : 'No marks set yet.';
  navigator.clipboard.writeText(text).then(()=>{
    const b=document.getElementById('copybtn'), o=b.textContent;
    b.textContent='Copied '+out.length+' marks'; setTimeout(()=>{b.textContent=o;},1800);
  });
}
"""


def write_review(attempts: list[Attempt], rows: list[dict[str, Any]], path: Path) -> None:
    """The human half of the score.

    Each candidate shows at thumbnail scale beside its silhouette, because the
    naming test is a thumbnail test and the silhouette test is the one that
    catches a blend carried only by surface detail.
    """
    by_model = {r["model"]: r for r in rows}
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Provider eval &mdash; review</title>",
        f"<style>{REVIEW_CSS}</style>",
        "<div class='bar'><button id='copybtn' onclick='copyMarks()'>Copy marks</button></div>",
        "<h1>Provider eval &mdash; identity review</h1>",
        "<p class='note'>Mechanical QA has already run and is shown per candidate. Your job is the "
        "two tests it cannot do. <b>Naming test:</b> at this thumbnail size, can someone who knows "
        "the source name it in about two seconds? <b>Blend verdict:</b> a good blend, or one of the "
        "two failure modes &mdash; <i>franchise copy</i> (the source style won: legs, source outline "
        "colour, heart missing or tacked on) or <i>generic blob</i> (the house form won: not nameable, "
        "cues collapsed). The small white panel is the silhouette test.</p>",
    ]
    for case in TEST_CASES:
        mine = [a for a in attempts if a.case == case["id"]]
        if not mine:
            continue
        parts.append(
            f"<div class='case'><h2>{html.escape(case['id'])}"
            f"<span class='tag'>{html.escape(case['kind'])}</span>"
            f"<span class='tag'>{html.escape(case['difficulty'])}</span></h2>"
            f"<p class='meta'>Cues that must survive: {html.escape(case['cues'])}</p><div class='grid'>"
        )
        for attempt in sorted(mine, key=lambda a: (not a.mechanical_pass, a.model)):
            summary = by_model.get(attempt.model, {})
            parts.append(
                f"<figure data-model='{html.escape(attempt.model)}' "
                f"data-case='{html.escape(attempt.case)}'>"
            )
            if attempt.preview:
                verdict = ("<span class='pass'>mechanical pass</span>" if attempt.mechanical_pass
                           else "<span class='fail'>"
                                + html.escape("; ".join(attempt.reasons)) + "</span>")
                parts.append(
                    f"<div class='pair'><img class='main' src='{attempt.preview}' "
                    f"alt='{html.escape(attempt.model)}'>"
                    f"<img class='sil' src='{attempt.silhouette}' alt='silhouette'></div>"
                    f"<figcaption><b>{html.escape(attempt.model)}</b><br>"
                    f"{attempt.duration_s:.1f}s &middot; ${attempt.cost_usd:.4f} &middot; "
                    f"{attempt.calls} call(s) &middot; {html.escape(attempt.alpha_path)}<br>"
                    f"57-frame ~${summary.get('projected_pass_usd', 0):.2f}<br>{verdict}</figcaption>"
                )
            else:
                parts.append(
                    f"<figcaption><b>{html.escape(attempt.model)}</b><br>"
                    f"<span class='err'>{html.escape(str(attempt.error))}</span></figcaption>"
                )
            parts.append(
                "<div class='marks'>"
                "<label>Aesthetic</label><select class='m-aes'>"
                "<option>-</option><option>1</option><option>2</option><option>3</option>"
                "<option>4</option><option>5</option></select>"
                "<label>Naming test</label><select class='m-name'>"
                "<option>-</option><option>pass</option><option>fail</option></select>"
                "<label>Blend verdict</label><select class='m-blend'>"
                "<option>-</option><option>good</option><option>franchise-copy</option>"
                "<option>generic-blob</option></select></div></figure>"
            )
        parts.append("</div></div>")
    parts.append(f"<script>{REVIEW_JS}</script>")
    path.write_text("".join(parts), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("provider-eval"))
    parser.add_argument("--models", nargs="*", default=list(CONTENDERS))
    parser.add_argument("--cases", nargs="*", default=[c["id"] for c in TEST_CASES])
    parser.add_argument("--max-images", type=int, default=90,
                        help="Hard ceiling on provider calls, fallbacks included")
    parser.add_argument("--max-cost-usd", type=float, default=4.5,
                        help="Hard ceiling on spend, independent of the key's own limit")
    parser.add_argument("--base-url", help="Provider base URL; point at a mock to spend nothing")
    args = parser.parse_args()

    set_base_url(args.base_url)
    api_key()
    print(f"endpoint: {endpoint()}")

    cases = [c for c in TEST_CASES if c["id"] in args.cases]
    missing = [str(c["reference"]) for c in cases if not c["reference"].is_file()]
    if missing:
        raise SystemExit("missing reference art:\n  " + "\n  ".join(missing))

    guard = EvalGuard(args.max_images, args.max_cost_usd)
    print(f"{len(args.models)} models x {len(cases)} cases = {len(args.models) * len(cases)} frames "
          f"(plus fallback calls)")
    print(f"ceilings: {args.max_images} calls, ${args.max_cost_usd:.2f}\n")

    attempts: list[Attempt] = []
    stopped = None
    # Case-major: if a ceiling fires you get complete model comparisons for the
    # finished cases rather than gaps spread across all of them.
    for case in cases:
        print(f"--- {case['id']} ({case['kind']}, {case['difficulty']})")
        reference = load_reference(case["reference"])
        for model in args.models:
            print(f"  {model:36} ", end="", flush=True)
            try:
                attempt = measure(model, case, reference, guard)
            except SystemExit as stop:
                stopped = str(stop)
                print(f"\n{stop}")
                break
            attempts.append(attempt)
            if attempt.ok:
                print(f"{attempt.duration_s:6.1f}s ${attempt.cost_usd:.4f} {attempt.calls}c "
                      f"{attempt.alpha_path:22} "
                      f"{'pass' if attempt.mechanical_pass else 'MECH FAIL'}")
            else:
                print(f"failed: {str(attempt.error)[:80]}")
        if stopped:
            break

    if not attempts:
        raise SystemExit("no measurements taken")

    args.out.mkdir(parents=True, exist_ok=True)
    rows = summarise(attempts)
    (args.out / "results.json").write_text(json.dumps({
        "cases": [{k: (str(v) if isinstance(v, Path) else v) for k, v in c.items()} for c in cases],
        "calls": guard.images,
        "cost_usd": round(guard.cost, 6),
        "stopped_early": stopped,
        "summary": rows,
        "attempts": [a.row() for a in attempts],
    }, indent=2), encoding="utf-8")
    write_review(attempts, rows, args.out / "review.html")
    print_summary(rows, guard)
    if stopped:
        print(f"\nSTOPPED EARLY: {stopped}")
    print(f"\nwrote {args.out / 'results.json'} and {args.out / 'review.html'}")


if __name__ == "__main__":
    main()
