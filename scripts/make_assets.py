"""Regenerate the static images in docs/assets/ (banner, architecture, social preview).

Names only, no vendor logos or marks.

    python scripts/make_assets.py

Light and dark versions come from one template, so they never drift apart. The social preview PNG needs Pillow
(`pip install pillow`); the SVGs need nothing. Numbers in the banner are from a real run (see docs/STATUS.md)."""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"

THEMES = {
    "light": dict(bg="#f6f7f9", card="#ffffff", line="#d8dce3", ink="#1c2129", muted="#5b6573", amber="#b4690e",
                  teal="#0f7c80", ok="#1f7a3a", arrow="#8b95a3", on="#ffffff", soft="#eef1f5", violet="#6e4fc4"),
    "dark": dict(bg="#0f1318", card="#161b22", line="#2b323c", ink="#e7ebf0", muted="#97a1ae", amber="#e3a14e",
                 teal="#4cc3c6", ok="#58c27a", arrow="#6b7684", on="#0f1318", soft="#1d242d", violet="#a990ec"),
}
MONO = 'ui-monospace,SFMono-Regular,&quot;Cascadia Mono&quot;,Menlo,Consolas,monospace'
SANS = '-apple-system,&quot;Segoe UI&quot;,Helvetica,Arial,sans-serif'


