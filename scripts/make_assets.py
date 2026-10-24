"""Regenerate the static images in docs/assets/ (banner, architecture, social preview).

    python scripts/make_assets.py

Light and dark versions come from one template, so they never drift apart. The social preview PNG needs Pillow
(`pip install pillow`); the SVGs need nothing. Numbers in the banner are from a real run (see docs/STATUS.md)."""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"

THEMES = {
    "light": dict(bg="#f6f7f9", card="#ffffff", line="#d8dce3", ink="#1c2129", muted="#5b6573", amber="#b4690e",
                  teal="#0f7c80", ok="#1f7a3a", arrow="#8b95a3", on="#ffffff", soft="#eef1f5"),
    "dark": dict(bg="#0f1318", card="#161b22", line="#2b323c", ink="#e7ebf0", muted="#97a1ae", amber="#e3a14e",
                 teal="#4cc3c6", ok="#58c27a", arrow="#6b7684", on="#0f1318", soft="#1d242d"),
}
MONO = 'ui-monospace,SFMono-Regular,&quot;Cascadia Mono&quot;,Menlo,Consolas,monospace'
SANS = '-apple-system,&quot;Segoe UI&quot;,Helvetica,Arial,sans-serif'


def banner(c: dict) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 340" width="1200" height="340" role="img" aria-labelledby="t d">
  <title id="t">ccx — Claude Code and Codex hand work to each other</title>
  <desc id="d">Claude Code hands a task to Codex; ccx routes it to a small model, Codex finishes in one attempt, and the result is verified at a cost of $0.0023 (a real run).</desc>
  <rect width="1200" height="340" rx="16" fill="{c['bg']}"/>
  <g font-family="{MONO}">
    <text x="64" y="122" font-size="84" font-weight="700" fill="{c['ink']}">ccx</text>
  </g>
  <g font-family="{SANS}">
    <text x="64" y="178" font-size="30" font-weight="600" fill="{c['ink']}">Claude Code ⇄ Codex,</text>
    <text x="64" y="216" font-size="30" font-weight="600" fill="{c['ink']}">each other's sub-agent</text>
    <text x="64" y="262" font-size="21" fill="{c['muted']}">The cheapest model likely to finish each piece —</text>
    <text x="64" y="292" font-size="21" fill="{c['muted']}">checked, and with the receipt.</text>
  </g>
  <g font-family="{MONO}">
    <rect x="640" y="32" width="512" height="276" rx="12" fill="{c['card']}" stroke="{c['line']}"/>
    <rect x="672" y="58" width="300" height="44" rx="8" fill="{c['amber']}"/>
    <text x="692" y="88" font-size="21" font-weight="600" fill="{c['on']}">Claude Code · lead</text>
    <path d="M700 102 V 138 M692 130 L700 140 L708 130" stroke="{c['arrow']}" stroke-width="2.5" fill="none"/>
    <text x="724" y="128" font-size="18" fill="{c['muted']}">route b=2 → luna · low · p 0.95</text>
    <rect x="672" y="146" width="380" height="44" rx="8" fill="{c['teal']}"/>
    <text x="692" y="176" font-size="21" font-weight="600" fill="{c['on']}">Codex · done, 1 attempt</text>
    <path d="M700 190 V 226 M692 218 L700 228 L708 218" stroke="{c['arrow']}" stroke-width="2.5" fill="none"/>
    <text x="724" y="216" font-size="18" fill="{c['muted']}">you check the diff</text>
    <text x="672" y="268" font-size="24" font-weight="700" fill="{c['ok']}">✓ verified</text>
    <text x="860" y="268" font-size="24" font-weight="700" fill="{c['ink']}">$0.0023</text>
    <text x="990" y="268" font-size="17" fill="{c['muted']}">real run</text>
  </g>
