"""Staff page: filter tickets, read them and change their status.

Staff login arrives in Week 7. Until then this page is protected only by the
API key that the Streamlit server holds (parents never see it).
"""

import pandas as pd
import streamlit as st

import api_client as api
import ui



ui.page("Staff inbox", "Every parent message, most urgent first. Open a ticket to read it, "
        "correct the AI and approve a reply.", "📥")

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
    # Staff login arrives in Week 7; until then staff type their name so every correction
    # and approval in the audit log says who made it.
    staff_name = st.text_input("Your name (for the audit log)", key="staff_name").strip()
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
    "Urgency": t["urgency"].title(),
    "Category": categories[t["category"]],
    "Routed to": roles.get(t["routed_role"], t["routed_role"]),
    "Language": languages.get(t["language"], t["language"]),
    "Status": statuses[t["status"]],
    "Received (UTC)": t["created_at"][:16].replace("T", " "),
    "Message": t["message"][:90],
} for t in tickets])
st.caption(f"{len(tickets)} ticket(s)")
st.dataframe(ui.style_urgency(table), hide_index=True, width="stretch")

# ---- Ticket detail -------------------------------------------------------
st.divider()
by_ref = {t["reference"]: t for t in tickets}
ref = st.selectbox("Open a ticket", list(by_ref))
t = by_ref[ref]

left, right = st.columns([2, 1])
with left:
    st.markdown(f"### {t['reference']} &nbsp; {ui.urgency_pill(t['urgency'])}", unsafe_allow_html=True)
    st.container(border=True).write(t["message"])
    st.caption(
        f"From: {t['parent_name'] or 'not given'} · Contact: {t['parent_contact'] or 'not given'} · "
        f"Grade: {t['learner_grade'] or '-'} · Channel: {t['channel']}"
    )
    if t["safety_flag"]:
        st.error("Learner safety concern: a person must handle this. Do not rely on an automatic reply.")
    # Week 6 transparency: always say this is an AI suggestion, how sure it is, and why.
    source = "rules (offline)" if t["method"] == "rules" else ("staff" if t["method"] == "staff" else f"AI ({t['method']})")
    label = "✅ Checked by staff" if t["method"] == "staff" else "🤖 AI-suggested"
    st.info(f"**{label}** · method: {source} · confidence: {t['confidence']:.0%}"
            + (" · **low confidence: please check**" if t["confidence"] < 0.35 and t["method"] != "staff" else ""))
    with st.expander("Why was it classified this way?"):
        st.write(t["reason"])
        try:
            history = api.ticket_audit(t["id"])
        except api.ApiError:
            history = []
        fired = sorted({g for row in history for g in row["guardrails"]})
        if fired:
            st.write("**Safety guardrails applied:** " + ", ".join(fired))
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

    # ---- Week 6: correct the AI (human override) ------------------------------
    with st.expander("✏️ Correct the AI"):
        st.caption("Your correction is logged. Child-safety rules still apply: a safety ticket cannot be "
                   "lowered, but you can resolve it once it is handled.")
        cats = list(categories)
        new_cat = st.selectbox("Category", cats, index=cats.index(t["category"]),
                               format_func=lambda c: categories[c], key=f"cc_{t['id']}")
        new_urg = st.selectbox("Urgency", urgencies, index=urgencies.index(t["urgency"]), key=f"cu_{t['id']}")
        why = st.text_input("Reason for the change", key=f"cr_{t['id']}")
        changed = new_cat != t["category"] or new_urg != t["urgency"]
        if st.button("Save correction", disabled=not (changed and why and staff_name), key=f"cb_{t['id']}"):
            try:
                out = api.correct_classification(
                    t["id"], staff_name, why,
                    category=new_cat if new_cat != t["category"] else None,
                    urgency=new_urg if new_urg != t["urgency"] else None)
            except api.ApiError as err:
                st.error(str(err))
            else:
                if out["note"]:
                    st.warning(out["note"])
                else:
                    st.success("Correction saved.")
                st.rerun()
        if not staff_name:
            st.caption("Type your name in the sidebar first.")

