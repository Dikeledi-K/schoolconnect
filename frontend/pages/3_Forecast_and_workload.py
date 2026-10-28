"""Week 5 staff page: forecast of parent messages, staff workload and recommendations.

Answers: which staff member will be overloaded, when, and what should the school do about it?
"""

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import api_client as api
import ui


# Chart colours: validated categorical slots in fixed order, and a one-hue sequential ramp.
ACTUAL_COLOUR = "#2a78d6"      # slot 1 (blue)
FORECAST_COLOUR = "#eb6834"    # slot 2 (orange)
SEQUENTIAL_BLUE = [[0, "#cde2fb"], [0.5, "#5598e7"], [1, "#0d366b"]]
MODEL_NAMES = {"seasonal_naive": "Same as last week", "last_year": "Same day last year",
               "moving_average": "Recent average", "ml_calendar": "Machine learning"}
STATUS_LABEL = {"ok": "✅ OK", "busy": "🟡 Busy", "overloaded": "🔴 Overloaded"}
SEVERITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🔵", "info": "ℹ️"}


@st.cache_data(ttl=60, show_spinner="Working out the forecast...")
def cached(name: str, **kwargs):
    return getattr(api, name)(**kwargs)


def call(name: str, **kwargs):
    """Call the API; show a friendly message (never a stack trace) if it fails."""
    try:
        return cached(name, **kwargs)
    except api.ApiError as err:
        st.error(str(err))
        if "history" in str(err):
            st.info("Load demo history with:  python scripts/generate_history.py --reset")
        if st.button("Try again"):
            st.cache_data.clear()
            st.rerun()
        st.stop()


ui.page("Forecast & workload", "Which staff will be overloaded, when, and what should the school do about it?", "📈")

tax = call("taxonomy")
categories = {c["code"]: c["display_name"] for c in tax["categories"]}
roles = {r["code"]: r["name"] for r in tax["staff_roles"]}

# ---- Controls (one row) --------------------------------------------------
c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1.2])
mode = c1.radio("View", ["Live (from today)", "Backtest demo"], horizontal=True,
                help="Backtest demo: pretend it is a past date, forecast, then compare with what really happened.")
as_of = None
if mode == "Backtest demo":
    as_of = c2.date_input("Pretend today is", value=date(2025, 12, 15),
                          max_value=date.today() - timedelta(days=7)).isoformat()
days = c3.slider("Days ahead", 7, 60, 45 if as_of else 14)
category = c4.selectbox("Category", ["total"] + list(categories),
                        format_func=lambda k: "All messages" if k == "total" else categories[k])

base = call("workload", days=days, as_of=as_of)
with st.expander("🧑‍💼 What if staff capacity changes? (scenario)"):
    default_staff = {r["role"]: r["staff"] for r in base["daily"][: len(roles)]}
    cols = st.columns(len(roles))
    staff = {code: cols[i].number_input(name, 0.0, 10.0, float(default_staff.get(code, 1)), 0.5, key=f"staff-{code}")
             for i, (code, name) in enumerate(roles.items())}
changed = {k: v for k, v in staff.items() if v != default_staff.get(k)}
staff_param = ",".join(f"{k}:{v:g}" for k, v in changed.items()) or None

fc = call("forecast", days=days, as_of=as_of)
wl = call("workload", days=days, as_of=as_of, staff=staff_param) if staff_param else base
ins = call("insights", days=days, as_of=as_of, staff=staff_param)
sg = call("surges", days=days, as_of=as_of)
ev = call("evaluation", as_of=as_of)

rows = pd.DataFrame(fc["rows"])
rows["date"] = pd.to_datetime(rows["date"])
weekly = pd.DataFrame(wl["weekly"])
start = pd.Timestamp(fc["as_of"])

if fc["is_backtest"]:
    st.info(f"**Backtest view.** The forecast uses only data from before {start:%d %b %Y}. "
            "The blue line after that date is what really happened.")

# ---- KPI tiles -----------------------------------------------------------
total = rows[rows["category"] == "total"]
next7 = total[total["date"] < start + pd.Timedelta(days=7)]["forecast"].sum()
peak = total.loc[total["forecast"].idxmax()]
last_year = call("history", start=(start - pd.Timedelta(days=364)).date().isoformat(),
                 end=(start - pd.Timedelta(days=364 - days + 1)).date().isoformat(), category="total")
ly = sum(r["total"] for r in last_year) if last_year else 0
flagged = weekly[(weekly["status"] != "ok") | weekly["overload_risk"]] if not weekly.empty else weekly

