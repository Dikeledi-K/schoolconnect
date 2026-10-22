"""Staff page: filter tickets, read them and change their status.

Staff login arrives in Week 7. Until then this page is protected only by the
API key that the Streamlit server holds (parents never see it).
"""

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Staff inbox - SchoolConnect", page_icon="📥", layout="wide")

URGENCY_ICON = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}

st.title("📥 Staff inbox")

try:
    tax = api.taxonomy()
except api.ApiError as err:
    st.error(str(err))
    st.stop()

categories = {c["code"]: c["display_name"] for c in tax["categories"]}
roles = {r["code"]: r["name"] for r in tax["staff_roles"]}
languages = {lang["code"]: lang["name"] for lang in tax["languages"]}
statuses = {s["code"]: s["label"] for s in tax["statuses"]}
urgencies = [u["code"] for u in tax["urgency_levels"]]

# ---- Filters -------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    f_status = st.selectbox("Status", ["All"] + list(statuses), format_func=lambda s: statuses.get(s, s))
    f_category = st.selectbox("Category", ["All"] + list(categories), format_func=lambda c: categories.get(c, c))
    f_urgency = st.selectbox("Urgency", ["All"] + urgencies)
    f_role = st.selectbox("Routed to", ["All"] + list(roles), format_func=lambda r: roles.get(r, r))
    f_language = st.selectbox("Language", ["All"] + list(languages), format_func=lambda x: languages.get(x, x))
    f_human = st.checkbox("Only tickets that need a person")
    f_search = st.text_input("Search text or reference")

try:
    tickets = api.list_tickets(
        status=f_status, category=f_category, urgency=f_urgency, routed_role=f_role,
        language=f_language, needs_human=True if f_human else None, search=f_search, limit=500,
    )
except api.ApiError as err:
    st.error(str(err))
    st.stop()

if not tickets:
    st.info("No tickets match these filters.")
    st.stop()

# Most urgent first. The API already returns newest first, and Python's sort
# is "stable", so within each urgency level the newest stay on top.
tickets.sort(key=lambda t: -urgencies.index(t["urgency"]))

open_critical = [t for t in tickets if t["urgency"] == "critical" and t["status"] != "resolved"]
if open_critical:
    st.error(f"🚨 {len(open_critical)} open critical ticket(s). These need immediate human action.")

table = pd.DataFrame([{
    "Reference": t["reference"],
    "Urgency": f"{URGENCY_ICON[t['urgency']]} {t['urgency']}",
    "Category": categories[t["category"]],
    "Routed to": roles.get(t["routed_role"], t["routed_role"]),
    "Language": languages.get(t["language"], t["language"]),
    "Status": statuses[t["status"]],
    "Received (UTC)": t["created_at"][:16].replace("T", " "),
    "Message": t["message"][:90],
} for t in tickets])
st.caption(f"{len(tickets)} ticket(s)")
st.dataframe(table, hide_index=True, width="stretch")

# ---- Ticket detail -------------------------------------------------------
st.divider()
by_ref = {t["reference"]: t for t in tickets}
ref = st.selectbox("Open a ticket", list(by_ref))
t = by_ref[ref]

left, right = st.columns([2, 1])
with left:
    st.subheader(f"{URGENCY_ICON[t['urgency']]} {t['reference']}")
    st.write(t["message"])
    st.caption(
        f"From: {t['parent_name'] or 'not given'} · Contact: {t['parent_contact'] or 'not given'} · "
        f"Grade: {t['learner_grade'] or '-'} · Channel: {t['channel']}"
    )
    if t["safety_flag"]:
        st.error("Learner safety concern: a person must handle this. Do not rely on an automatic reply.")
    with st.expander("Why was it classified this way?"):
        st.write(f"**Method:** {t['method']} · **Confidence:** {t['confidence']:.0%}")
        st.write(t["reason"])
with right:
    st.metric("Category", categories[t["category"]])
    st.metric("Routed to", roles.get(t["routed_role"], t["routed_role"]))
    new_status = st.selectbox("Status", list(statuses), index=list(statuses).index(t["status"]),
                              format_func=lambda s: statuses[s], key=f"status_{t['id']}")
    if st.button("Update status", type="primary", disabled=new_status == t["status"]):
        try:
            api.update_status(t["id"], new_status)
        except api.ApiError as err:
            st.error(str(err))
        else:
            st.success(f"{t['reference']} is now '{statuses[new_status]}'.")
            st.rerun()
