#!/usr/bin/env python3
"""Render an HTML human-review page for Geist Pet candidate packets."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
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
    """A path the page can still resolve after the bundle moves.

    `Path.relative_to` only walks downwards, and every asset a review page shows
    lives in a sibling of `qa/`, so it always failed and fell back to an absolute
    path. That works exactly until the bundle is copied to another machine, at
    which point every image on the page 404s and the reason is invisible.
    """
    try:
        return os.path.relpath(path, root)
    except ValueError:
        # Different drives on Windows; nothing relative exists to return.
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


def growth_allowance_row(context: dict[str, Any]) -> str:
    """Motion headroom, on the page where changing the base is still cheap.

    `generate_candidates.py` measures how far a silhouette can grow inside the
    cell before it touches the line, and writes it into the packet. Until it is
    on the review page it changes no decision: the base for the 2026-08-12 build
    was chosen for the strongest identity read, and its lack of room then caused
    five of the six clipping failures across `jumping`, both directional states
    and `review`. That risk was recorded in the character bible as prose. It is
    a number, and this is the last moment it is free to act on.
    """
    for record in context.get("provenance", []) or []:
        allowance = record.get("growth_allowance") if isinstance(record, dict) else None
        if not isinstance(allowance, dict):
            continue
        width = allowance.get("width_pct")
        height = allowance.get("height_pct")
        limited = allowance.get("limited_by", "")
        if width is None or height is None:
            continue
        tight = min(width, height) < 5
        note = " — tight; every motion state will fight the cell" if tight else ""
        text = f"grow {width}% wider, {height}% taller (limited by {limited}){note}"
        return (
            f'<div><dt>Motion headroom</dt>'
            f'<dd class="{"warn" if tight else ""}">{html.escape(text)}</dd></div>'
        )
    return ""


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
    headroom_row = growth_allowance_row(context)
    pre_status = pre_screen.get("status", "unknown") if isinstance(pre_screen, dict) else "unknown"
    prompt_id = f"prompt-{candidate_id}"
    choice_text = f"I choose {candidate_id} for {action}."
    if preview_src:
        preview_html = (
            f'<img src="{html.escape(preview_src, quote=True)}" '
            f'alt="{html.escape(candidate_id, quote=True)} preview">'
        )
    else:
        preview_html = '<div class="missing">No preview found</div>'
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
          {preview_html}
        </div>
        <dl>
          <div><dt>Target</dt><dd>{html.escape(str(destination))}</dd></div>
          <div><dt>Prompt File</dt><dd>{html.escape(prompt_file)}</dd></div>
          {headroom_row}
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
    dd.warn {{ color: var(--bad); font-weight: 700; }}
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


CONCEPT_SHEET = "concept-sheet"
MIN_PASSING_CELLS = 3


def sheet_cells(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Zip the grid, the identity locks and the per-cell verdicts into one list.

    The three come from different places and are joined on `cell_id`, never on
    list position, so a packet that is missing a lock or a verdict shows a gap
    instead of silently shifting every later cell up by one.
    """
    grid = context.get("grid", {}) or {}
    columns = int(grid.get("columns") or 1)
    count = int(grid.get("cell_count") or 0)

    locks = {
        str(entry.get("cell_id")): str(entry.get("text", ""))
        for entry in context.get("identity_locks", [])
        if isinstance(entry, dict)
    }
    pre_screen = context.get("agent_pre_screen", {})
    verdicts = {
        str(entry.get("cell_id")): entry
        for entry in (pre_screen.get("cells", []) if isinstance(pre_screen, dict) else [])
        if isinstance(entry, dict)
    }

    cells: list[dict[str, Any]] = []
    for position in range(1, count + 1):
        identifier = f"cell-{position:02d}"
        verdict = verdicts.get(identifier, {})
        cells.append(
            {
                "id": identifier,
                "row": (position - 1) // columns,
                "column": (position - 1) % columns,
                "lock": locks.get(identifier, ""),
                "status": str(verdict.get("status", "pending")),
                "notes": str(verdict.get("notes", "")),
                "checks": verdict.get("checks", {}) if isinstance(verdict.get("checks"), dict) else {},
            }
        )
    return cells


