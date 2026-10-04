"""Game report exporters (Phase 6): a self-contained HTML "web" report and a
print-grade PDF, both built from the same statistics as the in-app report.

The HTML file is fully standalone (inline CSS + inline SVG) so the user can
open or share it with no server. The PDF is drawn with ReportLab -- no external
binaries -- so it works inside the packaged Windows .exe.
"""
from __future__ import annotations

import html
import math
from typing import Any

from . import stats

# ---------------------------------------------------------------------------
# Shared colour vocabulary
# ---------------------------------------------------------------------------
SPRAY_COLORS = {"hit": "#35d07f", "out": "#ff5470", "other": "#ffc857"}
BAT_COLS = [("AB", "AB"), ("R", "R"), ("H", "H"), ("2B", "2B"), ("3B", "3B"),
            ("HR", "HR"), ("RBI", "RBI"), ("BB", "BB"), ("SO", "SO"),
            ("AVG", "AVG"), ("OPS", "OPS")]
PIT_COLS = [("IP", "IP"), ("BF", "BF"), ("H", "H"), ("R", "R"), ("ER", "ER"),
            ("BB", "BB"), ("SO", "SO"), ("HR", "HR"), ("ERA", "ERA"),
            ("WHIP", "WHIP")]


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


# Rate stats shown to 3 decimals as .XXX (leading zero dropped when < 1).
_RATE3 = {"AVG", "OBP", "SLG", "OPS", "ISO", "BABIP", "SB%", "CS%", "FPCT"}
# Rate stats shown to 2 decimals.
_RATE2 = {"ERA", "WHIP", "K9", "K/9", "BB9", "FIP"}


def _fmt(v, key=None) -> str:
    if v is None:
        return ""
    if key in _RATE3:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        s = "%.3f" % f
        return s.lstrip("0") if 0 <= f < 1 else s
    if key in _RATE2:
        try:
            return "%.2f" % float(v)
        except (TypeError, ValueError):
            return str(v)
    if key == "IP":
        # innings pitched already formatted upstream (e.g. 5.2); pass through
        return str(v)
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        s = "%.3f" % v
        return s.lstrip("0") if 0 <= v < 1 else "%.2f" % v
    return str(v)


def _heat_color(intensity: float) -> str:
    hue = round(220 - 210 * intensity)
    a = 0.12 + 0.85 * intensity
    return "hsla(%d,82%%,52%%,%.2f)" % (hue, a)


# ---------------------------------------------------------------------------
# SVG builders (used by the HTML export)
# ---------------------------------------------------------------------------
_CORE = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]


def _hz_cell_svg(z, zones, x, y, w, h):
    d = zones.get(str(z)) or zones.get(z) or {"pitches": 0, "strike_pct": 0, "intensity": 0}
    fill = _heat_color(d.get("intensity", 0))
    pct = round(d.get("strike_pct", 0) * 100) if d.get("pitches") else 0
    n = d.get("pitches", 0)
    s = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" '
         'stroke="rgba(255,255,255,.10)"/>' % (x, y, w, h, fill)]
    if n:
        s.append('<text x="%.1f" y="%.1f" fill="#eaf1fb" font-size="13" font-weight="700" '
                 'text-anchor="middle">%d</text>' % (x + w / 2, y + h / 2, n))
        s.append('<text x="%.1f" y="%.1f" fill="#a8bbd6" font-size="9" '
                 'text-anchor="middle">%d%%</text>' % (x + w / 2, y + h / 2 + 13, pct))
    return "".join(s)


def heatmap_svg(hm) -> str:
    """288x288 strike-zone heatmap: 3x3 core + 4 chase corners + plate."""
    z = hm["zones"]
    if not hm["total"]["pitches"]:
        return '<div class="nodata">No pitch-by-pitch data recorded for this game.</div>'
    pad, size = 44, 200
    cell = size / 3
    parts = ['<svg viewBox="0 0 288 288" width="288" height="288" class="svgbox">']
    parts.append('<rect x="0" y="0" width="288" height="288" rx="10" fill="#111c30" stroke="#1e3050"/>')
    parts.append(_hz_cell_svg(11, z, 4, 4, pad - 6, pad - 6))
    parts.append(_hz_cell_svg(12, z, 288 - pad + 2, 4, pad - 6, pad - 6))
    parts.append(_hz_cell_svg(13, z, 4, 288 - pad + 2, pad - 6, pad - 6))
    parts.append(_hz_cell_svg(14, z, 288 - pad + 2, 288 - pad + 2, pad - 6, pad - 6))
    for ri, row in enumerate(_CORE):
        for ci, zn in enumerate(row):
            parts.append(_hz_cell_svg(zn, z, pad + ci * cell, pad + ri * cell, cell, cell))
    parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
                 'stroke="#294066" stroke-width="2"/>' % (pad, pad, size, size))
    parts.append('<polygon points="124,270 164,270 164,278 144,286 124,278" '
                 'fill="#13223a" stroke="#294066"/>')
    parts.append('</svg>')
    return "".join(parts)