# ---- Week 6: reply to the parent -----------------------------------------
st.divider()
st.subheader("✉️ Reply to the parent")
st.caption("Drafts use only the school's own facts (config/school_info.yaml). Nothing is sent until "
           "a staff member approves it; sending arrives in Week 7.")
try:
    existing = api.replies(t["id"])
except api.ApiError as err:
    st.error(str(err))
    existing = []

c1, c2 = st.columns([1, 3])
tone = c1.selectbox("Tone", ["formal", "friendly", "urgent"], key=f"tone_{t['id']}")
if c1.button("Draft a reply", key=f"draft_{t['id']}"):
    try:
        api.draft_reply(t["id"], tone)
    except api.ApiError as err:
        st.error(str(err))
    else:
        st.rerun()

for reply in reversed(existing):
    box = c2.container(border=True)
    by = "template" if reply["method"] == "template" else f"AI ({reply['method']}), fact-checked"
    status = "✅ Approved by " + (reply["approved_by"] or "?") if reply["status"] == "approved" else "📝 Draft"
    box.markdown(f"**{status}** · {reply['tone']} · written by {by}" + (" · edited by staff" if reply["edited"] else ""))
    if reply["acknowledgement_only"]:
        box.warning("Learner welfare/safety: acknowledgement only. A person must follow up personally.")
    for note in filter(None, reply["notes"].split("\n")):
        box.caption("ℹ️ " + note)
    if reply["status"] == "draft":
        text = box.text_area("Reply text", reply["body"], height=260, key=f"body_{reply['id']}")
        b1, b2 = box.columns(2)
        if b1.button("Save edits", disabled=text == reply["body"] or not staff_name, key=f"save_{reply['id']}"):
            try:
                api.edit_reply(reply["id"], text, staff_name)
            except api.ApiError as err:
                box.error(str(err))
            else:
                st.rerun()
        if b2.button("Approve", type="primary", disabled=not staff_name or text != reply["body"],
                     key=f"approve_{reply['id']}"):
            try:
                api.approve_reply(reply["id"], staff_name)
            except api.ApiError as err:
                box.error(str(err))
            else:
                st.rerun()
        if not staff_name:
            box.caption("Type your name in the sidebar to edit or approve.")
        elif text != reply["body"]:
            box.caption("Save your edits before approving.")
    else:
        box.text(reply["body"])

# ---- Week 6: audit trail and privacy -------------------------------------
with st.expander("🧾 Audit trail for this ticket"):
    try:
        rows = api.ticket_audit(t["id"])
    except api.ApiError as err:
        st.error(str(err))
        rows = []
    if rows:
        st.dataframe(pd.DataFrame([{
            "When (UTC)": r["created_at"][:16].replace("T", " "),
            "What": r["feature"].replace("_", " "),
            "By": r["actor"] or r["method"],
            "AI used": "yes" if r["llm_used"] else "no",
            "Guardrails": ", ".join(r["guardrails"]) or "-",
            "Personal data masked": ", ".join(f"{k} ×{v}" for k, v in r["pii_found"].items()) or "-",
            "Note": r["fallback_reason"] or "",
        } for r in rows]), hide_index=True, width="stretch")
    else:
        st.write("No AI decisions recorded for this ticket (e.g. demo history).")

with st.expander("🔒 Privacy (POPIA)"):
    st.caption("Removes the parent's name and contact details and masks ID numbers, phone numbers and "
               "emails in the message. The ticket stays for statistics. This cannot be undone.")
    confirm = st.checkbox("I confirm the parent asked for their personal data to be removed", key=f"anon_{t['id']}")
    if st.button("Anonymise this ticket", disabled=not (confirm and staff_name), key=f"anonb_{t['id']}"):
        try:
            out = api.anonymise(t["id"], staff_name)
        except api.ApiError as err:
            st.error(str(err))
        else:
            st.success("Personal data removed: " + (", ".join(out["removed"]) or "nothing found"))

