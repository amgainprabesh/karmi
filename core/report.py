"""Karmi — report renderers, Nepali-first.

``render_html(report, scene, observed)``     -> ONE self-contained HTML string
``render_markdown(report, scene, observed)`` -> the same content as Markdown

The HTML is fully self-contained: inline CSS, no external assets, no
JavaScript — it must render correctly with zero network access. The font
stack prefers Devanagari-capable faces that ship with the platform
('Noto Sans Devanagari', 'Mangal', ...).

Both renderers are read by a Nepali homeowner: Nepali first, English after.
Both are safe against empty or missing data — a run that produced nothing
still renders a valid document that says so, and neither function ever
raises.
"""

from __future__ import annotations

import html
from typing import Any

from core import nepali
from core.schema import DiffReport

# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _sev_key(severity: Any) -> str:
    return str(getattr(severity, "value", severity) or "info").lower()


def _status_key(delta: Any) -> str:
    status = getattr(delta, "status", None)
    if status is None:
        return "unverifiable"
    return str(getattr(status, "value", status)).lower()


def _esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _md(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    text = text.strip()
    return text if text else "—"


def _dev(n: int) -> str:
    return nepali.to_devanagari_digits(str(n))


def _stats(report: Any, scene: Any, observed: Any) -> dict[str, Any]:
    deltas = list(getattr(report, "deltas", None) or [])
    verify = list(getattr(report, "verify_list", None) or [])
    limits = list(getattr(report, "limits", None) or [])
    matched = sum(1 for d in deltas if _status_key(d) == "matched")
    high = sum(1 for d in deltas if _sev_key(getattr(d, "severity", None)) == "high")
    missing = sum(1 for d in deltas if _status_key(d) == "missing")
    unexpected = sum(1 for d in deltas if _status_key(d) == "unexpected")
    return {
        "deltas": deltas,
        "verify": verify,
        "limits": limits,
        "total": len(deltas),
        "matched": matched,
        "high": high,
        "missing": missing,
        "unexpected": unexpected,
        "verify_count": len(verify),
        "scene_file": getattr(scene, "source_file", None) if scene is not None else None,
        "scene_kind": str(getattr(getattr(scene, "source_kind", None), "value", "")) if scene is not None else "",
        "walls": len(getattr(scene, "walls", None) or []) if scene is not None else 0,
        "openings": len(getattr(scene, "openings", None) or []) if scene is not None else 0,
        "rooms": len(getattr(scene, "rooms", None) or []) if scene is not None else 0,
        "dimensions": len(getattr(scene, "dimensions", None) or []) if scene is not None else 0,
        "scene_warnings": len(getattr(scene, "warnings", None) or []) if scene is not None else 0,
        "stage": getattr(observed, "stage", None) if observed is not None else None,
        "captures": len(getattr(observed, "captures", None) or []) if observed is not None else 0,
        "elements": len(getattr(observed, "elements", None) or []) if observed is not None else 0,
        "scale_refs": len(getattr(observed, "scale_refs", None) or []) if observed is not None else 0,
        "observed_warnings": len(getattr(observed, "warnings", None) or []) if observed is not None else 0,
        "ai": ((getattr(report, "meta", None) or {}).get("ai") or {}) if report is not None else {},
    }


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
_CSS = """
:root{--ink:#20242b;--muted:#6b7280;--line:#e3e0d8;--bg:#f7f5f1;--card:#ffffff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.6;font-size:15px;
  font-family:'Noto Sans Devanagari','Mangal','Kalimati','Nirmala UI',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:28px 18px 56px}
.kicker{color:var(--muted);font-size:12px;letter-spacing:.14em;text-transform:uppercase}
h1{font-size:25px;margin:4px 0 8px}
h1 .en{font-size:14px;color:var(--muted);font-weight:400}
.lead{margin:0 0 14px;color:#3d4451}
.runmeta{list-style:none;display:flex;flex-wrap:wrap;gap:8px 24px;margin:0;padding:12px 16px;
  background:var(--card);border:1px solid var(--line);border-radius:10px;font-size:14px}
h2{font-size:19px;margin:32px 0 10px}
h2 .en{font-size:13px;color:var(--muted);font-weight:400}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:720px}
th{background:#f1efe9;text-align:left;padding:9px 10px;font-size:13px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
td.num{width:34px;color:var(--muted)}
tr.sev-high td{background:#fdf1f1}
tr.sev-medium td{background:#fdf7ea}
tr.sev-low td{background:#f3f8ec}
tr.sev-info td{background:#f2f7fc}
tr.sev-high td:first-child{box-shadow:inset 3px 0 0 #c0392b}
tr.sev-medium td:first-child{box-shadow:inset 3px 0 0 #d68910}
tr.sev-low td:first-child{box-shadow:inset 3px 0 0 #7fa650}
tr.sev-info td:first-child{box-shadow:inset 3px 0 0 #4a89c8}
.badge{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;border:1px solid;white-space:nowrap}
.b-info{background:#eaf2fb;border-color:#bcd6ef;color:#1c5d99}
.b-low{background:#eef7e6;border-color:#cbe3b4;color:#3c6e1f}
.b-medium{background:#fdf3e0;border-color:#eed9a6;color:#8a5a12}
.b-high{background:#fdeaea;border-color:#f0b9b9;color:#a12b2b}
.muted{color:var(--muted)}
.small{font-size:12px}
.np{font-weight:600}
.verify ol{margin:0;padding-left:22px}
.verify li{margin-bottom:16px;padding-left:4px}
.item-np{font-weight:600}
.how{color:#2f5d3a}
.narration ul{margin:4px 0 8px;padding-left:22px}
.narration ul.np-list{font-weight:500}
.narration .en-label{color:var(--muted);font-size:13px;margin:6px 0 2px}
.limits{background:#fff8e6;border:1px solid #ecd9a0;border-radius:10px;padding:14px 18px;margin-top:30px}
.limits h2{margin:0 0 8px;font-size:17px}
.limits ul{margin:0;padding-left:20px}
.limits li{margin-bottom:6px}
.empty{padding:14px 16px;background:var(--card);border:1px dashed var(--line);border-radius:10px;color:var(--muted)}
footer{margin-top:36px;border-top:1px solid var(--line);padding-top:16px}
.grid{display:flex;flex-wrap:wrap;gap:14px}
.grid>div{flex:1 1 240px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px}
.grid h3{font-size:14px;margin:2px 0 6px}
.grid ul{list-style:none;margin:0;padding:0;font-size:13px;color:#3d4451}
.grid li{margin-bottom:3px}
.fine{color:var(--muted);font-size:12px;margin-top:16px}
@media print{
  @page{size:A4;margin:16mm 14mm}
  body{background:#fff;font-size:11.5px}
  .wrap{max-width:none;padding:0}
  .tablewrap{overflow:visible;border-radius:0}
  table{min-width:0;font-size:10.5px}
  tr{page-break-inside:avoid}
  h2{page-break-after:avoid}
  .verify li,.limits,.grid>div,.runmeta{page-break-inside:avoid}
  .limits{background:#fff8e6 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  tr.sev-high td,tr.sev-medium td,tr.sev-low td,tr.sev-info td{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .badge{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  a{color:inherit;text-decoration:none}
  .noprint{display:none}
  footer{margin-top:18px}
}
"""


def _badge_html(severity: Any) -> str:
    key = _sev_key(severity)
    return (
        f'<span class="badge b-{_esc(key)}">{_esc(nepali.severity_np(severity))} '
        f"({_esc(nepali.severity_en(severity))})</span>"
    )


def _render_html(report: Any, scene: Any, observed: Any) -> str:
    st = _stats(report, scene, observed)
    deltas = st["deltas"]
    verify = st["verify"]
    limits = st["limits"]

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="ne">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>कर्मी — तुलना प्रतिवेदन (Karmi comparison report)</title>")
    parts.append(f"<style>{_CSS}</style>")
    parts.append("</head>")
    parts.append("<body><div class=\"wrap\">")

    # ---- header ---------------------------------------------------------- #
    parts.append("<header>")
    parts.append('<div class="kicker">कर्मी · Karmi</div>')
    parts.append('<h1>तुलना प्रतिवेदन <span class="en">— approved drawing vs site</span></h1>')
    parts.append(
        '<p class="lead">स्वीकृत नक्सा र साइटका तस्बिरहरूबीचको स्वचालित तुलना। '
        "यो कानुनी प्रमाण होइन — तल जाँच गर्नुपर्ने बुँदाहरूको सूची छ।</p>"
    )
    parts.append('<ul class="runmeta">')
    parts.append(f'<li><b>नक्सा / drawing:</b> {_esc(st["scene_file"]) or "—"}</li>')
    parts.append(f'<li><b>तस्बिर / photos:</b> {_dev(st["captures"])}</li>')
    parts.append(
        f'<li><b>चरण / stage:</b> {_esc(nepali.stage_np(st["stage"]))} '
        f'({_esc(nepali.stage_en(st["stage"]))})</li>'
    )
    parts.append(
        f'<li><b>सारांश / summary:</b> जम्मा {_dev(st["total"])} · मिले {_dev(st["matched"])} · '
        f'जाँच {_dev(st["verify_count"])} · उच्च {_dev(st["high"])}</li>'
    )
    parts.append("</ul>")
    parts.append("</header>")

    # ---- narration ("at a glance") --------------------------------------- #
    narration_np = list(getattr(report, "narration_np", None) or [])
    narration_en = list(getattr(report, "narration_en", None) or [])
    if narration_np or narration_en:
        parts.append('<section class="narration">')
        parts.append('<h2>एक नजरमा <span class="en">(at a glance)</span></h2>')
        if narration_np:
            parts.append('<ul class="np-list">')
            for line in narration_np:
                parts.append(f"<li>{_esc(line)}</li>")
            parts.append("</ul>")
        if narration_en:
            parts.append('<div class="en-label">English:</div>')
            parts.append('<ul class="muted">')
            for line in narration_en:
                parts.append(f"<li>{_esc(line)}</li>")
            parts.append("</ul>")
        parts.append("</section>")

    # ---- delta table ------------------------------------------------------ #
    parts.append("<section>")
    parts.append(
        '<h2>भाग-दर-भाग तुलना <span class="en">(element-by-element comparison)</span></h2>'
    )
    if deltas:
        parts.append('<div class="tablewrap"><table>')
        parts.append(
            "<thead><tr>"
            "<th>#</th><th>भाग / element</th><th>स्थिति / status</th>"
            "<th>नक्सा / expected</th><th>साइट / observed</th>"
            "<th>विश्वास / confidence</th><th>कारण / reason</th>"
            "</tr></thead><tbody>"
        )
        for i, d in enumerate(deltas, 1):
            sev = _sev_key(getattr(d, "severity", None))
            status = _status_key(d)
            try:
                conf = float(getattr(d, "confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            weak = conf < 0.5
            conf_txt = f"{conf:.0%}" + (
                ' <span class="muted small">(कमजोर / weak)</span>' if weak else ""
            )
            element_np = getattr(d, "element_np", None) or getattr(d, "element", None)
            parts.append(f'<tr class="sev-{_esc(sev)}">')
            parts.append(f'<td class="num">{i}</td>')
            parts.append(
                f"<td><b>{_esc(element_np)}</b><br>"
                f'<span class="muted small">{_esc(getattr(d, "element", None))}</span></td>'
            )
            parts.append(
                f"<td>{_badge_html(getattr(d, 'severity', None))}<br>"
                f'<span class="muted small">{_esc(nepali.status_np(status))} '
                f"({_esc(nepali.status_en(status))})</span></td>"
            )
            parts.append(f"<td>{_esc(getattr(d, 'expected', None)) or '—'}</td>")
            parts.append(f"<td>{_esc(getattr(d, 'observed', None)) or '—'}</td>")
            parts.append(f"<td>{conf_txt}</td>")
            parts.append(
                f'<td><div class="np">{_esc(getattr(d, "reason_np", None)) or "—"}</div>'
                f'<div class="muted small">{_esc(getattr(d, "reason", None)) or "—"}</div></td>'
            )
            parts.append("</tr>")
        parts.append("</tbody></table></div>")
    else:
        parts.append(
            '<div class="empty">तुलना गर्न मिल्ने भाग भेटिएन — नक्सा वा साइट डेटा खाली छ। '
            "(No comparable elements — no data.)</div>"
        )
    parts.append("</section>")

    # ---- verify list ------------------------------------------------------ #
    parts.append("<section>")
    parts.append(
        '<h2>जाँच गर्नुपर्ने बुँदा <span class="en">(items to verify)</span></h2>'
    )
    if verify:
        parts.append('<div class="verify"><ol>')
        for v in verify:
            parts.append("<li>")
            parts.append(
                f'<div class="item-np">{_esc(getattr(v, "item_np", None) or getattr(v, "item", None))}</div>'
            )
            parts.append(f'<div class="muted">{_esc(getattr(v, "item", None))}</div>')
            if getattr(v, "why", None):
                parts.append(f'<div class="why">{_esc(v.why)}</div>')
            if getattr(v, "how", None):
                parts.append(f'<div class="how">➜ {_esc(v.how)}</div>')
            ref = getattr(v, "delta_ref", None)
            ref_txt = f' · <span class="muted small">ref: {_esc(ref)}</span>' if ref else ""
            parts.append(
                f'<div class="muted small">गम्भीरता / severity: '
                f"{_badge_html(getattr(v, 'severity', None))}{ref_txt}</div>"
            )
            parts.append("</li>")
        parts.append("</ol></div>")
    else:
        parts.append(
            '<div class="empty">यो रनमा जाँच गर्नुपर्ने बुँदा भेटिएन। '
            "(Nothing needs verification in this run.)</div>"
        )
    parts.append("</section>")

    # ---- limits ------------------------------------------------------------ #
    parts.append('<aside class="limits">')
    parts.append(
        '<h2>यो रनले यकिन गर्न नसकेका कुरा '
        '<span class="en">(limits — what this run could not determine)</span></h2>'
    )
    if limits:
        parts.append("<ul>")
        for item in limits:
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ul>")
    else:
        parts.append('<p class="muted">कुनै सूचना छैन (none).</p>')
    parts.append("</aside>")

    # ---- footer stats ------------------------------------------------------ #
    parts.append("<footer>")
    parts.append('<div class="grid">')
    parts.append(
        "<div><h3>नक्सा मोडेल / drawing model</h3><ul>"
        f'<li>स्रोत / source: {_esc(st["scene_kind"]) or "—"}</li>'
        f"<li>भित्ता / walls: {_dev(st['walls'])}</li>"
        f"<li>ढोका-झ्याल / openings: {_dev(st['openings'])}</li>"
        f"<li>कोठा / rooms: {_dev(st['rooms'])}</li>"
        f"<li>नाप / dimensions: {_dev(st['dimensions'])}</li>"
        f"<li>चेतावनी / warnings: {_dev(st['scene_warnings'])}</li>"
        "</ul></div>"
    )
    parts.append(
        "<div><h3>साइट मोडेल / site model</h3><ul>"
        f"<li>तस्बिर / photos: {_dev(st['captures'])}</li>"
        f"<li>भाग / elements: {_dev(st['elements'])}</li>"
        f"<li>स्केल सन्दर्भ / scale refs: {_dev(st['scale_refs'])}</li>"
        f"<li>चेतावनी / warnings: {_dev(st['observed_warnings'])}</li>"
        "</ul></div>"
    )
    ai = st["ai"] or {}
    if ai.get("used"):
        ai_txt = f"AI नरेशन: प्रयोग भयो ({_esc(ai.get('provider'))})"
    else:
        ai_txt = "AI नरेशन: टेम्प्लेट (AI प्रयोग भएन)"
    parts.append(
        "<div><h3>सारांश / summary</h3><ul>"
        f"<li>जम्मा / total: {_dev(st['total'])}</li>"
        f"<li>मिले / matched: {_dev(st['matched'])}</li>"
        f"<li>साइटमा भेटिएन / missing: {_dev(st['missing'])}</li>"
        f"<li>नक्सामा भेटिएन / unexpected: {_dev(st['unexpected'])}</li>"
        f"<li>जाँच / to verify: {_dev(st['verify_count'])}</li>"
        f"<li>{ai_txt}</li>"
        "</ul></div>"
    )
    parts.append("</div>")
    parts.append(
        '<p class="fine">कर्मी — स्वीकृत नक्सा र निर्मित वास्तविकताबीचको कम्पाइलर। '
        "(Karmi — a compiler between approved design and built reality.)</p>"
    )
    parts.append("</footer>")

    parts.append("</div></body></html>")
    return "".join(parts)


def _error_html(exc: BaseException) -> str:
    message = html.escape(f"{type(exc).__name__}: {exc}")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ne"><head><meta charset="utf-8">'
        "<title>कर्मी — प्रतिवेदन तयार हुन सकेन</title></head><body>"
        "<h1>कर्मी तुलना प्रतिवेदन</h1>"
        "<p>यो प्रतिवेदन रेन्डर गर्न सकिएन। (This report could not be rendered.)</p>"
        f"<pre>{message}</pre>"
        "</body></html>"
    )


def render_html(report: Any, scene: Any, observed: Any) -> str:
    """Render the report as ONE self-contained HTML string.

    Inline CSS, no external assets, no JavaScript — safe with zero network
    access. Never raises: on unexpected input a minimal valid document is
    returned instead.
    """
    try:
        return _render_html(report, scene, observed)
    except Exception as exc:  # noqa: BLE001 — a renderer must never break a run
        return _error_html(exc)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def _render_markdown(report: Any, scene: Any, observed: Any) -> str:
    st = _stats(report, scene, observed)
    deltas = st["deltas"]
    verify = st["verify"]
    limits = st["limits"]

    lines: list[str] = []
    lines.append("# कर्मी तुलना प्रतिवेदन (Karmi comparison report)")
    lines.append("")
    lines.append(
        "> स्वीकृत नक्सा र साइटका तस्बिरहरूबीचको स्वचालित तुलना — यो कानुनी प्रमाण होइन, "
        "जाँच गर्नुपर्ने बुँदाहरूको सूची हो।  "
    )
    lines.append(
        "> An automated comparison of the approved drawing and the site photos — not "
        "legal evidence; a list of items to verify."
    )
    lines.append("")
    lines.append(f"- **नक्सा / drawing:** {_md(st['scene_file'])}")
    lines.append(f"- **तस्बिर / photos:** {_dev(st['captures'])}")
    lines.append(
        f"- **चरण / stage:** {_md(nepali.stage_np(st['stage']))} "
        f"({_md(nepali.stage_en(st['stage']))})"
    )
    lines.append(
        f"- **सारांश / summary:** जम्मा {_dev(st['total'])} · मिले {_dev(st['matched'])} · "
        f"जाँच {_dev(st['verify_count'])} · उच्च {_dev(st['high'])}"
    )
    lines.append("")

    narration_np = list(getattr(report, "narration_np", None) or [])
    narration_en = list(getattr(report, "narration_en", None) or [])
    if narration_np or narration_en:
        lines.append("## एक नजरमा (at a glance)")
        lines.append("")
        for line in narration_np:
            lines.append(f"- {_md(line)}")
        if narration_en:
            lines.append("")
            lines.append("_English:_")
            for line in narration_en:
                lines.append(f"- _{_md(line)}_")
        lines.append("")

    lines.append("## भाग-दर-भाग तुलना (element-by-element)")
    lines.append("")
    if deltas:
        lines.append("| # | भाग / element | स्थिति / status | नक्सा / expected | साइट / observed | विश्वास / conf. | कारण / reason |")
        lines.append("|---|---------------|-----------------|------------------|-----------------|-----------------|----------------|")
        for i, d in enumerate(deltas, 1):
            sev_np = nepali.severity_np(getattr(d, "severity", None))
            sev_en = nepali.severity_en(getattr(d, "severity", None))
            status = _status_key(d)
            try:
                conf = float(getattr(d, "confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            conf_txt = f"{conf:.0%}" + (" (कमजोर / weak)" if conf < 0.5 else "")
            element_np = getattr(d, "element_np", None) or getattr(d, "element", None)
            lines.append(
                f"| {i} | **{_md(element_np)}** · {_md(getattr(d, 'element', None))} "
                f"| **{_md(sev_np)}** ({_md(sev_en)}) · {_md(nepali.status_np(status))} "
                f"({_md(nepali.status_en(status))}) "
                f"| {_md(getattr(d, 'expected', None))} | {_md(getattr(d, 'observed', None))} "
                f"| {_md(conf_txt)} "
                f"| {_md(getattr(d, 'reason_np', None))} — {_md(getattr(d, 'reason', None))} |"
            )
    else:
        lines.append(
            "तुलना गर्न मिल्ने भाग भेटिएन — नक्सा वा साइट डेटा खाली छ। "
            "(No comparable elements — no data.)"
        )
    lines.append("")

    lines.append("## जाँच गर्नुपर्ने बुँदा (items to verify)")
    lines.append("")
    if verify:
        for i, v in enumerate(verify, 1):
            sev_np = nepali.severity_np(getattr(v, "severity", None))
            sev_en = nepali.severity_en(getattr(v, "severity", None))
            ref = getattr(v, "delta_ref", None)
            ref_txt = f" · ref: {_md(ref)}" if ref else ""
            item_np = getattr(v, "item_np", None) or getattr(v, "item", None)
            lines.append(f"{i}. **{_md(item_np)}**")
            lines.append(f"   {_md(getattr(v, 'item', None))}  ")
            if getattr(v, "why", None):
                lines.append(f"   **किन / why:** {_md(v.why)}  ")
            if getattr(v, "how", None):
                lines.append(f"   **कसरी / how:** {_md(v.how)}  ")
            lines.append(
                f"   **गम्भीरता / severity:** {_md(sev_np)} ({_md(sev_en)}){ref_txt}"
            )
            lines.append("")
    else:
        lines.append(
            "यो रनमा जाँच गर्नुपर्ने बुँदा भेटिएन। (Nothing needs verification in this run.)"
        )
    lines.append("")

    lines.append("## यो रनले यकिन गर्न नसकेका कुरा (limits — what this run could not determine)")
    lines.append("")
    if limits:
        for item in limits:
            lines.append(f"- {_md(item)}")
    else:
        lines.append("- कुनै सूचना छैन (none).")
    lines.append("")

    lines.append("## मोडेल तथ्याङ्क (model stats)")
    lines.append("")
    lines.append("| नक्सा मोडेल / drawing | साइट मोडेल / site | सारांश / summary |")
    lines.append("|---|---|---|")
    lines.append(
        f"| स्रोत: {_md(st['scene_kind'])} · भित्ता: {_dev(st['walls'])} · "
        f"ढोका-झ्याल: {_dev(st['openings'])} · कोठा: {_dev(st['rooms'])} · "
        f"नाप: {_dev(st['dimensions'])} "
        f"| तस्बिर: {_dev(st['captures'])} · भाग: {_dev(st['elements'])} · "
        f"स्केल सन्दर्भ: {_dev(st['scale_refs'])} "
        f"| जम्मा: {_dev(st['total'])} · मिले: {_dev(st['matched'])} · "
        f"जाँच: {_dev(st['verify_count'])} · उच्च: {_dev(st['high'])} |"
    )
    lines.append("")
    lines.append(
        "_कर्मी — स्वीकृत नक्सा र निर्मित वास्तविकताबीचको कम्पाइलर। "
        "(Karmi — a compiler between approved design and built reality.)_"
    )
    lines.append("")
    return "\n".join(lines)


def render_markdown(report: Any, scene: Any, observed: Any) -> str:
    """Render the report as Markdown. Never raises."""
    try:
        return _render_markdown(report, scene, observed)
    except Exception as exc:  # noqa: BLE001
        return (
            "# कर्मी तुलना प्रतिवेदन (Karmi comparison report)\n\n"
            "यो प्रतिवेदन रेन्डर गर्न सकिएन। (This report could not be rendered.)\n\n"
            f"`{type(exc).__name__}: {exc}`\n"
        )


__all__ = ["render_html", "render_markdown"]