def spray_svg(sp, size: int = 340) -> str:
    """Fan-shaped field with colour-coded batted-ball dots (standalone HTML)."""
    if not sp["total"]:
        return '<div class="nodata">No batted-ball data for this game.</div>'
    W = size
    H = int(size * 0.94)
    hx, hy = 0.5 * W, 0.95 * H

    def pt(ang, rad):
        r = math.radians(ang)
        # Wider fan: foul lines open to ~±48° and reach close to the top corners
        # so batted-ball dots (normalised 0..1) sit inside the playable area.
        return (hx + rad * 0.62 * W * math.sin(r), hy - rad * 0.90 * H * math.cos(r))

    def P(a):
        return "%.1f,%.1f" % (a[0], a[1])

    lf = pt(-48, 1.05); cf = pt(0, 1.08); rf = pt(48, 1.05)
    b1 = pt(45, .42); b2 = pt(0, .52); b3 = pt(-45, .42)
    g1 = pt(45, .30); g2 = pt(0, .40); g3 = pt(-45, .30); mound = pt(0, .30)
    parts = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" class="svgbox" '
             'preserveAspectRatio="xMidYMid meet">' % (W, H, W, H)]
    parts.append('<defs><radialGradient id="sg" cx="50%%" cy="90%%" r="95%%">'
                 '<stop offset="0%%" stop-color="#1c5b34"/>'
                 '<stop offset="100%%" stop-color="#0f3d22"/></radialGradient></defs>')
    parts.append('<rect x="0" y="0" width="%d" height="%d" rx="12" fill="#08131f" stroke="#1e3050"/>' % (W, H))
    parts.append('<path d="M%.1f,%.1f L%s Q%.1f,%.1f %s Z" fill="url(#sg)" stroke="#2f7d4c"/>'
                 % (hx, hy, P(lf), cf[0], cf[1] - 24, P(rf)))
    parts.append('<polygon points="%.1f,%.1f %s %s %s" fill="#7a5230" stroke="#93673d" stroke-width="1.5"/>'
                 % (hx, hy, P(b1), P(b2), P(b3)))
    parts.append('<polygon points="%.1f,%.1f %s %s %s" fill="#1c5b34"/>'
                 % (hx, hy - 6, P(g1), P(g2), P(g3)))
    parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#dfe8f5" stroke-width="1.5" stroke-dasharray="5 4"/>'
                 % (hx, hy, lf[0], lf[1]))
    parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#dfe8f5" stroke-width="1.5" stroke-dasharray="5 4"/>'
                 % (hx, hy, rf[0], rf[1]))
    for bp in (b1, b2, b3):
        parts.append('<rect x="%.1f" y="%.1f" width="8" height="8" transform="rotate(45 %.1f %.1f)" '
                     'fill="#f4f7fb" stroke="#20303f"/>' % (bp[0] - 4, bp[1] - 4, bp[0], bp[1]))
    parts.append('<circle cx="%.1f" cy="%.1f" r="7" fill="#93673d" stroke="#b07f4c"/>' % (mound[0], mound[1]))
    for p in sp["points"]:
        col = SPRAY_COLORS.get(p["cat"], "#9db")
        r = 5.5 if p.get("contact") == "hard" else (3.5 if p.get("contact") == "soft" else 4.5)
        op = 0.95 if p.get("exact") else 0.6
        parts.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="%.2f" '
                     'stroke="#07101c" stroke-width=".8"><title>%s \u2014 %s%s</title></circle>' % (
                         p["x"] * W, p["y"] * H, r, col, op, _e(p["label"]), _e(p["batter"]),
                         (" (" + _e(p["bb_type"]) + ")") if p["bb_type"] else ""))
    parts.append('</svg>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# HTML report (standalone "web" export)
# ---------------------------------------------------------------------------
_CSS = """
*{box-sizing:border-box}body{margin:0;font-family:'Segoe UI',system-ui,Arial,sans-serif;
background:#070d18;color:#eaf1fb;padding:28px}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:24px;margin:0 0 2px}.sub{color:#6f86a8;font-size:14px;margin-bottom:22px}
.line{border-collapse:collapse;margin:0 0 26px;font-variant-numeric:tabular-nums}
.line th,.line td{border:1px solid #1e3050;padding:6px 10px;text-align:center;font-size:13px}
.line th{color:#6f86a8;background:#0f1b2e}.line td.tm{text-align:left;font-weight:600}
.viz{display:flex;gap:26px;flex-wrap:wrap;margin:0 0 26px;align-items:flex-start}
.card{background:#0f1b2e;border:1px solid #1e3050;border-radius:12px;padding:16px;flex:1;min-width:320px}
.card h2{font-size:15px;margin:0 0 12px}.svgbox{max-width:100%}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:#a8bbd6;margin-top:10px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
.kv{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:#a8bbd6;margin-top:8px}
.kv b{color:#eaf1fb}.nodata{color:#6f86a8;font-size:13px;padding:20px 0}
.side{margin:0 0 22px}.side h2{font-size:15px;margin:18px 0 8px;color:#4d94ff}
table.box{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
table.box th,table.box td{padding:7px 9px;border-bottom:1px solid #1e3050;text-align:right}
table.box th{color:#6f86a8;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
table.box th.l,table.box td.l{text-align:left}
.foot{color:#6f86a8;font-size:11px;margin-top:24px;border-top:1px solid #1e3050;padding-top:12px}
"""


def _box_table(rows, cols) -> str:
    if not rows:
        return '<p class="nodata">No data.</p>'
    head = '<th class="l">Player</th>' + "".join('<th>%s</th>' % _e(l) for _, l in cols)
    body = []
    for r in rows:
        tds = "".join('<td>%s</td>' % _e(_fmt(r.get(k), k)) for k, _ in cols)
        body.append('<tr><td class="l">%s</td>%s</tr>' % (_e(r.get("name")), tds))
    return ('<table class="box"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (head, "".join(body)))


def _line_table(rep) -> str:
    g = rep["game"]
    line = rep.get("line") or {}
    innings = line.get("innings") or []
    totals = line.get("totals") or {"away": {}, "home": {}}

    def row(side_key, name):
        per = line.get(side_key) or []
        cells = "".join('<td>%s</td>' % _e(per[i] if i < len(per) else "")
                        for i in range(len(innings)))
        tot = totals.get(side_key, {})
        rhe = "".join('<td>%s</td>' % _e(tot.get(k, 0)) for k in ("R", "H", "E"))
        return '<tr><td class="tm">%s</td>%s%s</tr>' % (_e(name), cells, rhe)

    hdr = "".join('<th>%s</th>' % _e(i) for i in innings)
    return ('<table class="line"><thead><tr><th class="tm">Team</th>%s'
            '<th>R</th><th>H</th><th>E</th></tr></thead><tbody>%s%s</tbody></table>'
            % (hdr, row("away", g["away_name"]), row("home", g["home_name"])))


def _viz_block(rep) -> str:
    hm, sp = rep["heatmap"], rep["spray"]
    hm_kv = ""
    if hm["total"]["pitches"]:
        hm_kv = ('<div class="kv"><span><b>%d</b> pitches</span>'
                 '<span><b>%d%%</b> strikes</span><span><b>%d%%</b> swing</span>'
                 '<span><b>%d%%</b> whiff</span>%s</div>' % (
                     hm["total"]["pitches"], round(hm["strike_pct"] * 100),
                     round(hm["swing_pct"] * 100), round(hm["whiff_pct"] * 100),
                     ('<span><b>%s</b> mph avg</span>' % hm["avg_velo"]) if hm.get("avg_velo") else ""))
    legend = ('<div class="legend">'
              '<span><i class="dot" style="background:%s"></i>Hit</span>'
              '<span><i class="dot" style="background:%s"></i>Out</span>'
              '<span><i class="dot" style="background:%s"></i>Other</span></div>'
              % (SPRAY_COLORS["hit"], SPRAY_COLORS["out"], SPRAY_COLORS["other"]))
    sp_kv = ('<div class="kv"><span><b>%d</b> batted balls</span>'
             '<span><b>%d</b> hits</span><span><b>%d</b> outs</span></div>%s'
             % (sp["total"], sp["counts"]["hit"], sp["counts"]["out"], legend)) if sp["total"] else ""
    return ('<div class="viz">'
            '<div class="card"><h2>Strike-zone heatmap</h2>%s%s</div>'
            '<div class="card"><h2>Spray chart</h2>%s%s</div></div>'
            % (heatmap_svg(hm), hm_kv, spray_svg(sp), sp_kv))


def _side_block(side) -> str:
    tn = side["team"].get("name", "")
    return ('<div class="side"><h2>%s \u2014 Batting</h2>%s'
            '<h2>%s \u2014 Pitching</h2>%s</div>' % (
                _e(tn), _box_table(side["batting"], BAT_COLS),
                _e(tn), _box_table(side["pitching"], PIT_COLS)))


def build_report_html(game_id: int) -> str:
    rep = stats.game_report(game_id)
    g = rep["game"]
    title = "%s @ %s" % (g["away_name"], g["home_name"])
    sub = _e(g.get("game_date") or "")
    if g.get("venue"):
        sub += " \u00b7 " + _e(g["venue"])
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>%s \u2014 Diamond Scorer</title><style>%s</style></head><body><div class='wrap'>"
        "<h1>%s</h1><div class='sub'>%s</div>%s%s%s%s"
        "<div class='foot'>Generated by Diamond Scorer \u2014 batted-ball spray is "
        "derived from fielder, trajectory and hit value.</div></div></body></html>"
        % (_e(title), _CSS, _e(title), sub, _line_table(rep), _viz_block(rep),
           _side_block(rep["away"]), _side_block(rep["home"]))
    )


# ---------------------------------------------------------------------------
# PDF report (ReportLab -- no external binaries)
# ---------------------------------------------------------------------------
def _heat_rgb(intensity: float):
    import colorsys
    from reportlab.lib import colors
    hue = (220 - 210 * intensity) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.5, 0.7)
    return colors.Color(r, g, b, alpha=0.15 + 0.8 * intensity)