k1, k2, k3, k4 = st.columns(4)
k1.metric("Expected next 7 days", f"{next7:.0f}")
k1.caption("parent messages")
k2.metric(f"Expected next {days} days", f"{total['forecast'].sum():.0f}")
if ly:
    change = (total["forecast"].sum() - ly) / ly
    k2.caption("about the same as last year" if abs(change) < 0.01 else f"{change:+.0%} vs same period last year")
k3.metric("Busiest day", f"{peak['date']:%a %d %b}")
k3.caption(f"about {peak['forecast']:.0f} messages")
k4.metric("Roles needing attention", f"{flagged['role'].nunique() if len(flagged) else 0}")
k4.caption(", ".join(sorted(flagged["role_name"].unique())) if len(flagged) else "all within capacity")

# ---- Recommendations: what the principal acts on -------------------------
st.subheader("💡 Recommendations")
for item in ins["insights"]:
    st.markdown(f"{SEVERITY_ICON.get(item['severity'], '•')} {item['text']}")

# ---- History + forecast chart --------------------------------------------
st.subheader("Messages per day: history and forecast")
chart_start = start - pd.Timedelta(days=90)
hist = pd.DataFrame(call("history", start=chart_start.date().isoformat(),
                         end=(start + pd.Timedelta(days=days - 1)).date().isoformat(), category=category))
sel = rows[rows["category"] == category]

fig = go.Figure()
for event in fc["calendar_events"]:
    if pd.Timestamp(event["end"]) < chart_start:
        continue
    x0 = max(pd.Timestamp(event["start"]), chart_start)
    x1 = pd.Timestamp(event["end"]) + pd.Timedelta(hours=23)
    if event["type"] == "is_holiday_break":   # holidays: light grey band
        fig.add_vrect(x0=x0, x1=x1, fillcolor="#8a8984", opacity=0.12, line_width=0, layer="below",
                      annotation_text="Holiday", annotation_position="top left",
                      annotation_font_size=10, annotation_font_color="#52514e")
    else:                                      # exams / admissions: thin labelled bar along the top
        fig.add_vrect(x0=x0, x1=x1, y0=0.94, y1=1.0, fillcolor="#8a8984", opacity=0.35, line_width=0,
                      layer="below", annotation_text=event["label"], annotation_position="top left",
                      annotation_font_size=10, annotation_font_color="#52514e")
fig.add_trace(go.Scatter(x=pd.concat([sel["date"], sel["date"][::-1]]),
                         y=pd.concat([sel["upper"], sel["lower"][::-1]]),
                         fill="toself", fillcolor="rgba(235,104,52,0.15)", line_width=0,
                         hoverinfo="skip", name="80% range"))
if len(hist):
    hist["date"] = pd.to_datetime(hist["date"])
    fig.add_trace(go.Scatter(x=hist["date"], y=hist[category], name="Actual", mode="lines",
                             line=dict(color=ACTUAL_COLOUR, width=2),
                             hovertemplate="%{x|%a %d %b}: %{y} messages<extra>Actual</extra>"))
fig.add_trace(go.Scatter(x=sel["date"], y=sel["forecast"], name="Forecast", mode="lines",
                         line=dict(color=FORECAST_COLOUR, width=2, dash="dash"),
                         hovertemplate="%{x|%a %d %b}: ~%{y:.0f} expected<extra>Forecast</extra>"))
fig.add_vline(x=start, line_width=1, line_dash="dot", line_color="#52514e")
fig.update_layout(height=420, hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10),
                  legend=dict(orientation="h", y=-0.15), yaxis_title="Messages per day",
                  xaxis=dict(showgrid=False), yaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
st.plotly_chart(fig, width="stretch")
st.caption("Grey = school holidays; bars along the top = exams and admissions windows (approximate calendar). "
           "The dotted line is the forecast start. Weekends are naturally low.")

