"""SchoolConnect - Overview page (the Streamlit entry point).

Run:  streamlit run frontend/Home.py
"""

import streamlit as st

import api_client as api
import ui

import auth

ui.page("SchoolConnect", "AI help desk for South African public schools. Parents write in English, "
        "isiZulu, Sesotho, Afrikaans or isiXhosa; we sort, route and track every message.", "🏫")
auth.sidebar()   # shows who is logged in (if anyone) and a logout button

# ---- Where do you want to go? One card per audience ------------------------
st.subheader("Where do you want to go?")
cards = [
    ("For parents", "Ask the school a question, or check on a message with your reference number.",
     [("pages/1_Send_a_message.py", "✉️", "Send a message")]),
    ("For staff (login)", "Your own tickets with their deadlines, and the whole inbox for your role.",
     [("pages/2_My_work.py", "✅", "My work"), ("pages/3_Staff_inbox.py", "📥", "Staff inbox")]),
    ("For finance & principal", "Fee exemption requests: documents, recommendation, decision, letter.",
     [("pages/4_Fee_exemptions.py", "💰", "Fee exemptions")]),
    ("For managers & SGB", "How the week went (volumes, response times, promises kept) and the weekly report.",
     [("pages/6_Analytics.py", "📊", "Analytics"), ("pages/7_Weekly_reports.py", "🗂️", "Weekly reports")]),
    ("For the principal", "Busy periods ahead, and whether the AI is safe, fair and POPIA-compliant.",
     [("pages/8_Forecast_and_workload.py", "📈", "Forecast"), ("pages/9_Risk_and_compliance.py", "🛡️", "Risk")]),
]
# Rows of three, so the buttons have room for their labels.
CARDS_PER_ROW = 3
slots = [col for _ in range(0, len(cards), CARDS_PER_ROW) for col in st.columns(CARDS_PER_ROW)]
for col, (audience, text, links) in zip(slots, cards):
    with col.container(border=True, height="stretch"):
        st.caption(audience.upper())
        for path, icon, label in links:
            st.page_link(path, label=f"**{label}**", icon=icon)
        st.write(text)

# ---- Overview numbers ------------------------------------------------------
st.subheader("Today at a glance")

try:
    health = api.health()
    stats = api.stats()
    taxonomy = api.taxonomy()
except api.ApiError as err:
    st.error(str(err))
    st.info("Start the API with:  uvicorn app.main:app --reload")
    st.stop()

open_count = stats["by_status"]["new"] + stats["by_status"]["in_progress"]
ai_mode = {"rules": "Offline rules"}.get(health["llm_provider"], health["llm_provider"].title())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total tickets", stats["total"])
c2.metric("Open tickets", open_count)
c3.metric("Open critical", stats["open_critical"])
c4.metric("AI mode", ai_mode)

if stats["open_critical"]:
    st.error(f"🚨 **{stats['open_critical']} critical ticket(s) still open.** "
             "Check the staff inbox now.")

if stats["total"] == 0:
    st.info("No tickets yet. Send a message, or load demo data with:  python scripts/seed_db.py")
    st.stop()

names = {c["code"]: c["display_name"] for c in taxonomy["categories"]}
languages = {lang["code"]: lang["name"] for lang in taxonomy["languages"]}
urgencies = [u["code"] for u in taxonomy["urgency_levels"]]

# ---- Charts ---------------------------------------------------------------
left, right = st.columns([3, 2])
with left, st.container(border=True):
    st.markdown("**What are parents asking about?**")
    by_cat = sorted(((names[c], stats["by_category"][c]) for c in names), key=lambda x: -x[1])
    st.plotly_chart(ui.bar_chart([n for n, _ in by_cat], [v for _, v in by_cat], horizontal=True),
                    width="stretch", config={"displayModeBar": False})
with right, st.container(border=True):
    st.markdown("**How urgent are they?**")
    # Urgency keeps its fixed order (low -> critical) and its status colour, with labels on the axis.
    st.plotly_chart(ui.bar_chart([u.title() for u in urgencies],
                                 [stats["by_urgency"].get(u, 0) for u in urgencies],
                                 colours=[ui.URGENCY_COLOUR[u] for u in urgencies]),
                    width="stretch", config={"displayModeBar": False})

with st.container(border=True):
    st.markdown("**Which languages do parents write in?**")
    by_lang = sorted(((languages[k], v) for k, v in stats["by_language"].items() if v), key=lambda x: -x[1])
    st.plotly_chart(ui.bar_chart([n for n, _ in by_lang], [v for _, v in by_lang], height=260),
                    width="stretch", config={"displayModeBar": False})
