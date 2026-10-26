"""Week 6 page for the principal / information officer: is the AI safe, fair and POPIA-compliant?"""

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Risk & compliance - SchoolConnect", page_icon="🛡️", layout="wide")
st.title("🛡️ Risk & compliance")
st.caption("What did the AI decide, did people correct it, is every group of parents treated fairly, "
           "and is personal data protected? Counts only: no names or messages on this page.")

days = st.select_slider("Period", options=[7, 30, 90, 365], value=30, format_func=lambda d: f"Last {d} days")

try:
    s = api.risk_summary(days)
except api.ApiError as err:
    st.error(str(err))
    st.stop()

ai, inc, rep, inj, fair = s["ai_decisions"], s["incidents"], s["replies"], s["prompt_injection"], s["fairness"]

# ---- Headline tiles --------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Messages", inc["tickets"])
k1.caption(f"{inc['critical']} critical · {inc['safety_flagged']} safety-flagged")
k2.metric("Injection checks", f"{inj['passed']}/{inj['checks']}")
k2.caption("all passed" if inj["passed"] == inj["checks"] else "⚠ some failed")
k3.metric("Staff corrections", s["human_overrides"]["count"])
k3.caption(f"{rep['edited_before_approval']} of {rep['approved']} approved replies edited")
k4.metric("Fairness flags", len(fair["flags"]))
k4.caption("no gaps found" if not fair["flags"] else "see below")
k5.metric("Due for anonymising", s["retention"]["tickets_due_for_anonymising"])
k5.caption("resolved tickets past retention")

if inc["critical_still_new_after_1h"]:
    st.error(f"🚨 {inc['critical_still_new_after_1h']} critical ticket(s) still 'new' after more than an hour.")
for flag in fair["flags"]:
    st.warning(f"⚖️ Fairness gap: {flag}")

try:
    pdf = api.risk_report_pdf(days)
    st.download_button("⬇️ Download the risk evaluation report (PDF)", pdf,
                       file_name="schoolconnect-risk-report.pdf", mime="application/pdf", type="primary")
except api.ApiError as err:
    st.error(str(err))

# ---- AI decisions and safeguards ------------------------------------------
st.subheader("AI decisions and safeguards")
left, mid, right = st.columns(3)
with left:
    st.markdown("**Decisions**")
    st.dataframe(pd.DataFrame([
        ("Messages classified", ai["classifications"]),
        ("…by an external AI", ai["classified_by_ai"]),
        ("…AI failed, rules used", ai["ai_fallbacks_to_rules"]),
        ("Reply drafts", ai["reply_drafts"]),
        ("…written by an AI", ai["reply_drafts_by_ai"]),
        ("…AI reply rejected (invented facts)", ai["ai_replies_rejected"]),
        ("Acknowledgement-only replies", rep["acknowledgement_only"]),
    ], columns=["Measure", "Count"]), hide_index=True, width="stretch")
with mid:
    st.markdown("**Safety guardrails fired**")
    g = s["guardrails_fired"]
    st.dataframe(pd.DataFrame(sorted(g.items()), columns=["Guardrail", "Times"]) if g
                 else pd.DataFrame({"Guardrail": ["none"], "Times": [0]}), hide_index=True, width="stretch")
with right:
    st.markdown("**Personal data masked before any AI**")
    p = s["pii_masked"]
    st.dataframe(pd.DataFrame([(k.replace("_", " "), v) for k, v in sorted(p.items())], columns=["Type", "Count"])
                 if p else pd.DataFrame({"Type": ["none found"], "Count": [0]}), hide_index=True, width="stretch")

# ---- Human overrides -------------------------------------------------------
st.subheader("Staff corrections of the AI")
recent = s["human_overrides"]["recent"]
if recent:
    st.dataframe(pd.DataFrame([{
        "When (UTC)": o["when"].replace("T", " "), "Ticket": o["ticket_id"], "By": o["by"],
        "Before": f"{o['before']['category']} / {o['before']['urgency']}",
        "After": f"{o['after']['category']} / {o['after']['urgency']}",
        "Reason": o["reason"], "Guardrail kept it safe": ", ".join(o["guardrails"]) or "-",
    } for o in reversed(recent)]), hide_index=True, width="stretch")
else:
    st.write("No corrections in this period.")

# ---- Fairness --------------------------------------------------------------
st.subheader("⚖️ Fairness by language and grade")
th = fair["thresholds"]
st.caption(f"A group is flagged if its accuracy is more than {th['accuracy_gap']:.0%} below overall, it waits "
           f"{th['wait_ratio']}× the overall median or longer, or staff correct it more than "
           f"{th['override_gap']:.0%} more often. Small groups are shown but not judged.")


def fairness_table(section: dict, metric: str, fmt) -> pd.DataFrame:
    rows = []
    for dimension, label in (("by_language", "Language"), ("by_grade", "Grade band")):
        for g in section[dimension]:
            result = "🔴 flagged" if g["flagged"] else ("too few to judge" if g["too_small"] else "✅ ok")
            rows.append({"Breakdown": label, "Group": g["group"], "n": g["n"], "Value": fmt(g[metric]),
                         "Result": result})
    return pd.DataFrame(rows)


t1, t2, t3 = st.tabs(["Classifier accuracy", "Waiting time", "Staff corrections"])
with t1:
    c = fair["classifier"]
    st.caption(f"Rules classifier on {c['messages']} labelled sample messages · overall {c['overall_accuracy']:.0%}")
    st.dataframe(fairness_table(c, "accuracy", lambda v: f"{v:.0%}"), hide_index=True, width="stretch")
with t2:
    sv = fair["service"]
    st.caption(f"Median hours from message to resolution · {sv['resolved_tickets']} resolved tickets · "
               f"overall {sv['overall_median_hours']} h")
    st.dataframe(fairness_table(sv, "median_hours", lambda v: f"{v} h"), hide_index=True, width="stretch")
with t3:
    ov = fair["overrides"]
    st.caption(f"Share of AI-classified tickets corrected by staff · {ov['classified_tickets']} tickets · "
               f"overall {ov['overall_override_rate']:.0%}")
    st.dataframe(fairness_table(ov, "override_rate", lambda v: f"{v:.0%}"), hide_index=True, width="stretch")

# ---- Prompt injection ------------------------------------------------------
st.subheader("🧪 Prompt-injection suite")
st.caption("Attacks hidden in parent messages, tested against the rules, against an AI that fully obeyed the "
           "attack, and against the reply fact-check. Run live every time this page loads.")
st.dataframe(pd.DataFrame([{"Case": r["id"], "Attack": r["attack"], "Layer": r["layer"],
                            "Result": "✅ pass" if r["passed"] else "❌ " + r["detail"]}
                           for r in inj["results"]]), hide_index=True, width="stretch")

# ---- Risk register ---------------------------------------------------------
st.subheader("📋 Risk register")
st.caption("From config/risk_register.yaml, reviewed each term by the principal / information officer.")
st.dataframe(pd.DataFrame([{"ID": r["id"], "Risk": r["risk"], "Likelihood": r["likelihood"], "Impact": r["impact"],
                            "Mitigation": r["mitigation"], "Status": r["status"], "Owner": r["owner"]}
                           for r in s["risk_register"]]), hide_index=True, width="stretch")