def _heatmap_drawing(hm):
    from reportlab.graphics.shapes import Drawing, Rect, String, Polygon
    from reportlab.lib import colors
    d = Drawing(210, 210)
    if not hm["total"]["pitches"]:
        d.add(String(6, 100, "No pitch data", fillColor=colors.HexColor("#6f86a8"), fontSize=10))
        return d
    z = hm["zones"]
    pad, size = 34, 150
    cell = size / 3.0

    def draw(zn, x, y, w, h):
        cd = z.get(str(zn)) or z.get(zn) or {}
        d.add(Rect(x, y, w, h, fillColor=_heat_rgb(cd.get("intensity", 0)),
                   strokeColor=colors.Color(1, 1, 1, 0.12), strokeWidth=0.5))
        if cd.get("pitches"):
            d.add(String(x + w / 2, y + h / 2, str(cd["pitches"]), textAnchor="middle",
                         fontSize=11, fontName="Helvetica-Bold", fillColor=colors.HexColor("#eaf1fb")))
            pct = round(cd.get("strike_pct", 0) * 100)
            d.add(String(x + w / 2, y + h / 2 - 11, "%d%%" % pct, textAnchor="middle",
                         fontSize=7, fillColor=colors.HexColor("#a8bbd6")))
    # corners (y inverted: reportlab origin bottom-left)
    draw(13, 2, 2, pad - 5, pad - 5)
    draw(14, 210 - pad + 3, 2, pad - 5, pad - 5)
    draw(11, 2, 210 - pad + 3, pad - 5, pad - 5)
    draw(12, 210 - pad + 3, 210 - pad + 3, pad - 5, pad - 5)
    order = [[7, 8, 9], [4, 5, 6], [1, 2, 3]]  # bottom-up rows
    for ri, rowz in enumerate(order):
        for ci, zn in enumerate(rowz):
            draw(zn, pad + ci * cell, pad + ri * cell, cell, cell)
    d.add(Rect(pad, pad, size, size, fillColor=None,
               strokeColor=colors.HexColor("#294066"), strokeWidth=1.5))
    return d