def banner(c: dict) -> str:
    chip = lambda x, y, w, label, fill: (  # noqa: E731
        f'<rect x="{x}" y="{y}" width="{w}" height="40" rx="8" fill="{fill}"/>'
        f'<text x="{x + w / 2}" y="{y + 27}" font-size="19" font-weight="600" fill="{c["on"]}" '
        f'text-anchor="middle">{label}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 340" width="1200" height="340" role="img" aria-labelledby="t d">
  <title id="t">relayline (ccx): coding agents take turns as each other's lead and sub-agent</title>
  <desc id="d">Claude Code, Codex and DeepSeek each can lead or work (Gemini CLI: sub-agent adapter only, not run for real). ccx picks a cheap model likely to finish, reruns the check, has another vendor review the diff, and records the cost. Example from a real run: Codex gpt-6-luna low, one attempt, $0.0023.</desc>
  <rect width="1200" height="340" rx="16" fill="{c['bg']}"/>
  <g font-family="{SANS}">
    <text x="64" y="118" font-size="76" font-weight="700" fill="{c['ink']}">relayline</text>
    <text x="68" y="160" font-size="22" fill="{c['muted']}" font-family="{MONO}">command: ccx</text>
    <text x="64" y="214" font-size="28" font-weight="600" fill="{c['ink']}">Coding agents as each other's</text>
    <text x="64" y="250" font-size="28" font-weight="600" fill="{c['ink']}">lead and sub-agent</text>
    <text x="64" y="294" font-size="20" fill="{c['muted']}">Shared memory · the cheapest model likely to finish ·</text>
    <text x="64" y="320" font-size="20" fill="{c['muted']}">checked, reviewed, and with the receipt.</text>
  </g>
  <g font-family="{MONO}">
    <rect x="640" y="28" width="512" height="284" rx="12" fill="{c['card']}" stroke="{c['line']}"/>
    {chip(664, 50, 150, "Claude Code", c['amber'])}
    {chip(822, 50, 110, "Codex", c['teal'])}
    {chip(940, 50, 150, "DeepSeek", c['violet'])}
    <text x="664" y="124" font-size="16" fill="{c['muted']}">any of the three leads · any of them works</text>
    <rect x="664" y="140" width="464" height="40" rx="8" fill="{c['soft']}" stroke="{c['line']}"/>
    <text x="682" y="167" font-size="18" fill="{c['ink']}">ccx route → codex · luna · low</text>
    <text x="664" y="212" font-size="17" fill="{c['ok']}">✓ check rerun</text>
    <text x="840" y="212" font-size="17" fill="{c['ok']}">✓ other-vendor review</text>
    <text x="664" y="240" font-size="17" fill="{c['muted']}">shared memory · handoff · ccx ui</text>
    <line x1="664" y1="258" x2="1128" y2="258" stroke="{c['line']}"/>
    <text x="664" y="292" font-size="22" font-weight="700" fill="{c['ok']}">✓ verified</text>
    <text x="840" y="292" font-size="22" font-weight="700" fill="{c['ink']}">$0.0023</text>
    <text x="960" y="292" font-size="16" fill="{c['muted']}">one real run</text>
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
    # top: the agent CLIs; middle: ccx; bottom: personal layer, project layer, the local page. Lines never cross.
    parts = [
        _box(40, 40, 350, 130, c, "Claude Code", ["lead or worker", "DeepSeek through it: optional"], c["amber"]),
        _box(425, 40, 350, 130, c, "Codex", ["lead or worker", "terminal / desktop app"], c["teal"]),
        _box(810, 40, 350, 130, c, "Gemini CLI", ["worker (adapter; not run live)", "one adapter per CLI"],
             c["violet"]),
        _box(200, 250, 800, 150, c, "ccx", ["route → agent:model:effort · or “do it yourself”",
                                            "run → headless, JSON back · check rerun · other-vendor review",
                                            "verify / auto verdicts → routing learns · ledger · ccx lead"]),
        _box(40, 480, 350, 140, c, "Personal layer · your hub",
             ["memory snapshot + journal", "skills · MCP registry", "ledger · learned estimates"]),
        _box(425, 480, 350, 140, c, "Project layer · .ccx/",
             ["context.md · journal · inbox", "handoffs · checkpoints", "undo snapshots · queue"]),
        _box(810, 480, 350, 140, c, "ccx ui · local page",
             ["127.0.0.1, read-only, no model", "what waits for you · who works", "quota at this pace"]),
        _arrow("M215 172 V 248", c, both=True),
        _arrow("M600 172 V 248", c, both=True),
        _arrow("M985 172 V 248", c, both=True),
        f'<text x="600" y="215" font-size="14" fill="{c["muted"]}" font-family="{MONO}" text-anchor="middle" '
        f'dx="110">brief ↓ · JSON ↑</text>',
        _arrow("M300 402 V 478", c, both=True),
        _arrow("M600 402 V 478", c, both=True),
        _arrow("M900 402 V 478", c),
        f'<text x="450" y="436" font-size="14" fill="{c["muted"]}" font-family="{MONO}" text-anchor="middle">'
        'session-start hook:</text>',
        f'<text x="450" y="456" font-size="14" fill="{c["muted"]}" font-family="{MONO}" text-anchor="middle">'
        'new memory · handoffs</text>',
        f'<text x="900" y="445" font-size="14" fill="{c["muted"]}" font-family="{MONO}" dx="12">reads files only</text>',
    ]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 660" width="1200" height="660" role="img" aria-labelledby="t d">
  <title id="t">How ccx connects the agent CLIs, your hub, the project and the local page</title>
  <desc id="d">Claude Code, Codex and Gemini CLI each connect to ccx; any of them can lead and hand a brief to another, which runs headless and returns JSON. ccx routes, reruns the check, asks another vendor to review, records verdicts and costs. Below: the personal layer (your hub: memory, skills, MCP, ledger), the project layer (.ccx: context, journal, handoffs, checkpoints, undo snapshots) and ccx ui, a local read-only page.</desc>
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0 0 L10 5 L0 10 z" fill="{c['arrow']}"/></marker></defs>
  <rect width="1200" height="660" rx="16" fill="{c['bg']}"/>
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
    d.text((80, 90), "relayline", font=sans_b(120), fill=c["ink"])
    d.text((86, 246), "command: ccx", font=mono(34), fill=c["muted"])
    d.text((84, 330), "Coding agents as each other's", font=sans_b(52), fill=c["ink"])
    d.text((84, 396), "lead and sub-agent", font=sans_b(52), fill=c["ink"])
    d.text((86, 490), "Shared memory · cheapest model likely to finish", font=sans(30), fill=c["muted"])
    d.text((86, 532), "checked, reviewed, with the receipt", font=sans(30), fill=c["muted"])
    x0 = 900
    for i, (name, col) in enumerate((("Claude Code", c["amber"]), ("Codex", c["teal"]), ("DeepSeek", c["violet"]))):
        y = 130 + i * 92
        d.rounded_rectangle((x0, y, 1200, y + 60), 12, fill=col)
        d.text((x0 + 24, y + 13), name, font=mono_b(30), fill=c["on"])
    d.text((x0, 418), "each leads · each works", font=mono(28), fill=c["muted"])
    runs((x0, 470), [("✓", sym(32), c["ok"]), (" verified", mono_b(32), c["ok"])])
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
