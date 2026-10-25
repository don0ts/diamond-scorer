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
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:'Inter','Segoe UI',system-ui,-apple-system,Arial,sans-serif;
  color:#e8eefb;padding:40px 24px;line-height:1.5;
  background:#060b16;
  background-image:radial-gradient(1200px 520px at 50% -140px,rgba(77,148,255,.16),transparent 60%),
    radial-gradient(900px 500px at 100% 0,rgba(53,208,127,.08),transparent 55%);}
.wrap{max-width:1000px;margin:0 auto}
.wrap::before{content:"";display:block;width:52px;height:4px;border-radius:4px;
  background:linear-gradient(90deg,#4d94ff,#35d07f);margin:0 0 20px}
h1{font-size:30px;line-height:1.15;margin:0 0 6px;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(90deg,#eaf1fb,#9fc2ff);-webkit-background-clip:text;
  background-clip:text;color:transparent}
.sub{color:#8aa0c0;font-size:14px;margin-bottom:30px;font-weight:500;letter-spacing:.2px}
.line{border-collapse:separate;border-spacing:0;margin:0 0 30px;width:100%;
  font-variant-numeric:tabular-nums;border:1px solid #1c2c48;border-radius:14px;
  overflow:hidden;box-shadow:0 10px 30px -18px rgba(0,0,0,.8)}
.line th,.line td{border-bottom:1px solid #16243c;border-right:1px solid #16243c;
  padding:9px 12px;text-align:center;font-size:13px}
.line tr td:last-child,.line tr th:last-child{border-right:none}
.line tbody tr:last-child td{border-bottom:none}
.line th{color:#7f97ba;background:#0d1729;font-weight:600;font-size:11px;
  text-transform:uppercase;letter-spacing:.6px}
.line td.tm{text-align:left;font-weight:700;color:#eaf1fb}
.line td:nth-last-child(-n+3){font-weight:700;background:rgba(77,148,255,.05)}
.viz{display:flex;gap:24px;flex-wrap:wrap;margin:0 0 30px;align-items:stretch}
.card{background:linear-gradient(180deg,#101d33,#0c1727);border:1px solid #1c2c48;
  border-radius:16px;padding:20px;flex:1;min-width:320px;
  box-shadow:0 14px 40px -24px rgba(0,0,0,.9)}
.card h2{font-size:12px;margin:0 0 16px;color:#7f97ba;text-transform:uppercase;
  letter-spacing:1.4px;font-weight:700}
.svgbox{max-width:100%}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#9fb4d4;margin-top:12px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
.kv{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:#9fb4d4;margin-top:12px}
.kv span{background:#0c1829;border:1px solid #1c2c48;border-radius:999px;padding:4px 11px}
.kv b{color:#eaf1fb;font-weight:700}
.nodata{color:#7f97ba;font-size:13px;padding:22px 0;text-align:center}
.side{margin:0 0 26px}
.side h2{font-size:12px;margin:22px 0 10px;color:#4d94ff;text-transform:uppercase;
  letter-spacing:1.4px;font-weight:700;display:flex;align-items:center;gap:10px}
.side h2::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,#1c2c48,transparent)}
table.box{width:100%;border-collapse:separate;border-spacing:0;font-size:13px;
  font-variant-numeric:tabular-nums;border:1px solid #1c2c48;border-radius:14px;
  overflow:hidden}
table.box th,table.box td{padding:9px 11px;border-bottom:1px solid #16243c;text-align:right}
table.box tbody tr:last-child td{border-bottom:none}
table.box thead th{color:#7f97ba;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.5px;background:#0d1729;font-weight:700}
table.box th.l,table.box td.l{text-align:left}
table.box td.l{font-weight:600;color:#eaf1fb}
table.box tbody tr:nth-child(even) td{background:rgba(255,255,255,.018)}
table.box tbody tr.tot td{font-weight:800;color:#eaf1fb;background:rgba(77,148,255,.10);
  border-top:1.5px solid #294066}
table.box tbody tr.tot td.l{color:#9fc2ff;text-transform:uppercase;letter-spacing:.6px;font-size:11px}
.foot{color:#6f86a8;font-size:11px;margin-top:30px;border-top:1px solid #16243c;
  padding-top:14px;letter-spacing:.2px}
@media print{body{background:#060b16 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def _round3(num, den):
    return round(num / den, 3) if den else 0.0


def _box_totals(rows, kind):
    """Team totals row: sum the counting stats and recompute the rate stats
    (AVG/OPS or ERA/WHIP) from those sums rather than averaging per-player
    rates. Returns a row-shaped dict with name='Totals', or None if no rows."""
    if not rows:
        return None
    def S(k):
        return sum((r.get(k) or 0) for r in rows)
    t = {"name": "Totals"}
    if kind == "pit":
        for k in ("BF", "H", "R", "ER", "BB", "SO", "HR", "Outs"):
            t[k] = S(k)
        ip3 = t["Outs"]
        ip = ip3 / 3.0
        t["IP"] = "%d.%d" % (ip3 // 3, ip3 % 3)
        t["ERA"] = round(9 * t["ER"] / ip, 2) if ip else 0.0
        t["WHIP"] = round((t["H"] + t["BB"]) / ip, 2) if ip else 0.0
    else:
        for k in ("AB", "R", "H", "2B", "3B", "HR", "RBI", "BB", "SO",
                  "HBP", "SF", "TB"):
            t[k] = S(k)
        ab, bb, hbp, sf = t["AB"], t["BB"], t["HBP"], t["SF"]
        obp = _round3(t["H"] + bb + hbp, ab + bb + hbp + sf)
        slg = _round3(t["TB"], ab)
        t["AVG"] = _round3(t["H"], ab)
        t["OPS"] = round(obp + slg, 3)
    return t


def _box_table(rows, cols, kind=None) -> str:
    if not rows:
        return '<p class="nodata">No data.</p>'
    if kind is None:
        kind = "pit" if any(k == "IP" for k, _ in cols) else "bat"
    head = '<th class="l">Player</th>' + "".join('<th>%s</th>' % _e(l) for _, l in cols)
    body = []
    for r in rows:
        tds = "".join('<td>%s</td>' % _e(_fmt(r.get(k), k)) for k, _ in cols)
        body.append('<tr><td class="l">%s</td>%s</tr>' % (_e(r.get("name")), tds))
    tot = _box_totals(rows, kind)
    if tot:
        tds = "".join('<td>%s</td>' % _e(_fmt(tot.get(k), k)) for k, _ in cols)
        body.append('<tr class="tot"><td class="l">Totals</td>%s</tr>' % tds)
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


def _pdf_bg(canvas, doc):
    """Paint the dark page background + top accent bar so the PDF matches the
    polished dark HTML export rather than the old white ReportLab look."""
    from reportlab.lib import colors
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#060b16"))
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#4d94ff"))
    canvas.rect(doc.leftMargin, doc.pagesize[1] - doc.topMargin + 16, 52, 4,
                fill=1, stroke=0)
    canvas.restoreState()


def build_report_pdf(game_id: int) -> bytes:
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepTogether, HRFlowable)

    rep = stats.game_report(game_id)
    g = rep["game"]
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=23, spaceAfter=3, leading=26,
                        textColor=colors.HexColor("#eaf1fb"))
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=10.5,
                         textColor=colors.HexColor("#8aa0c0"), spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=10.5, leading=13,
                        textColor=colors.HexColor("#4d94ff"), spaceBefore=12, spaceAfter=5,
                        fontName="Helvetica-Bold")
    foot = ParagraphStyle("foot", parent=ss["Normal"], fontSize=8,
                          textColor=colors.HexColor("#6f86a8"), spaceBefore=12)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=18 * mm, bottomMargin=15 * mm,
                            title="%s @ %s" % (g["away_name"], g["home_name"]))
    story = [Paragraph("%s @ %s" % (_e(g["away_name"]), _e(g["home_name"])), h1)]
    subtxt = _e(g.get("game_date") or "")
    if g.get("venue"):
        subtxt += " &middot; " + _e(g["venue"])
    story.append(Paragraph(subtxt or "&nbsp;", sub))
    story.append(HRFlowable(width="100%", thickness=1.4, color=colors.HexColor("#1c2c48"),
                            spaceBefore=4, spaceAfter=14))

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
    ldata = [header, lrow("away", g["away_name"]), lrow("home", g["home_name"])]
    lt = Table(ldata)
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d1729")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7f97ba")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#0b1424")),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#e8eefb")),
        ("BACKGROUND", (-3, 0), (-1, -1), colors.HexColor("#111f38")),
        ("TEXTCOLOR", (-3, 1), (-1, -1), colors.HexColor("#9fc2ff")),
        ("FONTNAME", (-3, 1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#16243c")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#1c2c48")),
    ]))
    story += [lt, Spacer(1, 14)]

    # heatmap + spray side by side (dark cards matching the HTML export)
    hd = _heatmap_drawing(rep["heatmap"])
    sd = _spray_drawing(rep["spray"])
    viz = Table([[Paragraph("Strike-zone heatmap", h2), Paragraph("Spray chart", h2)],
                 [hd, sd]], colWidths=[85 * mm, 85 * mm])
    viz.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#101d33")),
        ("BOX", (0, 1), (0, 1), 0.8, colors.HexColor("#1c2c48")),
        ("BOX", (1, 1), (1, 1), 0.8, colors.HexColor("#1c2c48")),
        ("TOPPADDING", (0, 1), (-1, 1), 12),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
    ]))
    story += [KeepTogether(viz), Spacer(1, 10)]

    def box(rows, cols, kind):
        if not rows:
            return Paragraph("No data.", sub)
        head = ["Player"] + [l for _, l in cols]
        data = [head]
        for r in rows:
            data.append([str(r.get("name", ""))] + [_fmt(r.get(k), k) for k, _ in cols])
        tot = _box_totals(rows, kind)
        tot_idx = None
        if tot:
            data.append(["Totals"] + [_fmt(tot.get(k), k) for k, _ in cols])
            tot_idx = len(data) - 1
        t = Table(data, repeatRows=1)
        cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d1729")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#7f97ba")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7.5),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#d7e2f5")),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#eaf1fb")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#0a1320"), colors.HexColor("#0d1829")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#16243c")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#1c2c48")),
        ]
        if tot_idx is not None:
            cmds += [
                ("BACKGROUND", (0, tot_idx), (-1, tot_idx), colors.HexColor("#132544")),
                ("TEXTCOLOR", (0, tot_idx), (-1, tot_idx), colors.HexColor("#eaf1fb")),
                ("FONTNAME", (0, tot_idx), (-1, tot_idx), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, tot_idx), (0, tot_idx), colors.HexColor("#9fc2ff")),
                ("LINEABOVE", (0, tot_idx), (-1, tot_idx), 1, colors.HexColor("#294066")),
            ]
        t.setStyle(TableStyle(cmds))
        return t

    for side, label in ((rep["away"], g["away_name"]), (rep["home"], g["home_name"])):
        story.append(Paragraph("%s &mdash; Batting" % _e(label), h2))
        story.append(box(side["batting"], BAT_COLS, "bat"))
        story.append(Paragraph("%s &mdash; Pitching" % _e(label), h2))
        story.append(box(side["pitching"], PIT_COLS, "pit"))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Generated by Diamond Scorer &mdash; batted-ball spray is "
                           "derived from fielder, trajectory and hit value.", foot))
    doc.build(story, onFirstPage=_pdf_bg, onLaterPages=_pdf_bg)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Statistics export (web HTML + PDF) -- mirrors the in-app Statistics view
# ---------------------------------------------------------------------------
_SBAT = {
    "basic": [("G","G",0),("PA","PA",0),("AB","AB",0),("R","R",0),("H","H",0),
        ("HR","HR",0),("RBI","RBI",0),("BB","BB",0),("SO","SO",0),("AVG","AVG",1),
        ("OBP","OBP",1),("SLG","SLG",1),("OPS","OPS",1)],
    "advanced": [("2B","2B",0),("3B","3B",0),("SB","SB",0),("CS","CS",0),("TB","TB",0),
        ("ISO","ISO",1),("BB%","BB%",1),("K%","K%",1)],
    "detailed": [("IBB","IBB",0),("HBP","HBP",0),("SF","SF",0),("SAC","SAC",0),
        ("BABIP","BABIP",1),("SB%","SB%",1)],
}
_SPIT = {
    "basic": [("G","G",0),("W","W",0),("L","L",0),("SV","SV",0),("IP","IP",0),("H","H",0),
        ("R","R",0),("ER","ER",0),("BB","BB",0),("SO","SO",0),("ERA","ERA",2),("WHIP","WHIP",2),
        ("BAA","BAA",1)],
    "advanced": [("HR","HR",0),("HBP","HBP",0),("K9","K/9",2),("BB9","BB/9",2),
        ("KBB","K/BB",2),("RA9","RA/9",2)],
    "detailed": [("BF","BF",0),("Pit","Pit",0),("Str%","Str%",1),("Sw%","Sw%",1),
        ("Whiff%","Whiff%",1),("IBB","IBB",0)],
}
_SFLD = {
    "basic": [("G","G",0),("PO","PO",0),("A","A",0),("E","E",0),("DP","DP",0),("FPCT","FPCT",1)],
    "advanced": [("TC","TC",0),("cCS","CS",0),("cSB","SB",0),("CS%","CS%",1),("cPB","PB",0)],
    "detailed": [("cPO","PO(C)",0),("pWP","WP",0),("pPO","PO(P)",0)],
}
_SSTAND = [("GP","GP",0),("W","W",0),("L","L",0),("T","T",0),("PCT","PCT",1),
    ("RF","RF",0),("RA","RA",0),("DIFF","DIFF",0),("STRK","STRK",0),("L10","L10",0)]


def _stat_cols(tab, level):
    src = {"batting": _SBAT, "pitching": _SPIT, "fielding": _SFLD}.get(tab, _SBAT)
    cols = list(src["basic"])
    if level != "basic":
        cols += src["advanced"]
    if level == "detailed":
        cols += src["detailed"]
    return cols


def _sfmt(v, rate):
    if v is None or v == "":
        return ""
    if rate == 1:
        try:
            s = "%.3f" % float(v)
        except (TypeError, ValueError):
            return str(v)
        return s.lstrip("0") if s[:1] != "-" else "-" + s[1:].lstrip("0")
    if rate == 2:
        try:
            return "%.2f" % float(v)
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def _stats_meta(season_id, team_id):
    """Human-readable scope header: (league name, season name, team name)."""
    from .db import get_conn
    league = season = team = None
    try:
        c = get_conn()
        if season_id:
            row = c.execute(
                "SELECT s.name AS sname, l.name AS lname "
                "FROM seasons s JOIN leagues l ON l.id = s.league_id "
                "WHERE s.id = ?", (season_id,)).fetchone()
            if row:
                season = row["sname"]
                league = row["lname"]
        if team_id:
            row = c.execute("SELECT name FROM teams WHERE id = ?", (team_id,)).fetchone()
            team = row["name"] if row else None
    except Exception:
        pass
    return league, season, team


def _stats_title(tab):
    return {"batting": "Batting", "pitching": "Pitching",
            "fielding": "Fielding", "standings": "Standings"}.get(tab, "Statistics")


_STATS_CSS = """
.rep-header{text-align:center;margin:0 0 30px;padding:6px 0 24px;position:relative}
.rep-header::after{content:"";position:absolute;left:50%;bottom:0;transform:translateX(-50%);
  width:120px;height:3px;border-radius:3px;background:linear-gradient(90deg,#4d94ff,#35d07f)}
.rep-header .rh-line{font-size:15px;color:#9fb4d4;line-height:1.6}
.rep-header .rh-line.lead{font-size:22px;font-weight:800;color:#eaf1fb;letter-spacing:.2px;margin-bottom:2px}
.rep-header .rh-title{margin-top:20px;font-size:28px;font-weight:800;letter-spacing:4px;
  text-transform:uppercase;background:linear-gradient(90deg,#4d94ff,#7fb5ff);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.rep-header .rh-scope{margin-top:12px;font-size:11px;color:#7f97ba;text-transform:uppercase;letter-spacing:1.4px}
.sect{margin:0 0 34px}
.sect .sect-title{text-align:center;font-size:18px;font-weight:800;letter-spacing:3px;
  text-transform:uppercase;color:#7fb5ff;margin:0 0 16px}
.card2{background:linear-gradient(180deg,#101d33,#0c1727);border:1px solid #1c2c48;
  border-radius:16px;padding:20px 22px;box-shadow:0 14px 40px -24px rgba(0,0,0,.9)}
.group-head{text-align:center;font-size:22px;font-weight:800;letter-spacing:5px;
  text-transform:uppercase;color:#eaf1fb;margin:6px 0 22px;padding-bottom:14px;
  position:relative}
.group-head::after{content:"";position:absolute;left:50%;bottom:0;transform:translateX(-50%);
  width:90px;height:3px;border-radius:3px;background:linear-gradient(90deg,#4d94ff,#35d07f)}
.lead-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:0 0 38px}
.lead-card{background:linear-gradient(180deg,#101d33,#0c1727);border:1px solid #1c2c48;
  border-radius:16px;padding:16px 18px;box-shadow:0 14px 40px -26px rgba(0,0,0,.9);min-width:0;
  transition:border-color .2s}
.lead-card .lc-title{text-align:center;font-size:12px;font-weight:800;letter-spacing:1.4px;
  text-transform:uppercase;color:#7fb5ff;margin:0 0 12px;padding-bottom:10px;
  border-bottom:1px solid #16243c}
@media (max-width:900px){.lead-grid{grid-template-columns:repeat(2,1fr)}}
@media (max-width:620px){.lead-grid{grid-template-columns:1fr}}
@media print{.lead-grid{grid-template-columns:repeat(3,1fr)}}
"""


def _scope_line(team, level, game_count):
    bits = [team or "All Teams"]
    if level:
        bits.append("%s view" % level.capitalize())
    bits.append("%d game%s" % (game_count, "" if game_count == 1 else "s"))
    return "  \u00b7  ".join(bits)


def _stats_header_html(league, season, team, level, game_count, report_name=None):
    lines = []
    if league:
        lines.append('<div class="rh-line lead">%s</div>' % _e(league))
    if season:
        lines.append('<div class="rh-line">%s</div>' % _e(season))
    lines.append('<div class="rh-line">%s</div>' % _e(team or "All Teams"))
    rn = ('<div class="rh-title">%s</div>' % _e((report_name or "").upper())) if report_name else ""
    scope = '<div class="rh-scope">%s</div>' % _e(_scope_line(team, level, game_count))
    return '<div class="rep-header">%s%s%s</div>' % ("".join(lines), rn, scope)


def _stats_table_html(data, tab, level):
    cols = _stat_cols(tab, level)
    head = ('<th class="l">Player</th><th class="l">Tm</th>'
            + "".join('<th>%s</th>' % _e(l) for _, l, _ in cols))
    body = []
    for row in data.get(tab, []):
        tds = "".join('<td>%s</td>' % _e(_sfmt(row.get(k), rt)) for k, _, rt in cols)
        body.append('<tr><td class="l">%s</td><td class="l">%s</td>%s</tr>'
                    % (_e(row.get("name")), _e(row.get("team") or ""), tds))
    if not body:
        return '<p class="nodata">No qualifying players in this scope yet.</p>'
    return ('<table class="box"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (head, "".join(body)))


def _standings_table_html(data):
    cols = _SSTAND
    head = ('<th class="l">#</th><th class="l">Team</th>'
            + "".join('<th>%s</th>' % _e(l) for _, l, _ in cols))
    body = []
    for i, row in enumerate(data.get("standings", []), 1):
        tds = "".join('<td>%s</td>' % _e(_sfmt(row.get(k), rt)) for k, _, rt in cols)
        body.append('<tr><td class="l">%d</td><td class="l">%s</td>%s</tr>'
                    % (i, _e(row.get("team")), tds))
    if not body:
        return '<p class="nodata">No completed games yet.</p>'
    return ('<table class="box"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (head, "".join(body)))


def _stats_doc_html(title, header, body):
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>%s \u2014 Diamond Scorer</title><style>%s%s</style></head>"
        "<body><div class='wrap'>%s%s"
        "<div class='foot'>Generated by Diamond Scorer \u2014 statistics are derived live "
        "from the play-by-play log.</div></div></body></html>"
        % (_e(title), _CSS, _STATS_CSS, header, body)
    )


# Leaders mode ------------------------------------------------------------
_LEAD_TITLE = {"batting": "Batting Leaders", "pitching": "Pitching Leaders"}
# (label, key, direction, min_kind, fmt)
_LEAD_BAT = [
    ("AVG de Bateo", "AVG", "desc", "pa", "r3"),
    ("Sencillos", "1B", "desc", None, "int"),
    ("Dobles", "2B", "desc", None, "int"),
    ("Triples", "3B", "desc", None, "int"),
    ("Home Runs", "HR", "desc", None, "int"),
    ("Bases Robadas", "SB", "desc", None, "int"),
    ("Carreras Anotadas", "R", "desc", None, "int"),
    ("Carreras Impulsadas", "RBI", "desc", None, "int"),
    ("OBP", "OBP", "desc", "pa", "r3"),
    ("SLG", "SLG", "desc", "pa", "r3"),
    ("OPS", "OPS", "desc", "pa", "r3"),
]
_LEAD_PIT = [
    ("Efectividad", "ERA", "asc", "ip", "r2"),
    ("Innings Lanzados", "IPnum", "desc", None, "ip"),
    ("Ponches", "SO", "desc", None, "int"),
    ("Porcentaje Juegos Ganados", "WLPCT", "desc", None, "r3"),
    ("Juegos Ganados", "W", "desc", None, "int"),
    ("Juegos Perdidos", "L", "desc", None, "int"),
    ("Juegos Salvados", "SV", "desc", None, "int"),
    ("WHIP", "WHIP", "asc", "ip", "r2"),
    ("Avg Bateo en Contra", "BAA", "asc", "ip", "r3"),
]


def _lead_val(row, key):
    if key == "1B":
        return (row.get("H", 0) - row.get("2B", 0)
                - row.get("3B", 0) - row.get("HR", 0))
    if key == "WLPCT":
        w, l = row.get("W", 0), row.get("L", 0)
        return (w / (w + l)) if (w + l) else 0.0
    if key == "IPnum":
        return row.get("Outs", 0) / 3.0
    return row.get(key, 0) or 0


def _lead_qualifies(row, team_games, min_pa, min_ip, kind):
    if not kind:
        return True
    tg = team_games.get(row.get("team_id"), 0) or 0
    if kind == "pa":
        return row.get("PA", 0) >= min_pa * tg
    if kind == "ip":
        return (row.get("Outs", 0) / 3.0) >= min_ip * tg
    return True


def _lead_fmt(row, key, fmt):
    v = _lead_val(row, key)
    if fmt == "ip":
        return str(row.get("IP", ""))
    if fmt == "r3":
        s = "%.3f" % float(v)
        return s.lstrip("0") if s[:1] != "-" else "-" + s[1:].lstrip("0")
    if fmt == "r2":
        return "%.2f" % float(v)
    return str(int(v))


def _leaders_rows(data, pool, spec, team_games, min_pa, min_ip):
    """Return top-5 (name, team, display) for one leader category."""
    label, key, direction, kind, fmt = spec
    cand = [r for r in pool if _lead_qualifies(r, team_games, min_pa, min_ip, kind)]
    cand.sort(key=lambda r: _lead_val(r, key), reverse=(direction == "desc"))
    out = []
    for r in cand[:5]:
        out.append((r.get("name", ""), r.get("team", "") or "",
                    _lead_fmt(r, key, fmt)))
    return out


def _lead_card_html(spec, rows):
    label = spec[0]
    if not rows:
        inner = '<p class="nodata">No qualifying players.</p>'
    else:
        body = "".join(
            '<tr><td class="l">%d</td><td class="l">%s</td>'
            '<td class="l">%s</td><td>%s</td></tr>'
            % (i, _e(nm), _e(tm), _e(val))
            for i, (nm, tm, val) in enumerate(rows, 1))
        inner = ('<table class="box"><thead><tr><th class="l">#</th>'
                 '<th class="l">Player</th><th class="l">Tm</th>'
                 '<th>Value</th></tr></thead><tbody>%s</tbody></table>' % body)
    return ('<div class="lead-card"><div class="lc-title">%s</div>%s</div>'
            % (_e(label.upper()), inner))


def _leaders_sections_html(data, tab, team_games, min_pa, min_ip):
    parts = []
    if tab in ("all", "batting"):
        cards = "".join(_lead_card_html(
            spec, _leaders_rows(data, data.get("batting", []), spec,
                                team_games, min_pa, min_ip))
            for spec in _LEAD_BAT)
        parts.append('<div class="group-head">Bateadores</div>'
                     '<div class="lead-grid">%s</div>' % cards)
    if tab in ("all", "pitching"):
        cards = "".join(_lead_card_html(
            spec, _leaders_rows(data, data.get("pitching", []), spec,
                                team_games, min_pa, min_ip))
            for spec in _LEAD_PIT)
        parts.append('<div class="group-head">Lanzadores</div>'
                     '<div class="lead-grid">%s</div>' % cards)
    return "".join(parts)


def _mode_rows(data, mode, sub):
    if mode == "team":
        return list(data.get("team_" + sub, []))
    return list(data.get(sub, []))


def _apply_sort(rows, sort_key, sort_dir):
    if not sort_key:
        return rows
    def kf(r):
        if sort_key == "IP":
            return r.get("Outs", 0)
        if sort_key == "name":
            return (r.get("name") or "")
        v = r.get(sort_key)
        return 0 if v is None else v
    try:
        return sorted(rows, key=kf, reverse=(sort_dir == "desc"))
    except TypeError:
        return sorted(rows, key=lambda r: str(kf(r)),
                      reverse=(sort_dir == "desc"))


def _stats_table_html2(rows, tab, level, first_label="Player"):
    cols = _stat_cols(tab, level)
    head = ('<th class="l">%s</th><th class="l">Tm</th>' % _e(first_label)
            + "".join('<th>%s</th>' % _e(l) for _, l, _ in cols))
    body = []
    for row in rows:
        tds = "".join('<td>%s</td>' % _e(_sfmt(row.get(k), rt)) for k, _, rt in cols)
        body.append('<tr><td class="l">%s</td><td class="l">%s</td>%s</tr>'
                    % (_e(row.get("name")), _e(row.get("team") or ""), tds))
    if not body:
        return '<p class="nodata">No qualifying rows in this scope yet.</p>'
    return ('<table class="box"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
            % (head, "".join(body)))


def build_stats_html(season_id=None, team_id=None, tab="batting", level="basic",
                     mode="player", sort_key=None, sort_dir=None,
                     min_pa=2.1, min_ip=1.0) -> str:
    data = stats.stats(season_id=season_id, team_id=team_id)
    league, season, team = _stats_meta(season_id, team_id)
    gc = data["game_count"]
    if mode == "leaders":
        rn = None if tab == "all" else _LEAD_TITLE.get(tab)
        header = _stats_header_html(league, season, team, level, gc, report_name=rn)
        body = _leaders_sections_html(data, tab, data.get("team_games", {}),
                                      min_pa, min_ip)
        return _stats_doc_html("Player Leaders", header, body)
    first_label = "Team" if mode == "team" else "Player"
    all_title = ("All Collective Statistics" if mode == "team"
                 else "All Individual Statistics")
    if tab == "all":
        header = _stats_header_html(league, season, team, level, gc, report_name=None)
        sects = []
        for sub, label in (("batting", "Batting"), ("pitching", "Pitching"),
                           ("fielding", "Fielding")):
            rows = _mode_rows(data, mode, sub)
            sects.append('<div class="sect"><div class="sect-title">%s</div>'
                         '<div class="card2">%s</div></div>'
                         % (label.upper(),
                            _stats_table_html2(rows, sub, level, first_label)))
        return _stats_doc_html(all_title, header, "".join(sects))
    report_name = _stats_title(tab)
    header = _stats_header_html(league, season, team, level, gc, report_name=report_name)
    if tab == "standings":
        body = _standings_table_html(data)
    else:
        rows = _apply_sort(_mode_rows(data, mode, tab), sort_key, sort_dir)
        body = _stats_table_html2(rows, tab, level, first_label)
    return _stats_doc_html(report_name + " Statistics", header, body)


def _OLD_build_stats_html(season_id=None, team_id=None, tab="batting", level="basic") -> str:
    data = stats.stats(season_id=season_id, team_id=team_id)
    league, season, team = _stats_meta(season_id, team_id)
    gc = data["game_count"]
    if tab == "all":
        header = _stats_header_html(league, season, team, level, gc, report_name=None)
        sects = []
        for sub_tab, label in (("batting", "Batting"), ("pitching", "Pitching"),
                               ("fielding", "Fielding")):
            sects.append('<div class="sect"><div class="sect-title">%s</div>'
                         '<div class="card2">%s</div></div>'
                         % (label.upper(), _stats_table_html(data, sub_tab, level)))
        return _stats_doc_html("All Individual Statistics", header, "".join(sects))
    report_name = _stats_title(tab)
    header = _stats_header_html(league, season, team, level, gc, report_name=report_name)
    body = (_standings_table_html(data) if tab == "standings"
            else _stats_table_html(data, tab, level))
    return _stats_doc_html(report_name + " Statistics", header, body)


def build_stats_pdf(season_id=None, team_id=None, tab="batting", level="basic",
                    mode="player", sort_key=None, sort_dir=None,
                    min_pa=2.1, min_ip=1.0) -> bytes:
    import io
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable)

    data = stats.stats(season_id=season_id, team_id=team_id)
    league, season, team = _stats_meta(season_id, team_id)
    gc = data["game_count"]
    ss = getSampleStyleSheet()
    lead = ParagraphStyle("lead", parent=ss["Normal"], fontSize=17, leading=21,
                          alignment=TA_CENTER, fontName="Helvetica-Bold",
                          textColor=colors.HexColor("#0b1f3a"))
    meta = ParagraphStyle("meta", parent=ss["Normal"], fontSize=12, leading=16,
                          alignment=TA_CENTER, textColor=colors.HexColor("#44586f"))
    rtitle = ParagraphStyle("rtitle", parent=ss["Title"], fontSize=22, spaceBefore=12,
                            alignment=TA_CENTER, textColor=colors.HexColor("#1c4f8f"))
    scope = ParagraphStyle("scope", parent=ss["Normal"], fontSize=9, alignment=TA_CENTER,
                           textColor=colors.HexColor("#7a8aa0"), spaceBefore=6, spaceAfter=4)
    sect = ParagraphStyle("sect", parent=ss["Title"], fontSize=16, alignment=TA_CENTER,
                          textColor=colors.HexColor("#1c4f8f"), spaceBefore=10, spaceAfter=6)
    group = ParagraphStyle("group", parent=ss["Title"], fontSize=20, alignment=TA_CENTER,
                           textColor=colors.HexColor("#0b1f3a"), spaceBefore=6, spaceAfter=10)
    ctitle = ParagraphStyle("ctitle", parent=ss["Normal"], fontSize=9, alignment=TA_CENTER,
                            fontName="Helvetica-Bold", spaceAfter=3,
                            textColor=colors.HexColor("#1c4f8f"))

    def _table(tdata, lead_cols, colWidths=None):
        t = Table(tdata, repeatRows=1, colWidths=colWidths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1c4f8f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (lead_cols, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (lead_cols - 1, -1), "LEFT"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#0b1f3a")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3fb")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#1c4f8f")),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#dce4f0")),
        ]))
        return t

    def _player_table(sub_tab):
        cols = _stat_cols(sub_tab, level)
        first = "Team" if mode == "team" else "Player"
        header = [first, "Tm"] + [l for _, l, _ in cols]
        rows = _mode_rows(data, mode, sub_tab)
        if sub_tab == tab:
            rows = _apply_sort(rows, sort_key, sort_dir)
        if not rows:
            return Paragraph("No qualifying rows in this scope yet.", meta)
        tdata = [header]
        for row in rows:
            tdata.append([str(row.get("name", "")), str(row.get("team", "") or "")]
                         + [_sfmt(row.get(k), rt) for k, _, rt in cols])
        return _table(tdata, 2)

    def _leader_table(spec):
        pool = (data.get("batting", []) if spec in _LEAD_BAT
                else data.get("pitching", []))
        rows = _leaders_rows(data, pool, spec, data.get("team_games", {}),
                             min_pa, min_ip)
        if not rows:
            return Paragraph("No qualifying players.", meta)
        tdata = [["#", "Player", "Tm", "Value"]]
        for i, (nm, tm, val) in enumerate(rows, 1):
            tdata.append([str(i), str(nm), str(tm), str(val)])
        return _table(tdata, 3)

    def _leader_cell(spec):
        """A mini leader card: category title + its top-5 table, for the grid."""
        pool = (data.get("batting", []) if spec in _LEAD_BAT
                else data.get("pitching", []))
        rows = _leaders_rows(data, pool, spec, data.get("team_games", {}),
                             min_pa, min_ip)
        title = Paragraph(_e(spec[0].upper()), ctitle)
        if not rows:
            return [title, Paragraph("No qualifying players.", meta)]
        tdata = [["#", "Player", "Tm", "Value"]]
        for i, (nm, tm, val) in enumerate(rows, 1):
            tdata.append([str(i), str(nm), str(tm), str(val)])
        return [title, _table(tdata, 3, colWidths=[13, 150, 34, 40])]

    def _leader_grid(specs):
        """Arrange leader cards up to 3 per row as an outer table."""
        cells = [_leader_cell(s) for s in specs]
        grid = []
        for i in range(0, len(cells), 3):
            chunk = cells[i:i + 3]
            while len(chunk) < 3:
                chunk.append("")
            grid.append(chunk)
        col_w = doc.width / 3.0
        gt = Table(grid, colWidths=[col_w] * 3)
        gt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        return gt

    def _standings_table():
        cols = _SSTAND
        header = ["#", "Team"] + [l for _, l, _ in cols]
        rows = data.get("standings", [])
        if not rows:
            return Paragraph("No completed games yet.", meta)
        tdata = [header]
        for i, row in enumerate(rows, 1):
            tdata.append([str(i), str(row.get("team", ""))]
                         + [_sfmt(row.get(k), rt) for k, _, rt in cols])
        return _table(tdata, 2)

    is_leaders = (mode == "leaders")
    is_all = (tab == "all")
    if is_leaders:
        doc_title = "Player Leaders"
    elif is_all:
        doc_title = ("All Collective Statistics" if mode == "team"
                     else "All Individual Statistics")
    else:
        doc_title = _stats_title(tab) + " Statistics"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm,
                            rightMargin=12 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=doc_title)
    story = []
    if league:
        story.append(Paragraph(_e(league), lead))
    if season:
        story.append(Paragraph(_e(season), meta))
    story.append(Paragraph(_e(team or "All Teams"), meta))
    if is_leaders and not is_all:
        story.append(Paragraph(_e(_LEAD_TITLE.get(tab, "Leaders").upper()), rtitle))
    elif not is_leaders and not is_all:
        story.append(Paragraph(_e(_stats_title(tab).upper()), rtitle))
    story.append(Paragraph(_e(_scope_line(team, level, gc)), scope))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#c3cfe0"),
                            spaceBefore=2, spaceAfter=12))
    if is_leaders:
        if tab in ("all", "batting"):
            story.append(Paragraph("Bateadores", group))
            story.append(_leader_grid(_LEAD_BAT))
            story.append(Spacer(1, 8))
        if tab in ("all", "pitching"):
            story.append(Paragraph("Lanzadores", group))
            story.append(_leader_grid(_LEAD_PIT))
    elif is_all:
        for sub_tab, label in (("batting", "Batting"), ("pitching", "Pitching"),
                               ("fielding", "Fielding")):
            story.append(Paragraph(label.upper(), sect))
            story.append(_player_table(sub_tab))
            story.append(Spacer(1, 12))
    elif tab == "standings":
        story.append(_standings_table())
    else:
        story.append(_player_table(tab))
    doc.build(story)
    return buf.getvalue()
