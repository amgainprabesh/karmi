"""Karmi — printable bilingual report and document exporter.

Generates clean, ink-friendly, print-ready HTML documents optimized for
field verification on construction sites across Nepal. Designed for physical
printout (A4 paper / browser Print-to-PDF) with:
- High contrast, ink-saving styles with `@media print` rules.
- Bilingual Nepali-English typography.
- Physical verification checkboxes for masons (डकर्मी) and homeowners.
- Official tripartite signature & sign-off blocks.
- Strict adherence to Karmi's honesty invariants (zero "violation" phrasing).
"""

from __future__ import annotations

import html
from typing import Any

from core import nepali
from core.schema import DiffReport, SceneGraph, ObservedState


def _esc(val: Any) -> str:
    if val is None:
        return ""
    return html.escape(str(val), quote=True)


def _dev(val: Any) -> str:
    if val is None:
        return ""
    return nepali.to_devanagari_digits(str(val))


def render_printable_report(
    report: DiffReport | dict[str, Any] | Any,
    scene: SceneGraph | dict[str, Any] | Any = None,
    observed: ObservedState | dict[str, Any] | Any = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Render a self-contained, print-optimized bilingual inspection document.

    Suitable for direct printing or saving as PDF via browser print dialogue.
    """
    meta = metadata or {}
    owner = meta.get("owner", "घरधनी / Property Owner")
    ward = meta.get("ward", "—")
    run_id = meta.get("run_id", meta.get("id", "KARMI-RUN-PRINT"))
    date_str = meta.get("date", meta.get("created_at", "—"))

    # Extract report attributes safely whether pydantic model or dict
    if isinstance(report, dict):
        deltas = report.get("deltas", [])
        verify_list = report.get("verify_list", [])
        summary = report.get("summary", {})
        rep_meta = report.get("meta", {})
    else:
        deltas = list(getattr(report, "deltas", None) or [])
        verify_list = list(getattr(report, "verify_list", None) or [])
        summary = getattr(report, "summary", None) or {}
        rep_meta = getattr(report, "meta", None) or {}

    municipal_info = rep_meta.get("municipal", {}) if isinstance(rep_meta, dict) else {}
    regulatory_info = rep_meta.get("regulatory", {}) if isinstance(rep_meta, dict) else {}

    profile_name = municipal_info.get("profile", "राष्ट्रिय आधारभूत (Basic By-laws)")
    reg_code = regulatory_info.get("standard", "NBC 206:2015")

    total_deltas = len(deltas)
    total_verify = len(verify_list)

    # Build verify rows
    verify_rows_html = []
    if not verify_list:
        verify_rows_html.append("""
        <tr>
            <td colspan="5" class="text-center text-muted py-3">
                कुनै स्थलगत जाँच सूची फेला परेन / No field verification items identified.
            </td>
        </tr>
        """)
    else:
        for idx, item in enumerate(verify_list, start=1):
            if isinstance(item, dict):
                item_en = item.get("item", "")
                item_np = item.get("item_np", "")
                why = item.get("why", "")
                how = item.get("how", "")
                severity = item.get("severity", "info")
            else:
                item_en = getattr(item, "item", "")
                item_np = getattr(item, "item_np", "")
                why = getattr(item, "why", "")
                how = getattr(item, "how", "")
                severity = getattr(getattr(item, "severity", None), "value", "info")

            sev_badge = "सामान्य / Low" if severity == "low" else ("मध्यम / Medium" if severity == "medium" else "उच्च प्राथमिकता / High")

            row_markup = f"""
            <tr class="verify-row">
                <td class="text-center">
                    <span class="print-checkbox">[ ]</span>
                </td>
                <td class="text-center">{idx} ({_dev(idx)})</td>
                <td>
                    <div class="fw-bold">{_esc(item_np) if item_np else _esc(item_en)}</div>
                    <div class="text-muted small">{_esc(item_en)}</div>
                </td>
                <td>
                    <div class="small"><strong>कारण (Why):</strong> {_esc(why)}</div>
                    <div class="small"><strong>विधि (How to check):</strong> {_esc(how)}</div>
                </td>
                <td>
                    <span class="badge badge-{_esc(severity)}">{sev_badge}</span>
                    <div class="sign-line mt-2">स्थलगत कैफियत: ________________</div>
                </td>
            </tr>
            """
            verify_rows_html.append(row_markup)

    # Build delta summary rows
    delta_rows_html = []
    for d in deltas[:15]:  # limit to top 15 in printable summary
        if isinstance(d, dict):
            elem = d.get("element", "")
            status = d.get("status", "")
            exp = d.get("expected", "—")
            obs = d.get("observed", "—")
            reason = d.get("reason_np") or d.get("reason", "")
        else:
            elem = getattr(d, "element", "")
            status = getattr(getattr(d, "status", None), "value", str(getattr(d, "status", "")))
            exp = getattr(d, "expected", "—")
            obs = getattr(d, "observed", "—")
            reason = getattr(d, "reason_np", None) or getattr(d, "reason", "")

        delta_rows_html.append(f"""
        <tr>
            <td><strong>{_esc(elem)}</strong></td>
            <td><code>{_esc(status)}</code></td>
            <td>{_esc(exp)}</td>
            <td>{_esc(obs)}</td>
            <td class="small">{_esc(reason)}</td>
        </tr>
        """)

    if not delta_rows_html:
        delta_rows_html.append("""
        <tr>
            <td colspan="5" class="text-center text-muted">कुनै भिन्नता दर्ता भएको छैन / No geometry differences recorded.</td>
        </tr>
        """)

    return f"""<!doctype html>
<html lang="ne">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>कर्मी (Karmi) — स्थलगत प्रमाणीकरण प्रतिवेदन / Field Verification Report</title>
<style>
/* CSS Reset & Base Print Styles */
*, *::before, *::after {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}
body {{
    font-family: 'Noto Sans Devanagari', 'Mangal', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color: #1a1a1a;
    background: #f8fafc;
    padding: 24px;
    font-size: 13px;
    line-height: 1.5;
}}
.container {{
    max-width: 960px;
    margin: 0 auto;
    background: #ffffff;
    padding: 36px 40px;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}}
.no-print {{
    margin-bottom: 24px;
    text-align: right;
}}
.btn-print {{
    background-color: #0284c7;
    color: #ffffff;
    border: none;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
    border-radius: 6px;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(2, 132, 199, 0.2);
    display: inline-flex;
    align-items: center;
    gap: 8px;
}}
.btn-print:hover {{
    background-color: #0369a1;
}}
/* Official Header */
.official-header {{
    border-bottom: 2px solid #0f172a;
    padding-bottom: 16px;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
}}
.header-brand h1 {{
    font-size: 22px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.5px;
}}
.header-brand .subtitle {{
    font-size: 14px;
    font-weight: 600;
    color: #475569;
    margin-top: 2px;
}}
.header-brand .legal-note {{
    font-size: 11px;
    color: #64748b;
    margin-top: 4px;
}}
.meta-box {{
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    background: #f8fafc;
    padding: 12px 16px;
    font-size: 12px;
    min-width: 260px;
}}
.meta-row {{
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
    border-bottom: 1px dashed #e2e8f0;
}}
.meta-row:last-child {{
    border-bottom: none;
}}
.meta-label {{
    font-weight: 600;
    color: #475569;
}}
.meta-val {{
    font-weight: 700;
    color: #0f172a;
}}
/* Summary Cards */
.summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 24px;
}}
.summary-card {{
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 12px;
    text-align: center;
    background: #f8fafc;
}}
.summary-card .number {{
    font-size: 20px;
    font-weight: 800;
    color: #0284c7;
}}
.summary-card .label {{
    font-size: 11px;
    font-weight: 600;
    color: #475569;
    margin-top: 4px;
}}
/* Tables */
h2 {{
    font-size: 16px;
    font-weight: 700;
    color: #0f172a;
    margin: 24px 0 12px 0;
    display: flex;
    align-items: center;
    gap: 8px;
    border-left: 4px solid #0284c7;
    padding-left: 10px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 24px;
    font-size: 12px;
}}
th, td {{
    border: 1px solid #cbd5e1;
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
}}
th {{
    background-color: #f1f5f9;
    font-weight: 700;
    color: #1e293b;
}}
.text-center {{
    text-align: center;
}}
.text-muted {{
    color: #64748b;
}}
.fw-bold {{
    font-weight: 700;
}}
.small {{
    font-size: 11px;
}}
.print-checkbox {{
    font-family: monospace;
    font-size: 16px;
    font-weight: bold;
    color: #0f172a;
}}
.badge {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
}}
.badge-low {{
    background: #e0f2fe;
    color: #0369a1;
}}
.badge-medium {{
    background: #fef3c7;
    color: #b45309;
}}
.badge-high {{
    background: #fee2e2;
    color: #b91c1c;
}}
.sign-line {{
    border-top: 1px dotted #94a3b8;
    margin-top: 6px;
    padding-top: 4px;
    color: #64748b;
    font-size: 10px;
}}
/* Sign-off Block */
.signoff-section {{
    margin-top: 36px;
    page-break-inside: avoid;
    border-top: 2px solid #0f172a;
    padding-top: 20px;
}}
.signoff-title {{
    font-size: 14px;
    font-weight: 700;
    margin-bottom: 16px;
    color: #0f172a;
}}
.signoff-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
}}
.signoff-box {{
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 16px;
    background: #fafafa;
    min-height: 120px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}}