def render_sheet_html(bundle: Path, candidate: dict[str, Any], output: Path) -> str:
    context = candidate["context"]
    candidate_id = candidate["id"]
    grid = context.get("grid", {}) or {}
    columns = int(grid.get("columns") or 1)
    rows = int(grid.get("rows") or 1)
    cells = sheet_cells(context)

    sheet_path = candidate["preview"]
    sheet_src = html_path(rel(sheet_path, output.parent)) if isinstance(sheet_path, Path) else ""
    prompt = str(candidate["prompt"])

    passing = [cell for cell in cells if cell["status"] == "pass"]
    pending = [cell for cell in cells if cell["status"] == "pending"]
    failing = [cell for cell in cells if cell["status"] == "fail"]

    banners = []
    if pending:
        banners.append(
            f"<div class=\"banner warn\"><b>{len(pending)} cell(s) not pre-screened.</b> "
            "Write a verdict for every cell before asking for a choice — an unscreened sheet "
            "looks exactly like a clean one.</div>"
        )
    if len(passing) < MIN_PASSING_CELLS and not pending:
        banners.append(
            f"<div class=\"banner stop\"><b>Only {len(passing)} cell(s) passed.</b> "
            f"Below {MIN_PASSING_CELLS}, redraw the sheet rather than asking the human to pick "
            "from what survived.</div>"
        )

    overlay = "".join(
        f"<div class=\"cell {cell['status']}\" style=\""
        f"left:{cell['column'] * 100 / columns:.4f}%;"
        f"top:{cell['row'] * 100 / rows:.4f}%;"
        f"width:{100 / columns:.4f}%;"
        f"height:{100 / rows:.4f}%\" data-cell=\"{html.escape(cell['id'], quote=True)}\">"
        f"<span class=\"badge\">{int(cell['id'].split('-')[1])}</span></div>"
        for cell in cells
    )

    rows_html = ""
    for cell in cells:
        checks = "".join(
            f"<span class=\"check\"><b>{html.escape(str(key))}</b>: {html.escape(str(value))}</span>"
            for key, value in cell["checks"].items()
        )
        choosable = cell["status"] != "fail"
        button = (
            f"<button type=\"button\" class=\"pick\" data-cell=\"{html.escape(cell['id'], quote=True)}\">Choose</button>"
            if choosable
            else "<span class=\"blocked\">Not choosable</span>"
        )
        notes_html = (
            f'<p class="notes">{html.escape(cell["notes"])}</p>' if cell["notes"] else ""
        )
        rows_html += f"""
        <article class="cellcard {cell['status']}" id="card-{html.escape(cell['id'])}">
          <header>
            <h2>{html.escape(cell['id'])}</h2>
            <span class="status {cell['status']}">{html.escape(cell['status'])}</span>
          </header>
          <p class="lock">{html.escape(cell['lock']) or "<em>no identity lock recorded</em>"}</p>
          <div class="checks">{checks}</div>
          {notes_html}
          <footer>{button}</footer>
        </article>
        """

    sheet_html = (
        f'<img src="{html.escape(sheet_src, quote=True)}" alt="concept sheet">'
        if sheet_src
        else "<div>No sheet image found</div>"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Geist Pet Concept Sheet: {html.escape(candidate_id)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172026; --muted:#58646d; --line:#d8dee3;
             --paper:#f7f7f4; --panel:#fff; --accent:#0b8ed8; --accent-dark:#086ca5;
             --bad:#c0392b; --warn:#a86a00; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color:var(--ink); background:var(--paper); }}
    main {{ max-width:1180px; margin:0 auto; padding:24px; }}
    h1 {{ margin:0 0 4px; font-size:24px; }}
    p {{ margin:0; color:var(--muted); }}
    .banner {{ padding:12px 14px; border-radius:8px; margin-bottom:12px; border:1px solid var(--line); }}
    .banner.warn {{ background:#fff8e6; border-color:#e8cf94; color:var(--warn); }}
    .banner.stop {{ background:#fdecea; border-color:#f0b3ac; color:var(--bad); }}
    .sheet-wrap {{ position:relative; display:inline-block; max-width:100%;
                   border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--panel); }}
    .sheet-wrap img {{ display:block; max-width:100%; height:auto; }}
    .cell {{ position:absolute; border:1px dashed rgba(11,142,216,.5); }}
    .cell.fail {{ border:2px solid var(--bad); background:rgba(192,57,43,.14); }}
    .cell.selected {{ border:3px solid var(--accent); background:rgba(11,142,216,.12); }}
    .badge {{ position:absolute; top:6px; left:6px; min-width:22px; height:22px; padding:0 6px;
              display:grid; place-items:center; border-radius:999px; background:var(--accent);
              color:#fff; font-weight:700; font-size:12px; box-shadow:0 1px 3px rgba(0,0,0,.3); }}
    .cell.fail .badge {{ background:var(--bad); }}
    .decision {{ margin:16px 0; padding:12px; border:1px solid var(--line);
                 background:var(--panel); border-radius:8px; }}
    #selectedText {{ margin-top:8px; font-weight:700; color:var(--accent-dark); }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; margin-top:18px; }}
    .cellcard {{ border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; }}
    .cellcard.fail {{ opacity:.62; }}
    .cellcard.fail .lock {{ text-decoration:line-through; }}
    .cellcard.selected {{ outline:3px solid var(--accent); }}
    .cellcard header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }}
    h2 {{ margin:0; font-size:17px; }}
    .status {{ padding:3px 8px; border-radius:999px; font-weight:700; font-size:11px; text-transform:uppercase; }}
    .status.pass {{ background:#e9f7ef; color:#14743a; }}
    .status.fail {{ background:#fdecea; color:var(--bad); }}
    .status.pending {{ background:#fff8e6; color:var(--warn); }}
    .lock {{ color:var(--ink); }}
    .notes {{ margin-top:8px; color:var(--bad); }}
    .checks {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
    .check {{ padding:3px 7px; border:1px solid var(--line); border-radius:999px; background:#fafafa; font-size:12px; }}
    footer {{ margin-top:12px; }}
    button {{ border:1px solid var(--accent-dark); border-radius:6px; background:var(--accent);
              color:#fff; padding:8px 12px; font-weight:700; cursor:pointer; }}
    button.ghost {{ background:#fff; color:var(--ink); border-color:var(--line); }}
    .blocked {{ color:var(--bad); font-weight:700; }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; margin:0; padding:10px; border:1px solid var(--line);
           border-radius:6px; background:#f8fafb; }}
    section.prompt {{ margin-top:18px; }}
    h3 {{ font-size:13px; text-transform:uppercase; color:var(--muted); margin:0 0 8px; }}
  </style>
</head>
<body>
  <main>
    <h1>Concept Sheet: {html.escape(candidate_id)}</h1>
    <p>{columns}x{rows} grid, {len(cells)} cells, read left to right and top to bottom.
       {len(passing)} passed, {len(failing)} failed, {len(pending)} unscreened.</p>
    {"".join(banners)}
    <div class="sheet-wrap">
      {sheet_html}
      {overlay}
    </div>
    <aside class="decision">
      <b>Decision Needed</b>
      <p>Click the cells you want, then send the copied sentence back to Codex.
         A cell is a concept, not a canonical base — each one you pick still gets
         redrawn at sprite scale and approved before it becomes an identity lock.</p>
      <div id="selectedText">No cell selected.</div>
      <p style="margin-top:10px"><button type="button" class="ghost" id="clear">Clear selection</button></p>
    </aside>
    <section class="grid">{rows_html}</section>
    <section class="prompt">
      <h3>Prompt</h3>
      <pre id="sheet-prompt">{html.escape(prompt)}</pre>
      <p style="margin-top:10px"><button type="button" class="ghost" id="copyPrompt">Copy Prompt</button></p>
    </section>
  </main>
  <script>
    const chosen = new Set();
    async function copyText(text) {{
      try {{ await navigator.clipboard.writeText(text); return true; }}
      catch (error) {{
        const area = document.createElement('textarea');
        area.value = text; document.body.appendChild(area); area.select();
        const ok = document.execCommand('copy'); area.remove(); return ok;
      }}
    }}
    function sentence() {{
      const ids = [...chosen].sort();
      if (!ids.length) return '';
      if (ids.length === 1) return `I choose ${{ids[0]}} from the concept sheet.`;
      const last = ids.pop();
      return `I choose ${{ids.join(', ')}} and ${{last}} from the concept sheet.`;
    }}
    function paint() {{
      document.querySelectorAll('.cell, .cellcard').forEach((node) => {{
        const id = node.dataset.cell || node.id.replace('card-', '');
        node.classList.toggle('selected', chosen.has(id));
      }});
      const text = sentence();
      document.getElementById('selectedText').textContent = text || 'No cell selected.';
      return text;
    }}
    async function toggle(id) {{
      if (chosen.has(id)) chosen.delete(id); else chosen.add(id);
      const text = paint();
      if (text) {{
        const ok = await copyText(text);
        document.getElementById('selectedText').textContent = ok ? text + ' Copied.' : text;
      }}
    }}
    document.querySelectorAll('button.pick').forEach((button) =>
      button.addEventListener('click', () => toggle(button.dataset.cell)));
    document.querySelectorAll('.cell:not(.fail)').forEach((cell) =>
      cell.addEventListener('click', () => toggle(cell.dataset.cell)));
    document.getElementById('clear').addEventListener('click', () => {{ chosen.clear(); paint(); }});
    document.getElementById('copyPrompt').addEventListener('click', async (event) => {{
      const ok = await copyText(document.getElementById('sheet-prompt').textContent);
      event.target.textContent = ok ? 'Prompt Copied' : 'Copy Failed';
      setTimeout(() => event.target.textContent = 'Copy Prompt', 1200);
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Path to PetName.pet source bundle")
    parser.add_argument("--action", required=True,
                        help="Sprite action/state to review, or concept-sheet for a brainstorm sheet")
    parser.add_argument("--output", help="HTML output path; defaults to <bundle>/qa/<action>-review.html")
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    output = Path(args.output).expanduser().resolve() if args.output else bundle / "qa" / f"{args.action}-review.html"
    candidates = discover_candidates(bundle, args.action)
    if not candidates:
        raise SystemExit(f"No candidate packets found for action {args.action!r}")
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.action == CONCEPT_SHEET:
        # A sheet is one candidate holding many options, so the page is the sheet
        # rather than a row of cards. Newest packet wins when a V2 round has run.
        candidate = candidates[-1]
        output.write_text(render_sheet_html(bundle, candidate, output), encoding="utf-8")
        cells = sheet_cells(candidate["context"])
        print(
            json.dumps(
                {
                    "ok": True,
                    "action": args.action,
                    "output": str(output),
                    "candidate_id": candidate["id"],
                    "cells": {
                        "pass": [c["id"] for c in cells if c["status"] == "pass"],
                        "fail": [c["id"] for c in cells if c["status"] == "fail"],
                        "pending": [c["id"] for c in cells if c["status"] == "pending"],
                    },
                },
                indent=2,
            )
        )
        return

    output.write_text(render_html(bundle, args.action, candidates, output), encoding="utf-8")
    print(json.dumps({"ok": True, "action": args.action, "output": str(output), "candidates": [c["id"] for c in candidates]}, indent=2))


if __name__ == "__main__":
    main()