# ---- Workload heatmap + weekly table -------------------------------------
st.subheader("Staff workload (share of available time)")
daily = pd.DataFrame(wl["daily"])
if not daily.empty:
    daily["date"] = pd.to_datetime(daily["date"])
    pivot = daily.pivot_table(index="role_name", columns="date", values="utilisation").fillna(0)
    z = pivot.to_numpy() * 100
    text = [[f"{v:.0f}%{' ⚠' if v > 100 else ''}" for v in row] for row in z]
    heat = go.Figure(go.Heatmap(
        z=z, x=pivot.columns, y=pivot.index, text=text, texttemplate="%{text}" if days <= 21 else "",
        colorscale=SEQUENTIAL_BLUE, zmin=0, zmax=max(120, float(z.max())), xgap=2, ygap=2,
        colorbar=dict(title="%", ticksuffix="%"),
        hovertemplate="%{y}<br>%{x|%a %d %b}: %{z:.0f}% of available time<extra></extra>"))
    heat.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(heat, width="stretch")
    st.caption("Office days only. Weekend messages are added to Monday. ⚠ = more work than time available.")

    w = weekly.copy()
    buffer_col = f"Busy week (+{wl['planning_buffer']:.0%})"
    w["Week of"] = pd.to_datetime(w["week_start"]).dt.strftime("%d %b %Y")
    w["Expected"] = (w["utilisation"] * 100).round().astype(int).astype(str) + "%"
    w[buffer_col] = (w["utilisation_upper"] * 100).round().astype(int).astype(str) + "%"
    w["Status"] = w["status"].map(STATUS_LABEL) + w["overload_risk"].map({True: " · risk", False: ""})
    w = w.rename(columns={"role_name": "Role", "tickets": "Tickets", "hours_needed": "Hours needed",
                          "capacity_hours": "Hours available"})
    cols = ["Week of", "Role", "Tickets", "Hours needed", "Hours available", "Expected", buffer_col, "Status"]
    if "actual_utilisation" in w:
        actual = (w["actual_utilisation"].astype(float) * 100).round()
        w["What really happened"] = actual.map(lambda v: "" if pd.isna(v) else f"{v:.0f}%")
        cols.append("What really happened")
    attention = (w["status"] != "ok") | w["overload_risk"]
    only = st.toggle("Show only weeks that need attention", value=bool(attention.any()),
                     disabled=not attention.any())
    st.dataframe((w[attention] if only else w)[cols].round(1), hide_index=True, width="stretch")

# ---- Spikes --------------------------------------------------------------
st.subheader("⚡ Expected spikes")
if sg["surges"]:
    s = pd.DataFrame(sg["surges"])
    s["drivers"] = s["drivers"].map(", ".join)
    st.dataframe(s[["date", "expected_tickets", "typical_tickets", "ratio", "main_category_name",
                    "drivers", "extra_staff_hours"]].rename(columns={
                        "date": "Date", "expected_tickets": "Expected", "typical_tickets": "Normal day",
                        "ratio": "× normal", "main_category_name": "Main topic", "drivers": "Likely cause",
                        "extra_staff_hours": "Extra staff hours"}), hide_index=True, width="stretch")
else:
    st.write("No unusual spikes expected in this period.")

# ---- Accuracy ------------------------------------------------------------
st.subheader("🎯 How accurate is this?")
o = ev["overall"]
a1, a2, a3 = st.columns(3)
a1.metric("Forecast error (WAPE)", f"{o['wape']:.0%}", help="Total error ÷ total messages. Lower is better.")
a2.metric("Simple 'same as last week' rule", f"{o['baseline_wape']:.0%}")
a3.metric("Average error per day", f"±{o['mae']:.1f} messages")
if o["baseline_wape"]:
    st.caption(f"Tested on {o['days_tested']} days ({o['test_start']} to {o['test_end']}) the system had not "
               f"seen. Our forecast was {1 - o['wape'] / o['baseline_wape']:.0%} more accurate than the simple rule.")
accuracy = []
for c in ev["per_category"]:
    row = {"Category": categories.get(c["category"], c["category"])}
    for m, v in c["models"].items():
        mark = " ✔" if m == c["chosen_model"] else ""
        row[MODEL_NAMES.get(m, m)] = None if v["wape"] is None else f"{v['wape']:.0%}{mark}"
    accuracy.append(row)
st.dataframe(pd.DataFrame(accuracy), hide_index=True, width="stretch")
st.caption("Error (WAPE) of each method per category in the backtest. ✔ = method used for the forecast.")

with st.expander("ℹ️ How it works (plain language)"):
    st.markdown(
        "1. **Count** parent messages per day and per topic.\n"
        "2. **Add the school calendar**: term starts, admissions windows, exams, report days, holidays.\n"
        "3. **Try four methods** on the last 8 weeks, pretending we didn't know what happened:\n"
        + "".join(f"   - **{MODEL_NAMES.get(k, k)}**: {v}\n" for k, v in ev["model_descriptions"].items())
        + "4. **Pick the most accurate method for each topic.** Machine learning is only used if it "
          "clearly beats the simple methods.\n"
        "5. **Convert messages to staff hours** using average handling time per topic, and compare "
        "with the hours each role has available.\n"
        "6. **Explain** the result in plain language, with a suggested action.\n\n"
        "_Demo data is synthetic and the calendar is approximate (verify against the official DBE calendar)._")