def _spray_drawing(sp):
    import math as _m
    from reportlab.graphics.shapes import Drawing, Circle, Polygon, Line, String
    from reportlab.lib import colors
    S = 210
    d = Drawing(S, S)
    if not sp["total"]:
        d.add(String(6, 100, "No batted-ball data", fillColor=colors.HexColor("#6f86a8"), fontSize=10))
        return d
    # reportlab y is bottom-up, so home plate near the bottom.
    hx, hy = 0.5 * S, 0.10 * S

    def pt(ang, rad):
        r = _m.radians(ang)
        return (0.5 * S + rad * 0.5 * S * _m.sin(r), 0.10 * S + rad * 0.86 * S * _m.cos(r))

    lf = pt(-45, 1.0); rf = pt(45, 1.0); cf = pt(0, 1.02)
    d.add(Polygon([hx, hy, lf[0], lf[1], cf[0], cf[1], rf[0], rf[1]],
                  fillColor=colors.HexColor("#123524"), strokeColor=colors.HexColor("#1e3050")))
    b1 = pt(45, 0.42); b2 = pt(0, 0.52); b3 = pt(-45, 0.42)
    d.add(Polygon([hx, hy, b1[0], b1[1], b2[0], b2[1], b3[0], b3[1]],
                  fillColor=colors.HexColor("#3a2a18"), strokeColor=colors.HexColor("#5a4326")))
    d.add(Line(hx, hy, lf[0], lf[1], strokeColor=colors.HexColor("#6f86a8"), strokeDashArray=[3, 3]))
    d.add(Line(hx, hy, rf[0], rf[1], strokeColor=colors.HexColor("#6f86a8"), strokeDashArray=[3, 3]))
    for p in sp["points"]:
        col = colors.HexColor(SPRAY_COLORS.get(p["cat"], "#99ddbb"))
        rr = 3.6 if p.get("contact") == "hard" else (2.2 if p.get("contact") == "soft" else 2.9)
        # flip y from the normalised (top-down) coord to reportlab bottom-up
        d.add(Circle(p["x"] * S, (1 - p["y"]) * S, rr, fillColor=col,
                     strokeColor=colors.HexColor("#07101c"), strokeWidth=0.4))
    return d


