"""Parent page: send a message and check progress with a reference number."""

import streamlit as st

import api_client as api
import ui


URGENCY_BADGE = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🟠 High", "critical": "🔴 Critical"}

ui.page("Send a message to the school",
        "Write in any language you are comfortable with: English, isiZulu, Sesotho, "
        "Afrikaans or isiXhosa. You will get a reference number to track your message.",
        "✉️", layout="centered")
st.warning(
    "If a child is in immediate danger, do not wait for a reply: call **10111** (SAPS) "
    "or **112** from a cellphone."
)

try:
    grades = [""] + api.taxonomy()["grades"]
except api.ApiError:
    grades = [""]

with st.form("send_message", clear_on_submit=True):
    message = st.text_area("Your message *", max_chars=4000, height=150,
                           placeholder="e.g. My son's report card is missing his maths mark")
    col1, col2, col3 = st.columns(3)
    name = col1.text_input("Your name (optional)", max_chars=120)
    contact = col2.text_input("Phone or email (optional)", max_chars=120)
    grade = col3.selectbox("Learner's grade (optional)", grades,
                           format_func=lambda g: g and f"Grade {g}" or "-")
    st.caption("Your name and contact details are only seen by school staff. "
               "They are never shared with an AI service.")
    submitted = st.form_submit_button("Send message", type="primary")

if submitted:
    if not message.strip():
        st.error("Please type a message first.")
    else:
        try:
            with st.spinner("Sending..."):
                result = api.create_ticket(message, name, contact, grade)
        except api.ApiError as err:
            st.error(str(err))
        else:
            if result["urgency"] == "critical":
                st.error(f"🚨 {result['safety_notice']}")
            st.success(f"Thank you, your message was received. "
                       f"Your reference number is **{result['reference']}**.")
            c1, c2 = st.columns(2)
            c1.metric("Topic", result["category_name"])
            c2.metric("Urgency", URGENCY_BADGE[result["urgency"]])
            if result["needs_human"]:
                st.info("A staff member will personally look at your message.")
            st.caption("Please keep your reference number to check progress below.")

st.divider()
st.subheader("🔎 Check my message")
st.write("Type the reference number you were given (it looks like SC-20261022-0001).")
with st.form("check_reference"):
    reference = st.text_input("Reference number", placeholder="SC-20261022-0001")
    check = st.form_submit_button("Check")

# Plain words for parents. No message text or personal details are ever shown here.
STATUS_WORDS = {
    "new": ("📬", "We have received your message", "A staff member will look at it soon."),
    "in_progress": ("🧑‍💼", "A staff member is working on it", "We will contact you if we need anything else."),
    "resolved": ("✅", "Your message has been dealt with", "If you still need help, send a new message "
                 "and mention this reference number."),
}
REPLY_WORDS = {
    "sent": "✉️ The school has sent you a reply by email.",
    "replied_not_emailed": "📞 The school has prepared a reply. If you gave a phone number, the office will "
                           "contact you; you can also phone the school and quote your reference.",
    "none": "No reply has been sent yet.",
}

if check:
    if not reference.strip():
        st.error("Please type your reference number first.")
    else:
        try:
            ticket = api.ticket_by_reference(reference)
        except api.ApiError:
            st.error("We could not find that reference number. Please check it and try again.")
        else:
            icon, headline, detail = STATUS_WORDS.get(ticket["status"], ("ℹ️", ticket["status"], ""))
            with st.container(border=True):
                st.markdown(f"### {icon} {headline}")
                st.write(detail)
                st.write(REPLY_WORDS.get(ticket.get("reply_status", "none"), ""))
                st.caption(f"Reference {ticket['reference']} · last updated "
                           f"{ticket['updated_at'][:16].replace('T', ' ')} (UTC)")
