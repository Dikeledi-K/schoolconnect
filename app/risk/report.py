"""Risk evaluation report as a PDF (reportlab), built only from build_summary() counts."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.taxonomy import LANGUAGES

INK = colors.HexColor("#1f2a44")
MUTED = colors.HexColor("#52514e")
GRID = colors.HexColor("#d9d8d4")
HEADER_BG = colors.HexColor("#eef2f8")
FLAG_BG = colors.HexColor("#fde8e4")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], textColor=INK, fontSize=18, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=INK, fontSize=12.5, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("s", parent=base["BodyText"], fontSize=8, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["BodyText"], fontSize=8.5, leading=11),
    }


def _table(rows: list[list], widths: list[float], styles, flag_rows: list[int] | None = None) -> Table:
    cell = styles["cell"]
    data = [[Paragraph(str(v), cell) for v in row] for row in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in flag_rows or []:
        style.append(("BACKGROUND", (0, r), (-1, r), FLAG_BG))
    t.setStyle(TableStyle(style))
    return t


def _fairness_rows(section: dict, metric: str, fmt) -> tuple[list[list], list[int]]:
    rows, flagged = [["Group", "n", metric.replace("_", " ").capitalize(), "Result"]], []
    for dimension in ("by_language", "by_grade"):
        for g in section[dimension]:
            result = "FLAGGED" if g["flagged"] else ("too few to judge" if g["too_small"] else "ok")
            rows.append([g["group"], g["n"], fmt(g[metric]), result])
            if g["flagged"]:
                flagged.append(len(rows) - 1)
    return rows, flagged


def build_pdf(summary: dict, school_name: str) -> bytes:
    s = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="SchoolConnect AI risk evaluation", author=school_name)
    p = summary["period"]
    ai, inc, rep, fair, inj = (summary["ai_decisions"], summary["incidents"], summary["replies"],
                               summary["fairness"], summary["prompt_injection"])
    story = [
        Paragraph("SchoolConnect: AI risk evaluation", s["title"]),
        Paragraph(f"{school_name} · period {p['start']} to {p['end']} ({p['days']} days)", s["small"]),
        Spacer(1, 6),
    ]

    # ---- Summary
    flags = fair["flags"]
    headline = [
        f"<b>{inc['tickets']}</b> parent messages; <b>{inc['critical']}</b> critical, "
        f"<b>{inc['safety_flagged']}</b> flagged for learner safety.",
        f"<b>{inj['passed']} of {inj['checks']}</b> prompt-injection checks passed.",
        f"<b>{summary['human_overrides']['count']}</b> staff corrections of AI classifications; "
        f"<b>{rep['edited_before_approval']}</b> of {rep['approved']} approved replies were edited by staff.",
        f"<b>{len(flags)}</b> fairness gap(s) flagged." + (" " + "; ".join(flags) if flags else ""),
        f"<b>{summary['retention']['tickets_due_for_anonymising']}</b> resolved ticket(s) due for anonymising.",
    ]
    if inc["critical_still_new_after_1h"]:
        headline.insert(1, f"<font color='#b3261e'><b>{inc['critical_still_new_after_1h']} critical ticket(s) "
                           "still 'new' after more than 1 hour.</b></font>")
    story.append(Paragraph("Summary", s["h2"]))
    for line in headline:
        story.append(Paragraph("• " + line, s["body"]))

    # ---- AI decisions and safeguards
    story.append(Paragraph("AI decisions and safeguards", s["h2"]))
    rows = [["Measure", "Count"],
            ["Messages classified", ai["classifications"]],
            ["  …classified by an external AI", ai["classified_by_ai"]],
            ["  …AI failed, rules used instead", ai["ai_fallbacks_to_rules"]],
            ["Reply drafts", ai["reply_drafts"]],
            ["  …written by an external AI", ai["reply_drafts_by_ai"]],
            ["  …AI reply rejected by the grounding check", ai["ai_replies_rejected"]],
            ["Replies that were acknowledgement-only (welfare/safety)", rep["acknowledgement_only"]]]
    story.append(_table(rows, [130, 48], s))
    story.append(Spacer(1, 4))
    g = summary["guardrails_fired"] or {"none": 0}
    story.append(_table([["Guardrail", "Times fired"]] + [[k, v] for k, v in sorted(g.items())], [130, 48], s))
    story.append(Spacer(1, 4))
    pii = summary["pii_masked"] or {"none found": 0}
    story.append(_table([["Personal data type masked before AI", "Count"]] +
                        [[k.replace("_", " "), v] for k, v in sorted(pii.items())], [130, 48], s))

    # ---- Human overrides
    story.append(Paragraph("Human overrides (staff corrections)", s["h2"]))
    recent = summary["human_overrides"]["recent"]
    if recent:
        rows = [["When (UTC)", "Ticket", "By", "Change", "Guardrail"]]
        for o in recent:
            change = f"{o['before']['category']}/{o['before']['urgency']} → {o['after']['category']}/{o['after']['urgency']}"
            rows.append([o["when"].replace("T", " "), o["ticket_id"], o["by"], f"{change}<br/>{o['reason']}",
                         ", ".join(o["guardrails"]) or "-"])
        story.append(_table(rows, [30, 14, 28, 76, 30], s))
    else:
        story.append(Paragraph("No corrections in this period.", s["body"]))

    # ---- Fairness
    story.append(Paragraph("Fairness by language and grade", s["h2"]))
    th = fair["thresholds"]
    story.append(Paragraph(
        f"Flags: accuracy more than {th['accuracy_gap']:.0%} below overall; waiting {th['wait_ratio']}× the overall "
        f"median or longer; correction rate more than {th['override_gap']:.0%} above overall. Small groups are not judged.",
        s["small"]))
    c = fair["classifier"]
    story.append(Paragraph(f"Classifier accuracy on {c['messages']} labelled messages (overall "
                           f"{c['overall_accuracy']:.0%})", s["body"]))
    rows, flagged = _fairness_rows(c, "accuracy", lambda v: f"{v:.0%}")
    story.append(_table(rows, [70, 20, 45, 43], s, flagged))
    sv = fair["service"]
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Hours to resolution, {sv['resolved_tickets']} resolved tickets (overall median "
                           f"{sv['overall_median_hours']} h)", s["body"]))
    rows, flagged = _fairness_rows(sv, "median_hours", lambda v: f"{v} h")
    story.append(_table(rows, [70, 20, 45, 43], s, flagged))
    ov = fair["overrides"]
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Staff correction rate, {ov['classified_tickets']} AI-classified tickets (overall "
                           f"{ov['overall_override_rate']:.0%})", s["body"]))
    rows, flagged = _fairness_rows(ov, "override_rate", lambda v: f"{v:.0%}")
    story.append(_table(rows, [70, 20, 45, 43], s, flagged))

    # ---- Prompt injection
    story.append(Paragraph("Prompt-injection suite", s["h2"]))
    rows = [["Case", "Attack", "Layer", "Result"]]
    failed_rows = []
    for r in inj["results"]:
        rows.append([r["id"], r["attack"], r["layer"], ("PASS" if r["passed"] else "FAIL: ") +
                     ("" if r["passed"] else r["detail"])])
        if not r["passed"]:
            failed_rows.append(len(rows) - 1)
    story.append(_table(rows, [16, 86, 26, 50], s, failed_rows))

    # ---- Risk register
    story.append(Paragraph("Risk register", s["h2"]))
    rows = [["ID", "Risk", "L / I", "Mitigation", "Status"]]
    for r in summary["risk_register"]:
        rows.append([r["id"], r["risk"], f"{r['likelihood']} / {r['impact']}", r["mitigation"], r["status"]])
    story.append(_table(rows, [10, 52, 22, 74, 20], s))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "This report contains counts only; no names, contact details or message text. "
        f"Languages: {', '.join(v for k, v in LANGUAGES.items() if k != 'unknown')}. "
        "Generated by SchoolConnect (Week 6: AI risk and compliance layer).", s["small"]))
    doc.build(story)
    return buffer.getvalue()