def build_report_pdf(game_id: int) -> bytes:
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepTogether)

    rep = stats.game_report(game_id)
    g = rep["game"]
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, spaceAfter=2,
                        textColor=colors.HexColor("#0b1f3a"))
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=10,
                         textColor=colors.HexColor("#5a6b82"), spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12,
                        textColor=colors.HexColor("#1c4f8f"), spaceBefore=8, spaceAfter=4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm,
                            title="%s @ %s" % (g["away_name"], g["home_name"]))
    story = [Paragraph("%s @ %s" % (_e(g["away_name"]), _e(g["home_name"])), h1)]
    subtxt = _e(g.get("game_date") or "")
    if g.get("venue"):
        subtxt += " &middot; " + _e(g["venue"])
    story.append(Paragraph(subtxt or "&nbsp;", sub))

    # line score
    line = rep.get("line") or {}
    innings = line.get("innings") or []
    totals = line.get("totals") or {"away": {}, "home": {}}
    header = ["Team"] + [str(i) for i in innings] + ["R", "H", "E"]
    def lrow(sk, name):
        per = line.get(sk) or []
        t = totals.get(sk, {})
        return [name] + [str(per[i]) if i < len(per) else "" for i in range(len(innings))] + \
               [str(t.get("R", 0)), str(t.get("H", 0)), str(t.get("E", 0))]
    ldata = [header, lrow(g["away_name"], g["away_name"]), lrow(g["home_name"], g["home_name"])]
    lt = Table(ldata)
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eff7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#33455e")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c3cfe0")),
        ("BACKGROUND", (-3, 0), (-1, -1), colors.HexColor("#f4f7fb")),
    ]))
    story += [lt, Spacer(1, 10)]

    # heatmap + spray side by side
    hd = _heatmap_drawing(rep["heatmap"])
    sd = _spray_drawing(rep["spray"])
    viz = Table([[Paragraph("Strike-zone heatmap", h2), Paragraph("Spray chart", h2)],
                 [hd, sd]], colWidths=[85 * mm, 85 * mm])
    viz.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story += [KeepTogether(viz), Spacer(1, 10)]

    def box(side, cols):
        rows = side
        if not rows:
            return Paragraph("No data.", ss["Normal"])
        head = ["Player"] + [l for _, l in cols]
        data = [head]
        for r in rows:
            data.append([str(r.get("name", ""))] + [_fmt(r.get(k), k) for k, _ in cols])
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1c4f8f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fc")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6dfed")),
        ]))
        return t

    for side, label in ((rep["away"], g["away_name"]), (rep["home"], g["home_name"])):
        story.append(Paragraph("%s &mdash; Batting" % _e(label), h2))
        story.append(box(side["batting"], BAT_COLS))
        story.append(Paragraph("%s &mdash; Pitching" % _e(label), h2))
        story.append(box(side["pitching"], PIT_COLS))
        story.append(Spacer(1, 8))

    doc.build(story)
    return buf.getvalue()
