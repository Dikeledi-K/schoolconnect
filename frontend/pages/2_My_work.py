"""Week 7 staff page: MY open tickets, overdue first, with quick actions.

Cards instead of a wide table, so it also works on a phone.
"""

import streamlit as st

import api_client as api
import auth
import ui

ui.page("My work", "Your open tickets: overdue first, then the most urgent. Start, hand over or resolve them here.",
        "✅", layout="centered")
me = auth.require_login()

try:
    tax = api.taxonomy()
    tickets = api.my_work()
    colleagues = [s for s in api.staff_list() if s["active"] and s["id"] != me["id"]]
except api.ApiError as err:
    st.error(str(err))
    st.stop()

categories = {c["code"]: c["display_name"] for c in tax["categories"]}
statuses = {s["code"]: s["label"] for s in tax["statuses"]}

overdue = sum(t["sla"]["status"] == "overdue" for t in tickets)
due_soon = sum(t["sla"]["status"] == "due_soon" for t in tickets)
c1, c2, c3 = st.columns(3)
c1.metric("My open tickets", len(tickets))
c2.metric("Overdue", overdue)
c3.metric("Due soon", due_soon)
if overdue:
    st.error(f"⏰ {overdue} ticket(s) are past their response time. Overdue tickets are escalated automatically.")

if not tickets:
    ui.empty_state("🎉", "Nothing waiting for you",
                   "New tickets are assigned automatically to the person in the right role with the least "
                   "open work. Have a look at the Staff inbox for your role's queue.")
    st.stop()


def run(action, success: str) -> None:
    """Call the API, show a friendly result, refresh the page."""
    try:
        with st.spinner("Working on it..."):   # the free server can take a few seconds
            action()
    except api.ApiError as err:
        st.error(str(err))
    else:
        st.toast(success)
        st.rerun()


for t in tickets:
    with st.container(border=True):
        st.markdown(f"**{t['reference']}** &nbsp; {ui.urgency_pill(t['urgency'])} &nbsp; {ui.sla_badge(t['sla'])}",
                    unsafe_allow_html=True)
        st.caption(f"{categories[t['category']]} · {statuses[t['status']]} · received "
                   f"{t['created_at'][:16].replace('T', ' ')} UTC"
                   + (f" · escalated {t['escalation_level']}×" if t["escalation_level"] else ""))
        preview = t["message"] if len(t["message"]) <= 160 else t["message"][:160] + "…"
        st.write(preview)
        if t["safety_flag"]:
            st.warning("Learner safety: phone the parent personally. Do not rely on an automatic reply.")

        b1, b2, b3 = st.columns([1, 1, 2])
        if t["status"] == "new":
            if b1.button("▶ Start", key=f"start_{t['id']}", type="primary",
                         help="Marks it 'In progress' and stops the response-time clock"):
                run(lambda t=t: api.update_status(t["id"], "in_progress"), f"{t['reference']} started")
        if b2.button("✔ Resolve", key=f"resolve_{t['id']}"):
            run(lambda t=t: api.update_status(t["id"], "resolved"), f"{t['reference']} resolved")
        with b3.popover("↪ Hand over", width="stretch"):
            if colleagues:
                pick = st.selectbox("Give it to", colleagues, key=f"to_{t['id']}",
                                    format_func=lambda s: f"{s['name']} ({auth.ROLE_NAMES[s['role']]})")
                why = st.text_input("Why? (optional)", key=f"why_{t['id']}")
                if st.button("Hand over", key=f"assign_{t['id']}"):
                    run(lambda t=t, pick=pick, why=why: api.assign(t["id"], pick["id"], why or None),
                        f"{t['reference']} handed to {pick['name']}")
            else:
                st.write("No colleagues have an account yet.")
        st.page_link("pages/3_Staff_inbox.py", label="Open in the inbox to reply", icon="📥")
