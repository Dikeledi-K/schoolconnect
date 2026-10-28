"""Week 3 page: how did the help desk do? Volumes, response times, promises kept, trends and insights."""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client as api
import auth
import ui

ui.page("Analytics", "How the help desk is doing: how many messages, how fast parents hear back, and "
        "whether we keep our promises. Counts only: no names or messages.", "📊")
me = auth.require_login()


@st.cache_data(ttl=60, show_spinner=False)
def cached(name: str, token: str | None, **kwargs):
    # The token is part of the cache key, so two staff members never share cached figures.
    return getattr(api, name)(**kwargs)


def call(name: str, **kwargs):
    try:
        return cached(name, api.current_token(), **kwargs)
    except api.ApiError as err:
        st.error(str(err))
        st.stop()


# ---- Filters (one row) -------------------------------------------------------
scopes = call("analytics_scopes")
if not scopes:
    ui.empty_state("🔒", "No department figures for your role", "Ask the principal for access.")
    st.stop()
names = {s["key"]: s["name"] for s in scopes}
c1, c2, c3 = st.columns([1.4, 1.2, 1.4])
scope = c1.selectbox("Department", list(names), format_func=names.get)
period = c2.selectbox("Period", ["Last week", "Last 4 weeks", "Last 12 weeks", "Choose dates"])
today = date.today()
last_monday = today - timedelta(days=today.weekday()) - timedelta(days=7)
if period == "Choose dates":
    picked = c3.date_input("From – to", value=(last_monday, last_monday + timedelta(days=6)), max_value=today)
    if not isinstance(picked, tuple) or len(picked) != 2:
        st.info("Choose a start and an end date.")
        st.stop()
    start, end = picked
else:
    weeks = {"Last week": 1, "Last 4 weeks": 4, "Last 12 weeks": 12}[period]
    start, end = last_monday - timedelta(weeks=weeks - 1), last_monday + timedelta(days=6)
    c3.caption(f"{start:%d %b %Y} to {end:%d %b %Y} (complete weeks)")

data = call("analytics_summary", start=start.isoformat(), end=end.isoformat(), scope=scope)
m, insights = data["metrics"], data["insights"]
v, r = m["volume"], m["response"]
word = "week" if m["period"]["days"] == 7 else "period"

# ---- KPI tiles: this period vs the one before ---------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Parent messages", v["total"],
          delta=None if v["change_pct"] is None else f"{v['change_pct']:+d}% vs previous {word}", delta_color="off")
fr, fr_prev = r["first_response"]["median"], r["previous"]["first_response"]["median"]
k2.metric("Median first response", "–" if fr is None else f"{fr:.1f} office h",
          delta=None if fr is None or fr_prev is None else f"{fr - fr_prev:+.1f} h",
          delta_color="inverse", help="Half of parents heard back within this many office hours.")
rate, rate_prev = r["on_time"]["rate"], r["previous"]["on_time"]["rate"]
target = m["sla_target_rate"]
# Show 89.5% rather than "90%" when rounding would hide that the 90% target was missed.
rate_shown = ("–" if rate is None else f"{rate:.1%}" if rate < target and round(rate * 100) >= round(target * 100)
              else f"{rate:.0%}")
k3.metric("Answered on time", rate_shown,
          delta=None if rate is None or rate_prev is None else f"{(rate - rate_prev) * 100:+.0f} points",
          help=f"First response within the promise made to parents. Target {m['sla_target_rate']:.0%}.")
k3.caption(f"target {m['sla_target_rate']:.0%} · {r['on_time']['missed']} late")
k4.metric("Open at end of period", m["backlog"]["open"])
k4.caption(f"{m['backlog']['overdue']} past their promised time" if m["backlog"]["overdue"]
           else "none past their promised time")

# ---- Weekly summary insights ---------------------------------------------------
st.subheader("💡 What happened")
icon = {"win": "✅", "concern": "⚠️", "info": "ℹ️"}
for item in insights:
    st.markdown(f"{icon[item['type']]} {item['text']}")

# ---- Trends --------------------------------------------------------------------
st.subheader("Trends (last 12 weeks)")
trend = pd.DataFrame(call("analytics_trends", weeks=12, scope=scope)["weeks"])
trend["label"] = pd.to_datetime(trend["week_start"]).dt.strftime("%d %b")
left, right = st.columns(2)
with left:
    st.markdown("**Messages per week**")
    st.plotly_chart(ui.bar_chart(trend["label"].tolist(), trend["total"].tolist(), height=280), width="stretch")
