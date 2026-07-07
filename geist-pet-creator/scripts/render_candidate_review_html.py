#!/usr/bin/env python3
"""Render an HTML human-review page for Geist Pet candidate packets."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image


STATE_FRAME_COUNTS = {
    "idle": 6,
    "running-right": 8,
    "running-left": 8,
    "waving": 4,
    "jumping": 5,
    "failed": 8,
    "waiting": 6,
    "running": 6,
    "review": 6,
}

STATE_CONTACT_GRIDS = {
    "idle": (3, 2),
    "running-right": (4, 2),
    "running-left": (4, 2),
    "waving": (4, 1),
    "jumping": (5, 1),
    "failed": (4, 2),
    "waiting": (3, 2),
    "running": (3, 2),
    "review": (3, 2),
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def html_path(path: str) -> str:
    return html.escape(path.replace("\\", "/"), quote=True)


def normalize_frame(cell: Image.Image) -> Image.Image:
    rgba = cell.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            is_green_key = green > 105 and green > red + 35 and green > blue + 35
            is_near_green_key = green > 150 and green > red + 18 and green > blue + 18
            if is_green_key or is_near_green_key:
                pixels[x, y] = (0, 0, 0, 0)
            elif alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba.resize((192, 208), Image.Resampling.LANCZOS)


def infer_contact_grid(action: str, frame_count: int, image_size: tuple[int, int]) -> tuple[int, int]:
    if action in STATE_CONTACT_GRIDS:
        return STATE_CONTACT_GRIDS[action]
    width, height = image_size
    columns = min(frame_count, max(1, round(math.sqrt(frame_count * width / max(height, 1)))))
    rows = math.ceil(frame_count / columns)
    return columns, rows


def ensure_animated_preview(bundle: Path, candidate_dir: Path, context: dict[str, Any], action: str) -> Path | None:
    frame_count = STATE_FRAME_COUNTS.get(action)
    if not frame_count or frame_count <= 1:
        return None

    source: Path | None = None
    generated_file = context.get("generated_file")
    if isinstance(generated_file, str):
        generated = bundle / generated_file
        if generated.is_file():
            source = generated
    if source is None:
        contact_sheet = candidate_dir / "contact-sheet.png"
        if contact_sheet.is_file():
            source = contact_sheet
    if source is None:
        return None

    preview = candidate_dir / "animated-preview.webp"
    if preview.is_file() and preview.stat().st_mtime >= source.stat().st_mtime:
        return preview

    sheet = Image.open(source).convert("RGBA")
    columns, rows = infer_contact_grid(action, frame_count, sheet.size)
    if columns * rows < frame_count:
        return None

    xs = [round(i * sheet.width / columns) for i in range(columns + 1)]
    ys = [round(i * sheet.height / rows) for i in range(rows + 1)]
    frames: list[Image.Image] = []
    for index in range(frame_count):
        col = index % columns
        row = index // columns
        cell = sheet.crop((xs[col], ys[row], xs[col + 1], ys[row + 1]))
        frames.append(normalize_frame(cell))

    if not frames:
        return None
    frames[0].save(
        preview,
        save_all=True,
        append_images=frames[1:],
        duration=120,
        loop=0,
        lossless=True,
        method=6,
    )
    return preview


def discover_candidates(bundle: Path, action: str) -> list[dict[str, Any]]:
    contexts = sorted((bundle / "sources" / "candidates").glob("*/candidate-context.json"))
    candidates: list[dict[str, Any]] = []
    for context_path in contexts:
        context = load_json(context_path)
        target = context.get("target", {})
        state = target.get("state") or target.get("action") or target.get("kind")
        candidate_id = str(context.get("candidate_id", context_path.parent.name))
        if action and state != action and not candidate_id.startswith(f"{action}-"):
            continue
        candidate_dir = context_path.parent
        generated_file = context.get("generated_file")
        preview = ensure_animated_preview(bundle, candidate_dir, context, action)
        for name in ("animated-preview.webp", "animated-preview.gif"):
            candidate_preview = candidate_dir / name
            if candidate_preview.is_file() and preview is None:
                preview = candidate_preview
                break
        if isinstance(generated_file, str):
            generated = bundle / generated_file
            if generated.is_file() and preview is None:
                preview = generated
        if preview is None:
            for name in ("contact-sheet.png", "candidate.png"):
                candidate_preview = candidate_dir / name
                if candidate_preview.is_file():
                    preview = candidate_preview
                    break
        prompt_file = context.get("prompt_file")
        prompt_path = bundle / prompt_file if isinstance(prompt_file, str) else candidate_dir / "prompt.md"
        prompt_text = context.get("prompt_text")
        if not isinstance(prompt_text, str) and prompt_path.is_file():
            prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        candidates.append(
            {
                "id": candidate_id,
                "context": context,
                "context_path": context_path,
                "preview": preview,
                "prompt_path": prompt_path if prompt_path.is_file() else None,
                "prompt": prompt_text or "",
            }
        )
    return candidates


def render_card(candidate: dict[str, Any], bundle: Path, output: Path, action: str) -> str:
    context = candidate["context"]
    candidate_id = candidate["id"]
    preview = candidate["preview"]
    prompt = str(candidate["prompt"])
    target = context.get("target", {})
    pre_screen = context.get("agent_pre_screen", {})
    checks = pre_screen.get("checks", {}) if isinstance(pre_screen, dict) else {}
    risks = context.get("known_risks", [])
    invariants = context.get("identity_invariants", [])
    prompt_path = candidate["prompt_path"]

    preview_src = ""
    if isinstance(preview, Path):
        preview_src = html_path(rel(preview, output.parent))
    prompt_file = rel(prompt_path, bundle) if isinstance(prompt_path, Path) else ""

    risk_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in risks)
    invariant_items = "".join(f"<li>{html.escape(str(item))}</li>" for item in invariants)
    check_items = "".join(
        f"<span class=\"check\"><b>{html.escape(str(key))}</b>: {html.escape(str(value))}</span>"
        for key, value in checks.items()
    )
    destination = target.get("destination", "")
    variant_intent = context.get("variant_intent", "")
    pre_status = pre_screen.get("status", "unknown") if isinstance(pre_screen, dict) else "unknown"
    prompt_id = f"prompt-{candidate_id}"
    choice_text = f"I choose {candidate_id} for {action}."
    return f"""
      <article class="candidate" id="{html.escape(candidate_id)}">
        <header>
          <div>
            <h2>{html.escape(candidate_id)}</h2>
            <p>{html.escape(str(variant_intent))}</p>
          </div>
          <span class="status">{html.escape(str(pre_status))}</span>
        </header>
        <div class="preview-wrap">
          {"<img src=\"" + preview_src + "\" alt=\"" + html.escape(candidate_id) + " preview\">" if preview_src else "<div class=\"missing\">No preview found</div>"}
        </div>
        <dl>
          <div><dt>Target</dt><dd>{html.escape(str(destination))}</dd></div>
          <div><dt>Prompt File</dt><dd>{html.escape(prompt_file)}</dd></div>
        </dl>
        <div class="checks">{check_items}</div>
        <section>
          <h3>Prompt</h3>
          <pre id="{html.escape(prompt_id)}">{html.escape(prompt)}</pre>
        </section>
        <section class="two-col">
          <div>
            <h3>Preserve</h3>
            <ul>{invariant_items}</ul>
          </div>
          <div>
            <h3>Risks</h3>
            <ul>{risk_items}</ul>
          </div>
        </section>
        <footer>
          <button type="button" class="choose" data-choice="{html.escape(choice_text, quote=True)}" data-id="{html.escape(candidate_id)}">Choose</button>
          <button type="button" class="copy" data-prompt-target="{html.escape(prompt_id)}">Copy Prompt</button>
        </footer>
      </article>
    """


def render_html(bundle: Path, action: str, candidates: list[dict[str, Any]], output: Path) -> str:
    cards = "\n".join(render_card(candidate, bundle, output, action) for candidate in candidates)
    option_ids = ", ".join(candidate["id"] for candidate in candidates)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Geist Pet Review: {html.escape(action)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #58646d;
      --line: #d8dee3;
      --paper: #f7f7f4;
      --panel: #ffffff;
      --accent: #0b8ed8;
      --accent-dark: #086ca5;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    .topbar {{
      display: flex;
      gap: 16px;
      align-items: flex-end;
      justify-content: space-between;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
    p {{ margin: 0; color: var(--muted); }}
    .decision {{
      min-width: 280px;
      padding: 12px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
      align-items: start;
    }}
    .candidate {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    .candidate.selected {{ outline: 3px solid var(--accent); }}
    .candidate header, .candidate footer {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 14px;
      border-bottom: 1px solid var(--line);
    }}
    .candidate footer {{ border-top: 1px solid var(--line); border-bottom: 0; }}
    h2 {{ margin: 0; font-size: 18px; }}
    h3 {{ margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: var(--muted); }}
    .status {{
      padding: 3px 8px;
      border-radius: 999px;
      background: #e9f7ef;
      color: #14743a;
      font-weight: 700;
      text-transform: uppercase;
      font-size: 11px;
    }}
    .preview-wrap {{
      display: grid;
      place-items: center;
      min-height: 236px;
      padding: 14px;
      background: #fbfbfa;
      border-bottom: 1px solid var(--line);
    }}
    img {{ max-width: 100%; height: auto; image-rendering: auto; }}
    .preview-wrap img[src$=".webp"], .preview-wrap img[src$=".gif"] {{
      width: min(192px, 100%);
    }}
    dl {{ margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--line); }}
    dl div {{ display: grid; grid-template-columns: 88px 1fr; gap: 8px; margin: 4px 0; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    .checks {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 14px; border-bottom: 1px solid var(--line); }}
    .check {{ padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; background: #fafafa; }}
    section {{ padding: 14px; border-bottom: 1px solid var(--line); }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      margin: 0;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafb;
      color: #27313a;
    }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    ul {{ margin: 0; padding-left: 18px; }}
    button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 8px 10px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.choose {{ background: var(--accent); color: white; border-color: var(--accent-dark); }}
    button:hover {{ filter: brightness(0.97); }}
    #selectedText {{ margin-top: 8px; font-weight: 700; color: var(--accent-dark); }}
    @media (max-width: 720px) {{
      main {{ padding: 14px; }}
      .topbar {{ display: block; }}
      .decision {{ margin-top: 12px; min-width: 0; }}
      .two-col {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="topbar">
      <div>
        <h1>Geist Pet Review: {html.escape(action)}</h1>
        <p>Choose exactly one candidate id before promotion. Options: {html.escape(option_ids)}</p>
      </div>
      <aside class="decision">
        <b>Decision Needed</b>
        <p>Click Choose, then send the copied choice back to Codex.</p>
        <div id="selectedText">No candidate selected.</div>
      </aside>
    </div>
    <section class="grid">
      {cards}
    </section>
  </main>
  <script>
    async function copyText(text) {{
      try {{
        await navigator.clipboard.writeText(text);
        return true;
      }} catch (error) {{
        const area = document.createElement('textarea');
        area.value = text;
        document.body.appendChild(area);
        area.select();
        const ok = document.execCommand('copy');
        area.remove();
        return ok;
      }}
    }}
    document.querySelectorAll('button.choose').forEach((button) => {{
      button.addEventListener('click', async () => {{
        document.querySelectorAll('.candidate').forEach((card) => card.classList.remove('selected'));
        const card = button.closest('.candidate');
        card.classList.add('selected');
        const choice = button.dataset.choice;
        const ok = await copyText(choice);
        document.getElementById('selectedText').textContent = ok ? choice + ' Copied.' : choice;
      }});
    }});
    document.querySelectorAll('button.copy').forEach((button) => {{
      button.addEventListener('click', async () => {{
        const promptNode = document.getElementById(button.dataset.promptTarget);
        const prompt = promptNode ? promptNode.textContent : '';
        const ok = await copyText(prompt);
        button.textContent = ok ? 'Prompt Copied' : 'Copy Failed';
        setTimeout(() => button.textContent = 'Copy Prompt', 1200);
      }});
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to PetName.pet source bundle")
    parser.add_argument("--action", required=True, help="Sprite action/state to review")
    parser.add_argument("--output", help="HTML output path; defaults to <bundle>/qa/<action>-review.html")
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else bundle / "qa" / f"{args.action}-review.html"
    candidates = discover_candidates(bundle, args.action)
    if not candidates:
        raise SystemExit(f"No candidate packets found for action {args.action!r}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(bundle, args.action, candidates, output), encoding="utf-8")
    print(json.dumps({"ok": True, "action": args.action, "output": str(output), "candidates": [c["id"] for c in candidates]}, indent=2))


if __name__ == "__main__":
    main()
