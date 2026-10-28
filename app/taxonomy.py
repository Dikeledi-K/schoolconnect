"""The SINGLE source of truth for how SchoolConnect understands messages.

Everything else (classifier, LLM prompt, API, frontend dropdowns) reads from here.
To add a category or keyword, change this file only.

How keywords are matched (see app/classifier/rules.py)
--------------------------------------------------------
* Text is lower-cased and apostrophes are removed, so "Didn't" == "didnt".
* Keywords are grouped by language because languages build words differently:
  - English / Afrikaans / Sesotho ("en", "af", "st"):
      keywords of 5+ characters match at the START of a word, so "payment"
      also matches "payments". Shorter keywords must match a WHOLE word
      (plural "s" allowed), so "app" does not match "apply" and "bus" does
      not match "business".
  - isiZulu / isiXhosa ("zu", "xh"):
      these languages attach small words to the FRONT of nouns
      ("nothisha" = "with the teacher", "ngemali" = "with money"), so their
      keywords are written as STEMS and match anywhere inside a word.
* Non-English terms should be reviewed by a first-language speaker
  (see docs/DATA.md, "Known limitations").
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Languages whose keywords are stems matched anywhere inside a word.
CONJUNCTIVE_LANGUAGES: set[str] = {"zu", "xh"}

# --------------------------------------------------------------------------
# Staff roles: who a ticket is routed to
# --------------------------------------------------------------------------
STAFF_ROLES: dict[str, str] = {
    "admin_clerk": "Admin Clerk",
    "finance_clerk": "Finance Clerk",
    "class_teacher": "Class Teacher",
    "deputy_principal": "Deputy Principal",
    "it_support": "IT Support",
}

# Week 7: staff ACCOUNTS can also be the principal. The principal is not a routing role
# (no category is routed there and the Week 5 workload model ignores it), but tickets
# escalate to the principal and the principal sees everything.
PRINCIPAL_ROLE = "principal"
ACCOUNT_ROLES: dict[str, str] = {**STAFF_ROLES, PRINCIPAL_ROLE: "Principal"}

# Least privilege (POPIA): only these roles may see learner-welfare tickets,
# the forecast and the risk & compliance pages.
SENIOR_ROLES: tuple[str, ...] = ("deputy_principal", PRINCIPAL_ROLE)


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Category:
    code: str
    display_name: str
    description: str
    routed_role: str
    # Keywords grouped by language code: {"en": [...], "zu": [...], ...}
    keywords: dict[str, list[str]] = field(default_factory=dict)


CATEGORIES: dict[str, Category] = {
    "admissions": Category(
        code="admissions",
        display_name="Admissions & Enrolment",
        description="Applying for a place, registration, transfers, waiting lists, Grade R / Grade 1 / Grade 8 intake.",
        routed_role="admin_clerk",
        keywords={
            "en": ["admission", "apply", "applying", "application", "applied", "enrol",
                   "enroll", "register", "registration", "waiting list", "space for",
                   "place for", "transfer", "new learner", "grade r", "birth certificate",
                   "proof of residence", "accepted", "placement", "placed", "intake",
                   "feeder zone", "appeal", "rejected", "certified copies"],
            "zu": ["bhalisa", "faka isicelo", "isicelo", "indawo yengane", "amukelwe",
                   "dlulisela"],
            "st": ["ngodisa", "ngodiso", "kopo", "sebaka sa ngwana", "kopa sebaka",
                   "amohelwa"],
            "af": ["aansoek", "inskrywing", "inskryf", "registreer", "toelating",
                   "waglys", "oorplasing", "plek vir"],
            "xh": ["bhalisa", "sicelo"],
        },
    ),
    "fees_exemptions": Category(
        code="fees_exemptions",
        display_name="Fees & Exemptions",
        description="School fees, statements, payments, fee exemptions, debit orders, refunds.",
        routed_role="finance_clerk",
        keywords={
            "en": ["fee", "fees", "school fees", "statement", "invoice", "payment",
                   "paid", "pay", "exemption", "exempt", "afford", "debit order",
                   "refund", "receipt", "owe", "outstanding", "balance", "arrears",
                   "eft", "proof of payment", "deposit", "bank account",
                   "banking details", "installment", "instalment", "discount",
                   "no-fee", "finance"],
            "zu": ["mali", "khokha", "khokhile", "sitatimende", "khululwa", "risidi"],
            "st": ["tjhelete", "chelete", "lefa", "lefile", "ditefello", "tefello",
                   "kolota"],
            "af": ["skoolgeld", "fooie", "betaal", "betaling", "vrystelling", "staat",
                   "rekening", "terugbetaling", "kwitansie", "debietorder",
                   "agterstallig"],
            "xh": ["mali", "ntlawulo", "hlawul"],
        },
    ),
    "academic": Category(
        code="academic",
        display_name="Academic & Reports",
        description="Marks, report cards, homework, tests and exams, subject choices, extra lessons, progress.",
        routed_role="class_teacher",
        keywords={
            "en": ["report card", "report", "marks", "mark", "results", "homework",
                   "assignment", "test", "exam", "subject", "maths", "mathematics",
                   "science", "teacher meeting", "parent meeting", "progress", "failing",
                   "failed", "repeat the grade", "promoted", "extra lessons", "tutor",
                   "project", "textbook", "stationery", "curriculum", "sba",
                   "subject choice", "reading", "struggling with", "matric",
                   "timetable", "condonation"],
            "zu": ["mbiko", "phumel", "msebenzi wesikole", "sebenzi wasekhaya",
                   "sivivinyo", "thisha", "zifundo", "zimpawu"],
            "st": ["dipalo", "sephetho", "mosebetsi wa sekolo", "mosebetsi wa lapeng",
                   "teko", "titjhere", "tichere", "dithuto", "ditlhahlobo"],
            "af": ["rapport", "punte", "huiswerk", "toets", "eksamen", "vak", "vakke",
                   "wiskunde", "onderwyser", "juffrou", "meneer", "vordering", "druip",
                   "projek", "handboek", "ouerdag"],
            "xh": ["ziphumo", "sebenzi wasekhaya", "vavanyo", "titshala"],
        },
    ),
    "learner_welfare": Category(
        code="learner_welfare",
        display_name="Learner Welfare & Safety",
        description="Bullying, abuse, injury, illness, missing learners, threats, emotional wellbeing. ALWAYS human-handled.",
        routed_role="deputy_principal",
        keywords={
            "en": ["bully", "bullied", "bullying", "abuse", "abused", "hit", "beaten",
                   "beat him", "beat her", "hurt", "hurting", "injured", "injury",
                   "bleeding", "bruise", "fight", "fighting", "threat", "unsafe",
                   "scared", "is missing", "went missing", "didnt come home",
                   "not come home", "crying", "depressed", "suicide", "self harm",
                   "harass", "touched", "inappropriate", "drugs", "weapon", "knife",
                   "gun", "hospital", "clinic", "assault", "teased", "mocked"],
            "zu": ["hlukunyezwa", "shaywa", "mshaya", "shayiwe", "limele", "lahlekile",
                   "buyanga", "sabekile", "yesaba", "yagula", "sibhedlela",
                   "dlwengulwa", "hlukumeza", "zibulala"],
            "st": ["shapuwa", "ba mo shapa", "o lemetse", "o tswile kotsi",
                   "o lahlehile", "ha a kgutla", "o tshaba", "o a kula", "sepetlele",
                   "hlekefetsa", "hlekefetswa", "tshosa"],
            "af": ["geboelie", "boelie", "afgeknou", "mishandel", "geslaan",
                   "seergemaak", "beseer", "vermis", "nie huis toe gekom", "bang",
                   "dreig", "hospitaal", "aangerand", "gespot", "dwelms", "mes"],
            "xh": ["bethwa", "bethwe", "nzakele", "lahlekile", "yoyika", "yagula",
                   "xhatshazwa", "zibulala"],
        },
    ),
    "transport": Category(
        code="transport",
        display_name="Transport",
        description="Scholar transport, school bus, taxis, pick-up and drop-off, late arrivals due to transport.",
        routed_role="admin_clerk",
        keywords={
            "en": ["transport", "bus", "scholar transport", "taxi", "driver", "pick up",
                   "pickup", "pick-up", "drop off", "drop-off", "route", "lift club",
                   "bus stop", "kombi", "speeding", "traffic"],
            "zu": ["bhasi", "tekisi", "mshayeli"],
            "st": ["bese", "beseng", "mokganni", "dipalangwang", "palangwang"],
            "af": ["vervoer", "skoolbus", "bus", "bestuurder", "oplaai", "aflaai",
                   "roete", "afhaal"],
            "xh": ["bhasi", "teksi", "mqhubi", "thutho"],
        },
    ),
    "it_portal": Category(
        code="it_portal",
        display_name="IT & School Portal",
        description="School portal / app login, passwords, D6/SA-SAMS communicator, online learning platforms.",
        routed_role="it_support",
        keywords={
            "en": ["portal", "login", "log in", "logon", "password", "username",
                   "otp", "app", "website", "online", "d6", "communicator",
                   "email address", "link", "wifi", "google classroom", "teams",
                   "locked out", "reset", "not loading", "not working", "error",
                   "notifications", "profile", "bounced"],
            "zu": ["phasiwedi", "ayingeni", "ayivuli", "i-app"],
            "st": ["phasewete", "ho kena", "ha e bule", "ha e kene"],
            "af": ["wagwoord", "aanmeld", "inteken", "webwerf", "toep", "e-pos",
                   "werk nie", "foutboodskap"],
            "xh": ["phasiwedi"],
        },
    ),
    "other": Category(
        code="other",
        display_name="Other / General",
        description="Anything that does not fit another category: uniforms, events, general enquiries, compliments.",
        routed_role="admin_clerk",
        keywords={
            "en": ["uniform", "blazer", "event", "sports day", "concert", "trip",
                   "excursion", "lost property", "school hours", "office hours",
                   "thank you to", "thanks to", "compliment", "complaint", "tuck shop",
                   "volunteer", "sgb meeting", "photos", "closing early",
                   "long weekend", "toilets", "gate"],
            "zu": ["yunifomu", "mcimbi"],
            "st": ["junifomo", "moketjana"],
            "af": ["skooldrag", "uniform", "funksie", "uitstappie", "afskeid"],
            "xh": ["yunifomu"],
        },
    ),
}

DEFAULT_CATEGORY = "other"
WELFARE_CATEGORY = "learner_welfare"

# When two categories score the same, the one listed first wins.
# Welfare comes first: if in doubt, treat it as a safety matter.
CATEGORY_TIE_BREAK_ORDER: list[str] = [
    "learner_welfare", "fees_exemptions", "admissions", "academic",
    "transport", "it_portal", "other",
]


# --------------------------------------------------------------------------
# Urgency (ordered from lowest to highest)
# --------------------------------------------------------------------------
URGENCY_LEVELS: list[str] = ["low", "medium", "high", "critical"]

URGENCY_DESCRIPTIONS: dict[str, str] = {
    "low": "General enquiry, no deadline.",
    "medium": "Needs an answer soon (default for most requests).",
    "high": "Time-sensitive or affects a learner's wellbeing; same-day attention.",
    "critical": "A child may be in danger. Immediate human action.",
}


def urgency_rank(level: str) -> int:
    """Return 0..3 so urgencies can be compared (higher = more urgent)."""
    return URGENCY_LEVELS.index(level)


def max_urgency(a: str, b: str) -> str:
    """Return the more urgent of two levels. Guardrails use this so they can only RAISE urgency."""
    return a if urgency_rank(a) >= urgency_rank(b) else b


# Words that push a normal message up to "high" (deadlines, time pressure).
HIGH_URGENCY_WORDS: dict[str, list[str]] = {
    "en": ["urgent", "urgently", "asap", "emergency", "today", "immediately",
           "deadline", "tomorrow", "closing date", "last day", "final notice",
           "suspended", "blocked"],
    "zu": ["ngokushesha", "namhlanje", "phuthuma"],
    "st": ["kajeno", "hang-hang", "potlako"],
    "af": ["dringend", "vandag", "noodgeval", "onmiddellik"],
    "xh": ["ngokukhawuleza", "namhlanje"],
}

# Words that suggest a relaxed, low-urgency enquiry.
LOW_URGENCY_WORDS: dict[str, list[str]] = {
    "en": ["just wondering", "when you have time", "no rush", "general question",
           "next year", "next term", "thank you to", "compliment"],
    "zu": ["nyaka ozayo"],
    "st": ["selemong se tlang"],
    "af": ["volgende jaar", "volgende kwartaal"],
    "xh": ["nyaka ozayo"],
}


# --------------------------------------------------------------------------
# Safety keywords: the child-safety guardrail
# --------------------------------------------------------------------------
# CRITICAL: a child may be in immediate danger.
SAFETY_CRITICAL_KEYWORDS: dict[str, list[str]] = {
    "en": ["abuse", "abused", "abusing", "sexual", "rape", "raped", "molest",
           "touched her", "touched him", "touching her", "touching him",
           "hurting her", "hurting him", "suicide", "kill himself", "kill herself",
           "kill myself", "self harm", "self-harm", "cutting herself",
           "cutting himself", "is missing", "went missing", "gone missing",
           "missing since", "didnt come home", "did not come home", "not come home",
           "hasnt come home", "has not come home", "kidnap", "abducted", "weapon",
           "knife", "gun", "stabbed", "unconscious", "threatened to kill",
           "wants to kill", "going to kill"],
    "zu": ["dlwengulwa", "lahlekile", "akabuyanga", "zibulala", "mmese", "sibhamu"],
    "st": ["o lahlehile", "ha a kgutla", "ha a so kgutle", "ho ipolaya", "thipa",
           "sethunya"],
    "af": ["mishandel", "verkrag", "vermis", "nie huis toe gekom", "selfmoord",
           "mes", "vuurwapen"],
    "xh": ["lahlekile", "zibulala", "mmese", "dlwenguliwe"],
}

# HIGH: wellbeing concern that a person must handle the same day.
SAFETY_HIGH_KEYWORDS: dict[str, list[str]] = {
    "en": ["bully", "bullied", "bullying", "hit", "beaten", "beat him", "beat her",
           "hurt", "hurting", "injured", "injury", "bleeding", "bruise", "fight",
           "fighting", "threat", "unsafe", "scared", "harass", "inappropriate",
           "drugs", "assault", "depressed", "hospital", "teased", "mocked", "slapped"],
    "zu": ["hlukunyezwa", "shaywa", "mshaya", "shayiwe", "limele", "yesaba",
           "sabekile", "hlukumeza"],
    "st": ["shapuwa", "ba mo shapa", "o lemetse", "o tshaba", "tshosa", "hlekefetsa"],
    "af": ["geboelie", "boelie", "afgeknou", "geslaan", "seergemaak", "beseer",
           "dreig", "aangerand", "gespot", "bang", "dwelms"],
    "xh": ["bethwa", "bethwe", "nzakele", "yoyika", "xhatshazwa"],
}


# --------------------------------------------------------------------------
# Languages
# --------------------------------------------------------------------------
LANGUAGES: dict[str, str] = {
    "en": "English",
    "zu": "isiZulu",
    "st": "Sesotho",
    "af": "Afrikaans",
    "xh": "isiXhosa",
    "unknown": "Unknown",
}

# Common everyday words used ONLY for language detection (not for topics).
LANGUAGE_MARKERS: dict[str, list[str]] = {
    "en": ["the", "and", "is", "my", "please", "pls", "plz", "school", "child",
           "when", "what", "how", "can", "i", "you", "for", "with", "have", "not",
           "this", "to", "of", "it", "we", "our", "son", "daughter", "do", "does",
           "there", "hi", "hello", "good", "where", "who", "why", "he", "she"],
    "zu": ["ngicela", "sawubona", "ngiyabonga", "ingane", "yami", "wami", "kodwa",
           "ukuthi", "angikwazi", "kanjani", "sikole", "manje", "ngifuna", "akukho",
           "yini", "ngoba", "futhi", "kakhulu", "ngizwe", "kusukela", "izolo",
           "namhlanje", "usizo", "ngakhokha", "ngafaka"],
    "st": ["dumela", "ke kopa", "kopa", "ngwana", "ngwanaka", "hore", "empa",
           "sekolong", "sekolo", "jwang", "hobane", "hape", "haholo", "ke batla",
           "ha ke", "ya ka", "wa ka", "kajeno", "rona", "lona", "ntate", "mme",
           "ke a leboha", "ho", "ka", "ke", "tsa", "ba", "neng"],
    "af": ["die", "en", "nie", "my", "kind", "asseblief", "skool", "dankie", "hoe",
           "wat", "ek", "is", "het", "van", "vir", "kan", "seun", "dogter", "goeie",
           "ons", "graag", "weer", "hoekom", "wanneer", "daar", "met", "n", "wil",
           "moet", "kry", "op"],
    "xh": ["molo", "ndicela", "enkosi", "umntwana", "ukuba", "andikwazi", "njani",
           "sikolo", "sikolw", "ngoku", "ndifuna", "ndiyabulela", "uncedo",
           "nithethe", "ndihlawule", "zomntwana"],
}


# --------------------------------------------------------------------------
# Ticket statuses
# --------------------------------------------------------------------------
STATUSES: list[str] = ["new", "in_progress", "resolved"]

STATUS_LABELS: dict[str, str] = {
    "new": "New",
    "in_progress": "In progress",
    "resolved": "Resolved",
}

# Grades a parent can pick (optional on a ticket). Used by fairness checks later.
GRADES: list[str] = ["R", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]


def taxonomy_as_dict() -> dict:
    """Serialise the taxonomy for the GET /taxonomy endpoint and the frontend.

    Keywords are deliberately NOT included: the frontend doesn't need them.
    """
    return {
        "categories": [
            {
                "code": c.code,
                "display_name": c.display_name,
                "description": c.description,
                "routed_role": c.routed_role,
                "routed_role_name": STAFF_ROLES[c.routed_role],
            }
            for c in CATEGORIES.values()
        ],
        "urgency_levels": [
            {"code": u, "description": URGENCY_DESCRIPTIONS[u]} for u in URGENCY_LEVELS
        ],
        "languages": [{"code": k, "name": v} for k, v in LANGUAGES.items()],
        "statuses": [{"code": s, "label": STATUS_LABELS[s]} for s in STATUSES],
        "staff_roles": [{"code": k, "name": v} for k, v in STAFF_ROLES.items()],
        "account_roles": [{"code": k, "name": v} for k, v in ACCOUNT_ROLES.items()],
        "grades": GRADES,
    }


# --------------------------------------------------------------------------
# Weeks 3-4: departments for analytics and weekly reports.
# A department = the staff role that a set of categories is routed to, so this follows
# CATEGORIES automatically. "school" is the whole school (principal / SGB report).
# --------------------------------------------------------------------------
SCHOOL_SCOPE = "school"
DEPARTMENT_NAMES: dict[str, str] = {
    SCHOOL_SCOPE: "Whole school (Principal & SGB)",
    "admin_clerk": "Admin office",
    "finance_clerk": "Finance office",
    "class_teacher": "Teaching staff (academic)",
    "deputy_principal": "Learner welfare (Deputy Principal)",
    "it_support": "IT support",
}


def categories_for_department(scope: str) -> list[str]:
    """Categories in a department's report. The whole school gets every category."""
    if scope == SCHOOL_SCOPE:
        return list(CATEGORIES)
    if scope not in STAFF_ROLES:
        raise ValueError(f"Unknown department '{scope}'")
    return [code for code, c in CATEGORIES.items() if c.routed_role == scope]