with right:
    st.markdown("**Median first response (office hours)**")
    fig = go.Figure(go.Scatter(
        x=trend["label"], y=trend["median_first_response"], mode="lines+markers",
        line=dict(color=ui.BAR_COLOUR, width=2), marker=dict(size=8),
        hovertemplate="Week of %{x}: %{y:.1f} office hours<extra></extra>"))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color=ui.INK),
                      yaxis=dict(rangemode="tozero", gridcolor=ui.GRID, title="office hours"),
                      xaxis=dict(showgrid=False))
    st.plotly_chart(fig, width="stretch")

st.markdown("**Answered on time, per week**")
fig = go.Figure(go.Scatter(
    x=trend["label"], y=trend["on_time_rate"], mode="lines+markers", name="On time",
    line=dict(color=ui.BAR_COLOUR, width=2), marker=dict(size=8),
    hovertemplate="Week of %{x}: %{y:.0%} on time<extra></extra>"))
fig.add_hline(y=m["sla_target_rate"], line_dash="dot", line_color=ui.MUTED_INK,
              annotation_text=f"target {m['sla_target_rate']:.0%}", annotation_position="bottom right")
fig.update_layout(height=240, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                  plot_bgcolor="rgba(0,0,0,0)", font=dict(color=ui.INK), showlegend=False,
                  # Zoom in on the range that matters (a rate line does not need to start at 0).
                  yaxis=dict(range=[max(0.0, min([x for x in trend["on_time_rate"] if x is not None]
                                                 + [m["sla_target_rate"]]) - 0.1), 1.02],
                             tickformat=".0%", gridcolor=ui.GRID), xaxis=dict(showgrid=False))
st.plotly_chart(fig, width="stretch")

# ---- This period in detail -----------------------------------------------------
st.subheader("This period in detail")
topics = pd.DataFrame([{
    "Topic": c["name"], "Messages": c["n"], f"Previous {word}": c["previous"], "Change": f"{c['change']:+d}",
    "Median first response": "–" if c["median_first_response"] is None else f"{c['median_first_response']:.1f} h",
} for c in sorted(v["by_category"].values(), key=lambda c: c["n"], reverse=True)])
st.dataframe(topics, hide_index=True, width="stretch")

if m["period"]["days"] > 1:
    days = pd.DataFrame(v["by_day"])
    days["label"] = pd.to_datetime(days["date"]).dt.strftime("%a %d %b")
    st.markdown("**Messages per day**")
    st.plotly_chart(ui.bar_chart(days["label"].tolist(), days["n"].tolist(), height=260), width="stretch")
    st.caption("Weekends are naturally quiet; weekend messages are answered on Monday.")

tabs = st.tabs(["Urgency", "Language", "Channel", "Grade band", "Weekday"])
breakdowns = [v["by_urgency"], v["by_language"], v["by_channel"], v["by_grade_band"], v["by_weekday"]]
for tab, counts in zip(tabs, breakdowns):
    with tab:
        shown = {k: n for k, n in counts.items() if n} or {"none": 0}
        colours = [ui.URGENCY_COLOUR.get(k, ui.BAR_COLOUR) for k in shown] if counts is v["by_urgency"] else ui.BAR_COLOUR
        st.plotly_chart(ui.bar_chart([k.title() if counts is v["by_urgency"] else k for k in shown],
                                     list(shown.values()), colours=colours, horizontal=True,
                                     height=60 + 36 * len(shown)), width="stretch")

with st.expander("ℹ️ How these figures are worked out"):
    st.markdown(
        "- **Office hours** are Monday to Friday 07:30–15:30, excluding public holidays: the time the school "
        "could actually respond. A message sent on Friday at 15:00 and answered on Monday at 08:30 took "
        "1.5 office hours.\n"
        "- **Median** means half of parents waited less than this, half waited more. It is not thrown off by "
        "one very slow reply the way an average is.\n"
        "- **Answered on time** compares the first response with the promise made to parents "
        "(critical: 1 hour; high: 1 school day; medium: 2; low: 5).\n"
        "- **Parents who wrote more than once** counts contact details used on more than one message; the "
        "details themselves are never shown.\n"
        "- The weekly report (next page) turns these figures into a PDF for the principal, the SGB and each "
        "department.")