.signoff-role {{
    font-weight: 700;
    font-size: 12px;
    color: #1e293b;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 6px;
    margin-bottom: 30px;
}}
.signoff-lines {{
    font-size: 11px;
    color: #475569;
}}
.signoff-lines div {{
    margin-top: 4px;
}}
/* Honesty Banner */
.honesty-banner {{
    margin-top: 24px;
    background-color: #f8fafc;
    border-left: 4px solid #64748b;
    padding: 12px 16px;
    font-size: 11px;
    color: #475569;
    line-height: 1.6;
    page-break-inside: avoid;
}}

/* Print Media Query */
@media print {{
    @page {{
        size: A4 portrait;
        margin: 12mm 10mm 12mm 10mm;
    }}
    body {{
        background: #ffffff !important;
        padding: 0 !important;
        font-size: 11px !important;
        color: #000000 !important;
    }}
    .container {{
        max-width: 100% !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }}
    .no-print {{
        display: none !important;
    }}
    th {{
        background-color: #f1f5f9 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}
    tr {{
        page-break-inside: avoid;
    }}
    .signoff-section {{
        page-break-inside: avoid;
    }}
}}
</style>
</head>
<body>

<div class="container">
    <div class="no-print">
        <button class="btn-print" onclick="window.print()">
            🖨️ प्रिन्ट गर्नुहोस् / Print or Save as PDF
        </button>
    </div>

    <header class="official-header">
        <div class="header-brand">
            <h1>कर्मी (Karmi) — स्थलगत प्रमाणीकरण प्रतिवेदन</h1>
            <div class="subtitle">Field Verification & As-Built Conformance Report</div>
            <div class="legal-note">
                मापदण्ड: {_esc(reg_code)} | स्थानीय प्रोफाइल: {_esc(profile_name)}
            </div>
        </div>
        <div class="meta-box">
            <div class="meta-row">
                <span class="meta-label">घरधनी (Owner):</span>
                <span class="meta-val">{_esc(owner)}</span>
            </div>
            <div class="meta-row">
                <span class="meta-label">स्थान / वडा (Ward):</span>
                <span class="meta-val">{_esc(ward)}</span>
            </div>
            <div class="meta-row">
                <span class="meta-label">रन आईडी (Run ID):</span>
                <span class="meta-val">{_esc(run_id)}</span>
            </div>
            <div class="meta-row">
                <span class="meta-label">मिति (Date):</span>
                <span class="meta-val">{_esc(date_str)}</span>
            </div>
        </div>
    </header>

    <section class="summary-grid">
        <div class="summary-card">
            <div class="number">{total_deltas} ({_dev(total_deltas)})</div>
            <div class="label">तुलना गरिएका तत्व (Elements Checked)</div>
        </div>
        <div class="summary-card">
            <div class="number">{total_verify} ({_dev(total_verify)})</div>
            <div class="label">जाँच गर्नुपर्ने विषय (Items to Verify)</div>
        </div>
        <div class="summary-card">
            <div class="number">{_esc(profile_name)}</div>
            <div class="label">नगरपालिका मापदण्ड (Municipal Bylaw)</div>
        </div>
        <div class="summary-card">
            <div class="number">{_esc(reg_code)}</div>
            <div class="label">भवन संहिता (Building Code)</div>
        </div>
    </section>

    <h2>जाँच गर्नुपर्ने विषयहरू (Items to verify on site)</h2>
    <p class="small text-muted mb-2">
        डकर्मी वा प्राविधिकसँग मिलेर भौतिक रूपमा नापजाँच गरी बाकसमा चिह्न (☐) लगाउनुहोस्:
    </p>
    <table>
        <thead>
            <tr>
                <th style="width: 50px;" class="text-center">जाँच (✓)</th>
                <th style="width: 60px;" class="text-center">क्र.सं. (S.N.)</th>
                <th style="width: 280px;">विवरण (Description)</th>
                <th>कारण तथा कसरी जाँच्ने (Reason & Measurement Method)</th>
                <th style="width: 170px;">प्राथमिकता तथा स्थलगत कैफियत (Action)</th>
            </tr>
        </thead>
        <tbody>
            {"".join(verify_rows_html)}
        </tbody>
    </table>

    <h2>नक्सा र निर्माण बीचका भिन्नताहरू (Geometry Differences Summary)</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 180px;">तत्व (Element)</th>
                <th style="width: 90px;">स्थिति (Status)</th>
                <th style="width: 120px;">नक्सा (Drawn)</th>
                <th style="width: 120px;">स्थलगत (Observed)</th>
                <th>कैफियत (Details & Notes)</th>
            </tr>
        </thead>
        <tbody>
            {"".join(delta_rows_html)}
        </tbody>
    </table>

    <section class="signoff-section">
        <div class="signoff-title">हस्ताक्षर तथा स्थलगत प्रमाणीकरण (Verification & Sign-off Block)</div>
        <div class="signoff-grid">
            <div class="signoff-box">
                <div class="signoff-role">१. डकर्मी / निर्माण व्यवसायी (Mason / Contractor)</div>
                <div class="signoff-lines">
                    <div>हस्ताक्षर (Signature): _________________</div>
                    <div>नाम (Name): ______________________</div>
                    <div>मिति (Date): ______________________</div>
                </div>
            </div>
            <div class="signoff-box">
                <div class="signoff-role">२. घरधनी (Homeowner / Representative)</div>
                <div class="signoff-lines">
                    <div>हस्ताक्षर (Signature): _________________</div>
                    <div>नाम (Name): ______________________</div>
                    <div>मिति (Date): ______________________</div>
                </div>
            </div>
            <div class="signoff-box">
                <div class="signoff-role">३. प्राविधिक / इन्जिनियर (Site Engineer / Supervisor)</div>
                <div class="signoff-lines">
                    <div>हस्ताक्षर (Signature): _________________</div>
                    <div>नाम / काउन्सिल नं.: ________________</div>
                    <div>मिति (Date): ______________________</div>
                </div>
            </div>
        </div>
    </section>

    <div class="honesty-banner">
        <strong>प्राविधिक स्पष्टोक्ति तथा इमानदारी (Technical Disclaimer):</strong><br>
        कर्मी (Karmi) ले उपलब्ध गराइएका स्थलगत तस्बिर र स्वीकृत नक्साको ज्यामितीय तुलना मात्र गर्छ।
        यो कुनै कानुनी फैसला वा नगरपालिकाको कारबाही पत्र होइन। निर्माणको संरचनात्मक सुरक्षा (structural stability)
        वा गुणस्तर प्राविधिक इन्जिनियरबाट मात्र प्रमाणित हुनुपर्छ।
        <br>
        <em>Karmi compares visible photo geometry against drawings. This is an advisory field verification checklist,
        not a legal finding or municipal citation.</em>
    </div>
</div>

</body>
</html>
"""
