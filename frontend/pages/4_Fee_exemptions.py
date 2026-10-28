"""Week 7 page: the fee exemption approval workflow, one queue per step.

    submitted -> finance review -> principal decision -> approved / declined -> parent notified

Buttons only appear for the role allowed to do that step (the API checks again: 403 / 409).
"""

import streamlit as st

import api_client as api
import auth
import ui

ui.page("Fee exemptions", "Fee exemption requests: the finance clerk checks the documents and recommends, "
        "the principal decides, and the parent gets a letter.", "💰", layout="centered")
me = auth.require_login(roles=("finance_clerk", "principal"))
is_finance, is_principal = me["role"] == "finance_clerk", me["role"] == "principal"

try:
    requests_ = api.fee_exemptions()
except api.ApiError as err:
    st.error(str(err))
    st.stop()

QUEUES = [
    ("📨 New", ["submitted"], "Waiting for the finance clerk to start the review."),
    ("🧾 Finance review", ["finance_review"], "The finance clerk ticks off documents and recommends."),
    ("⚖️ Principal", ["principal_decision"], "Waiting for the principal's decision."),
    ("✉️ Tell the parent", ["approved", "declined"], "Decided: send the letter to the parent."),
    ("✅ Done", ["parent_notified"], "The parent has been notified."),
]

if not requests_:
    ui.empty_state("💰", "No fee exemption requests yet",
                   "Start one from a fees ticket in the Staff inbox (open the ticket, then '💰 Fee exemption').")
    st.stop()


def run(action, success: str) -> None:
    try:
        action()
    except api.ApiError as err:
        st.error(str(err))
    else:
        st.toast(success)
        st.rerun()


def card(fe: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{fe['ticket_reference']}** · {fe['status'].replace('_', ' ')}")
        received = [item["received"] for item in fe["checklist"]]
        st.caption(f"Documents: {sum(received)} of {len(received)} received")

        if fe["status"] == "submitted":
            if is_finance:
                if st.button("Start review", key=f"start_{fe['id']}", type="primary"):
                    run(lambda: api.fee_step(fe["id"], "start-review"), "Review started")
            else:
                st.write("Waiting for the finance clerk.")

        elif fe["status"] == "finance_review":
            ticks = [st.checkbox(item["document"], value=item["received"], key=f"doc_{fe['id']}_{i}",
                                 disabled=not is_finance) for i, item in enumerate(fe["checklist"])]
            if is_finance:
                if ticks != received and st.button("Save checklist", key=f"save_{fe['id']}"):
                    run(lambda: api.fee_checklist(fe["id"], ticks), "Checklist saved")
                choice = st.radio("Recommendation", ["approve", "decline"], horizontal=True, key=f"rec_{fe['id']}")
                reason = st.text_input("Reason (needed to recommend a decline)", key=f"rr_{fe['id']}")
                all_in = all(ticks) and ticks == received
                if choice == "approve" and not all_in:
                    st.caption("Tick and save every document before recommending approval.")
                if st.button("Send to the principal", key=f"fin_{fe['id']}", type="primary",
                             disabled=(choice == "approve" and not all_in) or (choice == "decline" and not reason)):
                    run(lambda: api.fee_step(fe["id"], "finance-decision", {"decision": choice, "reason": reason}),
                        "Sent to the principal")
            else:
                st.write("The finance clerk is checking the documents.")

        elif fe["status"] == "principal_decision":
            st.write(f"Finance ({fe['finance_by']}) recommends: **{fe['finance_decision']}**"
                     + (f". Note: {fe['finance_note']}" if fe["finance_note"] else ""))
            if is_principal:
                choice = st.radio("Your decision", ["approve", "decline"], horizontal=True, key=f"dec_{fe['id']}")
                reason = st.text_area("Reason (needed to decline; it is included in the letter to the parent)",
                                      key=f"dr_{fe['id']}")
                if st.button("Confirm decision", key=f"pd_{fe['id']}", type="primary",
                             disabled=choice == "decline" and not reason.strip()):
                    run(lambda: api.fee_step(fe["id"], "principal-decision", {"decision": choice, "reason": reason}),
                        f"Decision recorded: {choice}")
            else:
                st.write("Waiting for the principal.")

        elif fe["status"] in ("approved", "declined"):
            st.write(f"**{fe['status'].title()}** by {fe['principal_by']}"
                     + (f". Reason: {fe['decline_reason']}" if fe["decline_reason"] else ""))
            if st.button("Send the letter to the parent", key=f"notify_{fe['id']}", type="primary"):
                run(lambda: api.fee_step(fe["id"], "notify-parent"), "Letter queued")

        else:
            st.write(f"Finished: **{'approved' if fe['principal_decision'] == 'approve' else 'declined'}**. "
                     "See the ticket's timeline in the Staff inbox for every step.")


tabs = st.tabs([f"{label} ({sum(fe['status'] in states for fe in requests_)})" for label, states, _ in QUEUES])
for tab, (label, states, help_text) in zip(tabs, QUEUES):
    with tab:
        st.caption(help_text)
        rows = [fe for fe in requests_ if fe["status"] in states]
        if not rows:
            st.write("Nothing in this step. 🎉")
        for fe in rows:
            card(fe)