</svg>
"""


def _box(x, y, w, h, c, title, lines, accent=None):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{c["card"]}" stroke="{c["line"]}"/>']
    if accent:
        out.append(f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{accent}"/>')
    out.append(f'<text x="{x + 22}" y="{y + 32}" font-size="19" font-weight="600" fill="{c["ink"]}" '
               f'font-family="{SANS}">{title}</text>')
    for i, ln in enumerate(lines):
        out.append(f'<text x="{x + 22}" y="{y + 60 + i * 24}" font-size="15" fill="{c["muted"]}" '
                   f'font-family="{MONO}">{ln}</text>')
    return "\n  ".join(out)


def _arrow(path, c, label=None, lx=0, ly=0, both=False):
    head = f'marker-end="url(#a)"' + (' marker-start="url(#a)"' if both else "")
    s = f'<path d="{path}" stroke="{c["arrow"]}" stroke-width="2" fill="none" {head}/>'
    if label:
        s += (f'\n  <text x="{lx}" y="{ly}" font-size="14" fill="{c["muted"]}" font-family="{MONO}" '
              f'text-anchor="middle">{label}</text>')
    return s


def architecture(c: dict) -> str:
    # top: the two tools with ccx between them; bottom: where things live. Lines never cross.
    parts = [
        _box(40, 40, 290, 150, c, "Claude Code", ["lead or sub-agent", "terminal / desktop app"], c["amber"]),
        _box(870, 40, 290, 150, c, "Codex", ["lead or sub-agent", "Gemini CLI: optional"], c["teal"]),
        _box(450, 40, 300, 150, c, "ccx", ["route → agent:model:effort", "run → headless, JSON back",
                                           "verify → routing learns", "writes the ledger"]),
        _box(40, 300, 520, 200, c, "Your hub · personal, never in the repo",
             ["memory snapshot + journal", "skills · MCP registry", "ledger · learned estimates",
              "settings · archived sessions"]),
        _box(640, 300, 520, 200, c, "Project · &lt;project&gt;/.ccx/",
             ["context.md — every sub-agent reads it", "journal · inbox · handoff",
              "tasks/ — checkpoints for resuming", "read by whichever agent works here"]),
        _arrow("M330 100 H 448", c, "brief", 389, 90),
        _arrow("M750 90 H 868", c, "run", 809, 80),
        _arrow("M868 140 H 752", c, "JSON", 809, 162),
        _arrow("M185 298 V 192", c),
        _arrow("M420 298 V 245 H 1015 V 192", c),
        f'<text x="718" y="236" font-size="14" fill="{c["muted"]}" font-family="{MONO}" text-anchor="middle">'
        'to both tools: session-start hook · skills · MCP</text>',
    ]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 540" width="1200" height="540" role="img" aria-labelledby="t d">
  <title id="t">How ccx connects Claude Code, Codex, your hub and the project</title>
  <desc id="d">Either tool leads; ccx routes a brief to the other tool, runs it headless and returns a JSON result. A session-start hook brings new memory, handoffs and unfinished tasks from your personal hub; skills and MCP are linked into both tools; the project's .ccx folder holds context, journal, inbox, handoff, checkpoints and undo snapshots.</desc>
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0 0 L10 5 L0 10 z" fill="{c['arrow']}"/></marker></defs>
  <rect width="1200" height="540" rx="16" fill="{c['bg']}"/>
  {chr(10).join('  ' + p for p in parts).strip()}
</svg>
"""


def social_preview(path: Path) -> bool:
    """1280×640 PNG for GitHub's social preview (Settings → Social preview), drawn with Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("skip social preview: pip install pillow")
        return False
    c = THEMES["dark"]

    def font(names, size):
        for n in names:
            try:
                return ImageFont.truetype(n, size)
            except OSError:
                continue
        return ImageFont.load_default(size)
    mono_b = lambda s: font(["consolab.ttf", "DejaVuSansMono-Bold.ttf", "Menlo.ttc"], s)   # noqa: E731
    mono = lambda s: font(["consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc"], s)          # noqa: E731
    sans_b = lambda s: font(["seguisb.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc"], s)   # noqa: E731
    sans = lambda s: font(["segoeui.ttf", "DejaVuSans.ttf", "Helvetica.ttc"], s)          # noqa: E731
    sym = lambda s: font(["seguisym.ttf", "DejaVuSans.ttf", "Apple Symbols.ttf"], s)     # noqa: E731

    def runs(xy, parts):
        """Draw text in pieces, so a glyph the main font lacks (⇄, ✓) comes from a symbol font."""
        x, y = xy
        for text, f, fill in parts:
            d.text((x, y), text, font=f, fill=fill)
            x += d.textlength(text, font=f)
    img = Image.new("RGB", (1280, 640), c["bg"])
    d = ImageDraw.Draw(img)
    d.text((80, 96), "ccx", font=mono_b(150), fill=c["ink"])
    runs((84, 300), [("Claude Code ", sans_b(56), c["ink"]), ("⇄", sym(52), c["ink"]),
                     (" Codex,", sans_b(56), c["ink"])])
    d.text((84, 372), "each other's sub-agent", font=sans_b(56), fill=c["ink"])
    d.text((86, 470), "The cheapest model likely to finish each piece —", font=sans(30), fill=c["muted"])
    d.text((86, 512), "checked, and with the receipt.", font=sans(30), fill=c["muted"])
    x0 = 860
    d.rounded_rectangle((x0, 120, 1200, 176), 12, fill=c["amber"])
    d.text((x0 + 22, 132), "Claude Code", font=mono_b(30), fill=c["on"])
    d.line((x0 + 40, 180, x0 + 40, 230), fill=c["arrow"], width=4)
    d.rounded_rectangle((x0, 234, 1200, 290), 12, fill=c["teal"])
    d.text((x0 + 22, 246), "Codex", font=mono_b(30), fill=c["on"])
    d.line((x0 + 40, 294, x0 + 40, 344), fill=c["arrow"], width=4)
    runs((x0, 356), [("✓", sym(32), c["ok"]), (" verified", mono_b(32), c["ok"])])
    d.text((x0, 404), "$0.0023", font=mono_b(32), fill=c["ink"])
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    return True


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, c in THEMES.items():
        (OUT / f"banner-{name}.svg").write_text(banner(c), encoding="utf-8")
        (OUT / f"architecture-{name}.svg").write_text(architecture(c), encoding="utf-8")
    made = social_preview(OUT / "social-preview.png")
    print("wrote", sorted(p.name for p in OUT.iterdir()), "(social preview)" if made else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
