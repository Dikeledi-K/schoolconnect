"""Week 4 page: the automated weekly business report (PDF) for the whole school and each department."""

from datetime import date

import streamlit as st

import api_client as api
import auth
import ui

ui.page("Weekly reports", "A one-page summary of each week for the principal, the SGB and each department: "
        "key figures, trends, wins and concerns, and what to expect next week.", "🗂️")
me = auth.require_login()

try:
    scopes = api.analytics_scopes()
    weeks = api.report_weeks(12)
except api.ApiError as err:
    st.error(str(err))
    st.stop()
if not scopes:
    ui.empty_state("🔒", "No reports for your role", "Ask the principal for access.")
    st.stop()
names = {s["key"]: s["name"] for s in scopes}


def week_label(monday: str) -> str:
    d = date.fromisoformat(monday)
    return f"Week of {d.day} {d:%B %Y}"


# ---- Make a report -------------------------------------------------------------
with st.container(border=True):
    st.markdown("**Make a report**")
    st.caption("Reports are made automatically every Monday for the week before (Week 8 scheduler). "
               "You can also make one now; it replaces any older version of the same report.")
    c1, c2, c3 = st.columns([1.4, 1.4, 1])
    scope = c1.selectbox("Department", list(names), format_func=names.get)
    week = c2.selectbox("Week", weeks, format_func=week_label)
    c3.write("")
    if c3.button("Make report", type="primary", width="stretch"):
        with st.spinner("Working out the figures and drawing the report..."):
            try:
                made = api.create_report(week, scope)
            except api.ApiError as err:
                st.error(str(err))
            else:
                st.session_state["just_made"] = made["id"]
                st.success(f"Report ready: {names[scope]}, {week_label(week)}.")

# ---- Stored reports -------------------------------------------------------------
st.subheader("Reports")
show = st.selectbox("Show", ["All my departments"] + list(names),
                    format_func=lambda k: k if k == "All my departments" else names[k])
try:
    reports = api.list_reports(None if show == "All my departments" else show)
except api.ApiError as err:
    st.error(str(err))
    st.stop()
if not reports:
    ui.empty_state("🗂️", "No reports yet", "Make one above, or wait for Monday's automatic reports.")
    st.stop()

for rep in reports:
    new = st.session_state.get("just_made") == rep["id"]
    with st.container(border=True):
        top, button = st.columns([4, 1])
        top.markdown(f"**{rep['scope_name']}** · {week_label(rep['week_start'])}" + ("  🆕" if new else ""))
        plural = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")  # noqa: E731
        top.caption(f"{plural(rep['messages'], 'message')} · {plural(rep['wins'], 'win')} · "
                    f"{plural(rep['concerns'], 'concern')} · made by "
                    f"{rep['created_by']} on {rep['created_at'][:16].replace('T', ' ')} UTC"
                    + ("" if rep["summary_method"] == "template" else f" · summary worded by AI ({rep['summary_method']})"))
        st.write(rep["summary"])
        key = f"pdf_{rep['id']}"
        if button.button("Prepare PDF", key=f"prep_{rep['id']}", width="stretch"):
            try:
                st.session_state[key] = api.report_pdf(rep["id"])
            except api.ApiError as err:
                st.error(str(err))
        if key in st.session_state:
            button.download_button("⬇️ Download", st.session_state[key], type="primary", width="stretch",
                                   file_name=f"schoolconnect-{rep['scope']}-{rep['week_start']}.pdf",
                                   mime="application/pdf", key=f"dl_{rep['id']}")
