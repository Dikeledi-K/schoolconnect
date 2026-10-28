"""Shared look and feel for every SchoolConnect page ("warm & friendly" design).

Base colours and the font live in .streamlit/config.toml (the theme). This file adds
what the theme cannot do: the page header banner, the button-style sidebar menu,
card-style metrics and coloured urgency labels. Pure presentation - no API calls
and no business logic here.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Urgency uses the fixed "status" colours (good / warning / serious / critical).
# They are always shown WITH a text label, never colour alone (colour-blind safe).
URGENCY_COLOUR = {"low": "#0ca30c", "medium": "#fab219", "high": "#ec835a", "critical": "#d03b3b"}
URGENCY_TEXT = {"low": "#ffffff", "medium": "#3b2a1a", "high": "#3b2a1a", "critical": "#ffffff"}

# Week 7: response-time (SLA) badges, also always with a text label.
SLA_COLOUR = {"overdue": "#d03b3b", "due_soon": "#fab219", "on_track": "#0ca30c", "met": "#8a8984"}
SLA_TEXT = {"overdue": "#ffffff", "due_soon": "#3b2a1a", "on_track": "#ffffff", "met": "#ffffff"}
SLA_ICON = {"overdue": "⏰", "due_soon": "⏳", "on_track": "🕒", "met": "✔"}

# Chart ink and gridlines: warm browns, kept quiet so the data stands out.
INK = "#3b2a1a"
MUTED_INK = "#7a6552"
GRID = "#f1e4d0"
BAR_COLOUR = "#0f766e"   # teal bars: friendly, and never confused with the urgency colours

_CSS = """
<style>
/* ===== Sidebar: light cream panel, menu items are big rounded buttons ===== */
[data-testid="stSidebar"] { background: #fff1dc; border-right: 1px solid #f3dcb8; }
/* App badge above the menu: name + tagline on a slowly shimmering sunset gradient.
   The nav is made a flex column so we can place the tagline (::after) under the name
   (::before) using "order", even though ::after normally comes after the menu. */
[data-testid="stSidebarNav"] { display: flex; flex-direction: column; }
[data-testid="stSidebarNav"]::before {
  order: -2; content: "🏫 SchoolConnect"; color: #ffffff; font-size: 1.35rem; font-weight: 800;
  white-space: nowrap;   /* keep the icon and the name on one line */
  letter-spacing: 0.01em; text-shadow: 0 2px 4px rgba(124, 45, 18, 0.35);
  padding: 1rem 1.1rem 0.15rem 1.1rem; border-radius: 1.2rem 1.2rem 0 0;
  background: linear-gradient(110deg, #c2410c, #ea580c, #f59e0b, #be3455, #c2410c);
  background-size: 300% 100%; animation: sc-shimmer 9s ease-in-out infinite;
}
[data-testid="stSidebarNav"]::after {
  order: -1; content: "Every parent heard, every child safe ✨"; color: #fff7ed;
  font-size: 0.85rem; font-weight: 700; padding: 0.1rem 1.1rem 0.95rem 1.1rem; margin: -1px 0 1rem 0;
  border-radius: 0 0 1.2rem 1.2rem; box-shadow: 0 6px 14px rgba(194, 65, 12, 0.30);
  background: linear-gradient(110deg, #c2410c, #ea580c, #f59e0b, #be3455, #c2410c);
  background-size: 300% 100%; animation: sc-shimmer 9s ease-in-out infinite;
}
@keyframes sc-shimmer {
  0%, 100% { background-position: 0% 50%; }
  50%      { background-position: 100% 50%; }
}
/* Respect people who turn off animations in their device settings */
@media (prefers-reduced-motion: reduce) {
  [data-testid="stSidebarNav"]::before, [data-testid="stSidebarNav"]::after { animation: none; }
}
[data-testid="stSidebarNavLink"] {
  background: #ffffff; border: 2px solid #f3dcb8; border-radius: 999px;
  padding: 0.6rem 1rem; margin-bottom: 0.5rem;
  box-shadow: 0 2px 0 #f3dcb8; transition: transform 0.15s, box-shadow 0.15s;
}
[data-testid="stSidebarNavLink"] p { color: #3b2a1a; font-weight: 700; font-size: 1rem; }
[data-testid="stSidebarNavLink"]:hover {
  border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 4px 0 var(--accent);
}
/* The page you are on: filled with that page's colour, white text */
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: var(--accent); border-color: var(--accent); box-shadow: 0 3px 0 rgba(59, 42, 26, 0.25);
}
[data-testid="stSidebarNavLink"][aria-current="page"] p { color: #ffffff; }
/* One colour + icon per page, in menu order:
   Home, Send a message, My work, Staff inbox, Fee exemptions, Forecast, Risk.
   Shades are dark enough for white text (contrast 4.5:1 or more). */
[data-testid="stSidebarNavItems"] li:nth-child(1) a { --accent: #c2410c; }
[data-testid="stSidebarNavItems"] li:nth-child(2) a { --accent: #be3455; }
[data-testid="stSidebarNavItems"] li:nth-child(3) a { --accent: #6d28d9; }
[data-testid="stSidebarNavItems"] li:nth-child(4) a { --accent: #15803d; }
[data-testid="stSidebarNavItems"] li:nth-child(5) a { --accent: #0369a1; }
[data-testid="stSidebarNavItems"] li:nth-child(6) a { --accent: #b45309; }
[data-testid="stSidebarNavItems"] li:nth-child(7) a { --accent: #0f766e; }
[data-testid="stSidebarNavItems"] li:nth-child(1) a p::before { content: "🏠  "; }
[data-testid="stSidebarNavItems"] li:nth-child(2) a p::before { content: "✉️  "; }
[data-testid="stSidebarNavItems"] li:nth-child(3) a p::before { content: "✅  "; }
[data-testid="stSidebarNavItems"] li:nth-child(4) a p::before { content: "📥  "; }
[data-testid="stSidebarNavItems"] li:nth-child(5) a p::before { content: "💰  "; }
[data-testid="stSidebarNavItems"] li:nth-child(6) a p::before { content: "📈  "; }
[data-testid="stSidebarNavItems"] li:nth-child(7) a p::before { content: "🛡️  "; }

/* ===== Page header banner: sunny orange, rounded, with a soft "sun" circle ===== */
.sc-hero {
  position: relative; overflow: hidden;
  background: linear-gradient(120deg, #c2410c 0%, #ea580c 60%, #f59e0b 100%);
  color: #ffffff; border-radius: 1.4rem; padding: 1.5rem 1.8rem; margin-bottom: 1.3rem;
  box-shadow: 0 6px 18px rgba(194, 65, 12, 0.25);
}
.sc-hero::after {   /* decorative circle in the corner */
  content: ""; position: absolute; right: -40px; top: -60px; width: 200px; height: 200px;
  border-radius: 50%; background: rgba(255, 255, 255, 0.16);
}
.sc-hero h1 { color: #ffffff; font-size: 2rem; font-weight: 800; margin: 0; padding: 0; }
.sc-hero p  { color: #fff7ed; font-size: 1.08rem; margin: 0.4rem 0 0 0; max-width: 52rem; }

/* ===== Cards: white, very rounded, warm soft shadow ===== */
[data-testid="stMetric"] {
  background: #ffffff; border: 1px solid #f3dcb8; border-radius: 1.1rem;
  padding: 1rem 1.2rem; box-shadow: 0 4px 12px rgba(122, 101, 82, 0.10);
}
[data-testid="stMetricLabel"] p { color: #7a6552; font-weight: 700; }
[data-testid="stMetricValue"] { color: #3b2a1a; font-weight: 800; font-size: 1.9rem; }
/* Long values (e.g. "Learner Welfare & Safety") wrap instead of being cut off with "...".
   (!important is needed because Streamlit's own ellipsis rule is more specific) */
[data-testid="stMetricValue"] div, [data-testid="stMetricValue"] p {
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
  line-height: 1.2;
}
[data-testid="stVerticalBlockBorderWrapper"] {
  background: #ffffff; border-radius: 1.1rem; box-shadow: 0 4px 12px rgba(122, 101, 82, 0.08);
}

/* ===== Buttons: chunky, rounded, with a little "pressable" shadow ===== */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {
  border-radius: 999px; font-weight: 700; padding: 0.45rem 1.3rem;
}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"],
.stDownloadButton button[kind="primary"] { box-shadow: 0 3px 0 #9a3412; }

/* Home page links: solid coloured pill buttons, same colour as the page in the sidebar */
[data-testid="stPageLink"] a {
  background: var(--btn, #c2410c); border-radius: 999px; padding: 0.5rem 1rem;
  justify-content: center; box-shadow: 0 3px 0 rgba(59, 42, 26, 0.25);
}
[data-testid="stPageLink"] a:hover { filter: brightness(1.1); }
[data-testid="stPageLink"] a p { color: #ffffff !important; font-weight: 800; }
/* One colour per Home card (parents, staff, finance, principal), matching the sidebar */
[data-testid="stColumn"]:nth-child(1) [data-testid="stPageLink"] a { --btn: #be3455; }
[data-testid="stColumn"]:nth-child(2) [data-testid="stPageLink"] a { --btn: #15803d; }
[data-testid="stColumn"]:nth-child(3) [data-testid="stPageLink"] a { --btn: #0369a1; }
[data-testid="stColumn"]:nth-child(4) [data-testid="stPageLink"] a { --btn: #0f766e; }

/* Section headings: warm brown, a little more space above */
h2, h3 { color: #3b2a1a; font-weight: 800 !important; margin-top: 0.6rem; }

/* Week 8: "this is a demo" strip under the page header */
.sc-demo {
  background: #fff7d6; border: 1px dashed #b45309; color: #3b2a1a; border-radius: 0.8rem;
  padding: 0.45rem 0.9rem; margin: -0.6rem 0 1rem 0; font-size: 0.92rem;
}

/* Coloured urgency label, e.g. <span class="sc-pill" style="...">High</span> */
.sc-pill {
  display: inline-block; padding: 0.15rem 0.7rem; border-radius: 999px;
  font-size: 0.85rem; font-weight: 800; letter-spacing: 0.02em;
}
</style>
"""


def page(title: str, subtitle: str, icon: str, layout: str = "wide") -> None:
    """Set up a page: browser tab, shared styles and the header banner. Call first on every page."""
    st.set_page_config(page_title=f"{title} - SchoolConnect", page_icon=icon, layout=layout)
    st.markdown(_CSS, unsafe_allow_html=True)
    # title/subtitle are fixed strings written in our own code, never user input.
    st.markdown(f'<div class="sc-hero"><h1>{icon} {title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)
    demo_banner()


DEMO_TEXT = ("🧪 <b>Demo: fictional school, synthetic data.</b> Ubuntu Demo Primary School does not exist; "
             "every parent, learner, staff member and message here is made up.")


def demo_banner() -> None:
    """Week 8: always visible, so nobody mistakes the live demo for a real school."""
    st.markdown(f'<div class="sc-demo" role="note">{DEMO_TEXT}</div>', unsafe_allow_html=True)


def urgency_pill(urgency: str) -> str:
    """HTML for a coloured urgency label. `urgency` comes from the taxonomy, not from parents."""
    bg, fg = URGENCY_COLOUR.get(urgency, "#898781"), URGENCY_TEXT.get(urgency, "#ffffff")
    return f'<span class="sc-pill" style="background:{bg};color:{fg}">{urgency.title()}</span>'


def sla_badge(sla: dict | None) -> str:
    """HTML badge such as "⏰ overdue 3 h" or "🕒 2 h left". `sla` comes from the API."""
    if not sla:
        return ""
    status = sla["status"]
    return (f'<span class="sc-pill" style="background:{SLA_COLOUR[status]};color:{SLA_TEXT[status]}">'
            f'{SLA_ICON[status]} {sla["label"]}</span>')


def empty_state(icon: str, title: str, text: str) -> None:
    """A friendly message instead of an empty table."""
    with st.container(border=True):
        st.markdown(f"### {icon} {title}")
        st.write(text)


def style_urgency(table: pd.DataFrame, column: str = "Urgency"):
    """Colour the urgency column of a table so critical tickets jump out."""
    def colour(value: str) -> str:
        key = str(value).split()[-1].lower()
        if key not in URGENCY_COLOUR:
            return ""
        return f"background-color:{URGENCY_COLOUR[key]};color:{URGENCY_TEXT[key]};font-weight:700"
    return table.style.map(colour, subset=[column])


def bar_chart(labels: list[str], values: list[int], colours: list[str] | str = BAR_COLOUR,
              horizontal: bool = False, height: int = 320) -> go.Figure:
    """A clean bar chart: value labels on the bars, quiet grid, hover shows the exact count."""
    fig = go.Figure(go.Bar(
        x=values if horizontal else labels, y=labels if horizontal else values,
        orientation="h" if horizontal else "v", marker=dict(color=colours, cornerradius=6),
        text=values, textposition="outside", textfont=dict(color=INK),
        hovertemplate="%{label}: %{value} tickets<extra></extra>" if not horizontal
        else "%{y}: %{x} tickets<extra></extra>", cliponaxis=False))
    fig.update_layout(
        height=height, margin=dict(l=10, r=30, t=10, b=10), bargap=0.35,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Nunito, sans-serif", color=INK, size=13), showlegend=False)
    value_axis = dict(showgrid=True, gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED_INK))
    label_axis = dict(showgrid=False, tickfont=dict(color=INK, size=13))
    if horizontal:
        fig.update_layout(xaxis=value_axis, yaxis={**label_axis, "autorange": "reversed"})
    else:
        fig.update_layout(yaxis=value_axis, xaxis=label_axis)
    return fig
