"""SchoolConnect - Overview page (the Streamlit entry point).

Run:  streamlit run frontend/Home.py
"""

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="SchoolConnect", page_icon="🏫", layout="wide")

st.title("🏫 SchoolConnect")
st.caption("AI help desk for South African public schools")

st.markdown(
    "Parents send a message in English, isiZulu, Sesotho, Afrikaans or isiXhosa. "
    "SchoolConnect works out what it is about, how urgent it is, and which staff "
    "member should handle it."
)
st.page_link("pages/1_Send_a_message.py", label="Parents: send a message", icon="✉️")
st.page_link("pages/2_Staff_inbox.py", label="Staff: open the inbox", icon="📥")
st.page_link("pages/3_Forecast_and_workload.py", label="Principal: forecast & staff workload", icon="📈")
st.page_link("pages/4_Risk_and_compliance.py", label="Principal: AI risk & compliance (POPIA)", icon="🛡️")

st.divider()
st.subheader("Overview")

try:
    health = api.health()
    stats = api.stats()
    taxonomy = api.taxonomy()
except api.ApiError as err:
    st.error(str(err))
    st.info("Start the API with:  uvicorn app.main:app --reload")
    st.stop()

open_count = stats["by_status"]["new"] + stats["by_status"]["in_progress"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total tickets", stats["total"])
c2.metric("Open tickets", open_count)
c3.metric("Open critical", stats["open_critical"])
c4.metric("AI mode", health["llm_provider"])

if stats["open_critical"]:
    st.error(f"{stats['open_critical']} critical ticket(s) still open. Check the staff inbox.")

if stats["total"] == 0:
    st.info("No tickets yet. Send a message, or load demo data with:  python scripts/seed_db.py")
    st.stop()

names = {c["code"]: c["display_name"] for c in taxonomy["categories"]}
languages = {lang["code"]: lang["name"] for lang in taxonomy["languages"]}

left, right = st.columns(2)
with left:
    st.markdown("**Tickets by category**")
    by_cat = pd.DataFrame(
        {"Tickets": [stats["by_category"][c] for c in names]}, index=[names[c] for c in names]
    )
    st.bar_chart(by_cat, horizontal=True)
with right:
    st.markdown("**Tickets by urgency**")
    st.bar_chart(pd.DataFrame({"Tickets": stats["by_urgency"]}))

st.markdown("**Tickets by language**")
st.bar_chart(pd.DataFrame(
    {"Tickets": {languages[k]: v for k, v in stats["by_language"].items() if v}}
))
