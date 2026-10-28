"""Week 4: the weekly business report as a PDF (reportlab only; charts drawn with reportlab.graphics).

Built only from build_report_data() output: counts, times and template text. No personal data.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.analytics.insights import rate_text

INK = colors.HexColor("#3b2a1a")
MUTED = colors.HexColor("#7a6552")
GRID = colors.HexColor("#ead9c0")
HEADER_BG = colors.HexColor("#fff1dc")
BRAND = colors.HexColor("#c2410c")      # SchoolConnect orange (headings, "this week" bar)
BAR = colors.HexColor("#0f766e")        # teal bars, as on the dashboard
WIN_BG = colors.HexColor("#e7f6ec")
CONCERN_BG = colors.HexColor("#fdebe4")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], textColor=BRAND, fontSize=19, spaceAfter=2, alignment=0),
        "sub": ParagraphStyle("sub", parent=base["BodyText"], textColor=MUTED, fontSize=9.5, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], textColor=INK, fontSize=12.5, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["BodyText"], textColor=INK, fontSize=10, leading=14),
        "summary": ParagraphStyle("s", parent=base["BodyText"], textColor=INK, fontSize=10.5, leading=15,
                                  backColor=HEADER_BG, borderPadding=(7, 8, 7, 8), spaceBefore=4, spaceAfter=8),
        "small": ParagraphStyle("sm", parent=base["BodyText"], textColor=MUTED, fontSize=8, leading=10.5),
        "cell": ParagraphStyle("c", parent=base["BodyText"], textColor=INK, fontSize=9, leading=11.5),
    }


def _fmt(value, kind: str = "n") -> str:
    if value is None:
        return "–"
    if kind == "pct":
        return f"{value:.0%}"
    if kind == "h":
        return f"{value:.1f} h"
    return f"{value}"


def _change(cur, prev, kind: str = "n", lower_is_better: bool = False) -> str:
    """'+12 (+11%)' style change text, saying whether it got better.

    Plain words, no arrow symbols: the built-in PDF fonts cannot draw them."""
    if cur is None or prev is None:
        return "–"
    diff = cur - prev
    if abs(diff) < 1e-9:
        return "no change"
    better = diff < 0 if lower_is_better else diff > 0
    note = "better" if better else "worse"
    if kind == "pct":
        return f"{diff * 100:+.0f} points ({note})"
    if kind == "h":
        return f"{diff:+.1f} h ({note})"
    pct = f" ({diff / prev:+.0%})" if prev else ""
    return f"{diff:+d}{pct}"


def _table(rows: list[list], widths: list[float], s: dict, shade: dict[int, colors.Color] | None = None) -> Table:
    data = [[Paragraph(str(v), s["cell"]) for v in row] for row in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), HEADER_BG), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    for row, colour in (shade or {}).items():
        style.append(("BACKGROUND", (0, row), (-1, row), colour))
    t.setStyle(TableStyle(style))
    return t


def _bar_chart(title: str, labels: list[str], values: list[float | None], value_format: str) -> Drawing:
    """One series, bars from zero, the last bar (this week) in the brand colour, values on top."""
    width, height = 85 * mm, 58 * mm
    d = Drawing(width, height)
    d.add(String(0, height - 10, title, fontName="Helvetica-Bold", fontSize=9, fillColor=INK))
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 22, 22, width - 30, height - 42
    clean = [v if v is not None else 0 for v in values]
    chart.data = [clean]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.fillColor = MUTED
    chart.categoryAxis.strokeColor = GRID
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(clean + [1]) * 1.25
    chart.valueAxis.labels.fontSize = 6.5
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = GRID
    chart.valueAxis.gridStrokeColor = GRID
    chart.valueAxis.visibleGrid = True
    chart.bars.strokeColor = None
    chart.barSpacing = 2
    chart.bars[0].fillColor = BAR
    chart.bars[(0, len(clean) - 1)].fillColor = BRAND
    chart.barLabelFormat = value_format
    chart.barLabels.fontSize = 6.5
    chart.barLabels.fillColor = INK
    chart.barLabels.nudge = 6
    d.add(chart)
    return d


def build_pdf(data: dict, school_name: str) -> bytes:
    s = _styles()
    m, r = data["metrics"], data["metrics"]["response"]
    v, prev_r = m["volume"], r["previous"]
    start, end = date.fromisoformat(data["week_start"]), date.fromisoformat(data["week_end"])
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"SchoolConnect weekly report {data['week_start']} {data['scope_name']}",
                            author=school_name)
    story = [
        Paragraph("Weekly business report", s["title"]),
        Paragraph(f"<b>{data['scope_name']}</b> · {school_name} · week of {start.day} {start:%B} to "
                  f"{end.day} {end:%B %Y}", s["sub"]),
        Paragraph("Executive summary", s["h2"]),
        Paragraph(data["summary"], s["summary"]),
    ]
    if data["summary_method"] != "template":
        story.append(Paragraph(f"Summary worded by AI ({data['summary_method']}) from the figures below; "
                               "every number was checked against them.", s["small"]))

    # ---- Key figures
    on, on_prev = r["on_time"], prev_r["on_time"]
    rows = [["Measure", "This week", "Previous week", "Change"],
            ["Parent messages", _fmt(v["total"]), _fmt(v["previous"]), _change(v["total"], v["previous"])],
            ["Median first response (office hours)", _fmt(r["first_response"]["median"], "h"),
             _fmt(prev_r["first_response"]["median"], "h"),
             _change(r["first_response"]["median"], prev_r["first_response"]["median"], "h", lower_is_better=True)],
            ["Median time to resolve (office hours)", _fmt(r["resolution"]["median"], "h"),
             _fmt(prev_r["resolution"]["median"], "h"),
             _change(r["resolution"]["median"], prev_r["resolution"]["median"], "h", lower_is_better=True)],
            [f"Answered within the promised time (target {m['sla_target_rate']:.0%})",
             "–" if on["rate"] is None else rate_text(on["rate"], m["sla_target_rate"]),
             "–" if on_prev["rate"] is None else rate_text(on_prev["rate"], m["sla_target_rate"]),
             _change(on["rate"], on_prev["rate"], "pct")],
            ["Still open at the end of the week", _fmt(m["backlog"]["open"]), "", ""],
            ["  …past their promised response time", _fmt(m["backlog"]["overdue"]), "", ""],
            ["Escalated (nobody responded in time)", _fmt(m["escalations"]), "", ""],
            ["Parents who wrote more than once", _fmt(m["repeat_contacts"]), "", ""],
            ["Replies approved by staff", _fmt(m["replies"]["approved"]), "", ""]]
    story += [Paragraph("Key figures", s["h2"]), _table(rows, [78, 28, 28, 44], s)]

    # ---- Charts: 8-week trend (two separate charts, one measure each)
    trends = data["trends"]
    labels = [f"{date.fromisoformat(t['week_start']):%d %b}" for t in trends]
    charts = Table([[
        _bar_chart("Parent messages per week", labels, [t["total"] for t in trends], "%d"),
        _bar_chart("Median first response (office hours)", labels,
                   [t["median_first_response"] for t in trends], "%.1f"),
    ]], colWidths=[90 * mm, 90 * mm])
    story += [Paragraph("Last 8 weeks", s["h2"]), charts,
              Paragraph("Orange bar = this week. Office hours: Monday to Friday 07:30–15:30, excluding public holidays.",
                        s["small"])]

    # ---- Topics
    rows = [["Topic", "This week", "Previous week", "Change", "Median first response"]]
    for c in sorted(v["by_category"].values(), key=lambda c: c["n"], reverse=True):
        rows.append([c["name"], c["n"], c["previous"], f"{c['change']:+d}", _fmt(c["median_first_response"], "h")])
    story += [KeepTogether([Paragraph("Messages by topic", s["h2"]), _table(rows, [62, 24, 28, 24, 40], s)])]

    # ---- Wins and concerns
    wins = [i["text"] for i in data["insights"] if i["type"] == "win"] or ["None this week."]
    concerns = [i["text"] for i in data["insights"] if i["type"] == "concern"] or ["None this week."]
    rows = [["<b>Wins</b>", "<b>Concerns</b>"]]
    for i in range(max(len(wins), len(concerns))):
        rows.append([wins[i] if i < len(wins) else "", concerns[i] if i < len(concerns) else ""])
    t = _table(rows, [89, 89], s)
    t.setStyle(TableStyle([("BACKGROUND", (0, 1), (0, -1), WIN_BG), ("BACKGROUND", (1, 1), (1, -1), CONCERN_BG)]))
    story += [KeepTogether([Paragraph("Wins and concerns", s["h2"]), t])]
    notes = [i["text"] for i in data["insights"] if i["type"] == "info"][1:]
    for note in notes:
        story.append(Paragraph("• " + note, s["body"]))

    # ---- Outlook (Week 5 forecast)
    story.append(Paragraph("Next week", s["h2"]))
    look = data.get("outlook")
    if look:
        ns, ne = date.fromisoformat(look["week_start"]), date.fromisoformat(look["week_end"])
        lines = [f"About <b>{look['expected_messages']}</b> parent messages are expected next week "
                 f"({ns.day} {ns:%B} to {ne.day} {ne:%B}), based on the backtested Week 5 forecast."]
        for b in look["busy_roles"]:
            lines.append(f"{b['role']}: {b['status']} ({b['utilisation']:.0%} of available time; "
                         f"{b['busy_week_utilisation']:.0%} in a busy week).")
        for sp in look["spikes"][:3]:
            d = date.fromisoformat(sp["date"])
            lines.append(f"Expected spike on {d:%A} {d.day} {d:%B}: about {sp['expected']:.0f} messages, mostly "
                         f"{sp['topic'].lower()} ({sp['cause']}).")
        if not look["busy_roles"]:
            lines.append("No staff role is expected to be over capacity.")
        story += [Paragraph("• " + line, s["body"]) for line in lines]
    else:
        story.append(Paragraph("Not enough history yet for a forecast.", s["body"]))

    story += [Spacer(1, 10), Paragraph(
        "Counts and times only: no names, contact details or message text. Response promises come from the "
        "school's own settings (config/school_info.yaml). Generated by SchoolConnect "
        f"on {data['generated_at'].replace('T', ' ')} UTC.", s["small"])]
    doc.build(story)
    return buffer.getvalue()
