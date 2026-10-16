"""Knowledge-base taxonomy aligned with cybercrime.gov.in / NCRP.

Collections are fixed at the code level — the LLM cannot create or rename them.
Incident categories mirror the portal complaint tree.
"""

from __future__ import annotations

# --- Collections (one tool per collection, hardcoded in worker.py) ---

COLLECTION_INCIDENT_PLAYBOOK = "incident_playbook"
COLLECTION_PORTAL_GUIDE = "portal_guide"
COLLECTION_PREVENTION = "prevention"
COLLECTION_REASSURANCE = "reassurance"
COLLECTION_RESOURCES = "resources"
COLLECTION_AGENT_BOUNDS = "agent_bounds"

COLLECTIONS: frozenset[str] = frozenset(
    {
        COLLECTION_INCIDENT_PLAYBOOK,
        COLLECTION_PORTAL_GUIDE,
        COLLECTION_PREVENTION,
        COLLECTION_REASSURANCE,
        COLLECTION_RESOURCES,
        COLLECTION_AGENT_BOUNDS,
    }
)

COLLECTION_LABELS: dict[str, str] = {
    COLLECTION_INCIDENT_PLAYBOOK: "Incident playbook — what to do after a crime",
    COLLECTION_PORTAL_GUIDE: "Portal guide — cybercrime.gov.in filing & tracking",
    COLLECTION_PREVENTION: "Prevention — safety tips & FAQs",
    COLLECTION_REASSURANCE: "Reassurance — calm, factual context by crime type",
    COLLECTION_RESOURCES: "Resources — helplines, manuals, official links",
    COLLECTION_AGENT_BOUNDS: "Agent bounds — what the desk may and may not say",
}

# --- Incident categories (portal complaint sub-types) ---

CATEGORY_FINANCIAL_FRAUD = "financial_fraud"
CATEGORY_UPI_FRAUD = "upi_fraud"
CATEGORY_DIGITAL_ARREST = "digital_arrest"
CATEGORY_SEXTORTION = "sextortion"
CATEGORY_CSEAM_RGR = "cseam_rgr"
CATEGORY_IMPERSONATION = "impersonation"
CATEGORY_SOCIAL_MEDIA = "social_media"
CATEGORY_RANSOMWARE = "ransomware"
CATEGORY_HACKING = "hacking"
CATEGORY_CRYPTO = "cryptocurrency"
CATEGORY_CYBER_BULLYING = "cyber_bullying"
CATEGORY_CYBER_STALKING = "cyber_stalking"
CATEGORY_ONLINE_GAMBLING = "online_gambling"
CATEGORY_TRAFFICKING = "cyber_trafficking"
CATEGORY_OTHER = "other"

INCIDENT_CATEGORIES: frozenset[str] = frozenset(
    {
        CATEGORY_FINANCIAL_FRAUD,
        CATEGORY_UPI_FRAUD,
        CATEGORY_DIGITAL_ARREST,
        CATEGORY_SEXTORTION,
        CATEGORY_CSEAM_RGR,
        CATEGORY_IMPERSONATION,
        CATEGORY_SOCIAL_MEDIA,
        CATEGORY_RANSOMWARE,
        CATEGORY_HACKING,
        CATEGORY_CRYPTO,
        CATEGORY_CYBER_BULLYING,
        CATEGORY_CYBER_STALKING,
        CATEGORY_ONLINE_GAMBLING,
        CATEGORY_TRAFFICKING,
        CATEGORY_OTHER,
    }
)

INCIDENT_CATEGORY_LABELS: dict[str, str] = {
    CATEGORY_FINANCIAL_FRAUD: "Online financial fraud (general)",
    CATEGORY_UPI_FRAUD: "UPI / payment-app fraud",
    CATEGORY_DIGITAL_ARREST: "Digital arrest / impersonation of police",
    CATEGORY_SEXTORTION: "Sextortion / blackmail with intimate images",
    CATEGORY_CSEAM_RGR: "Women/child — CSEAM or RGR content",
    CATEGORY_IMPERSONATION: "Impersonation / fake profiles",
    CATEGORY_SOCIAL_MEDIA: "Social media abuse or fraud",
    CATEGORY_RANSOMWARE: "Ransomware / locked files",
    CATEGORY_HACKING: "Hacking / unauthorized access",
    CATEGORY_CRYPTO: "Cryptocurrency fraud",
    CATEGORY_CYBER_BULLYING: "Cyber bullying",
    CATEGORY_CYBER_STALKING: "Cyber stalking / harassment",
    CATEGORY_ONLINE_GAMBLING: "Online gambling fraud",
    CATEGORY_TRAFFICKING: "Online cyber trafficking",
    CATEGORY_OTHER: "Other cybercrime",
}

# Portal top-level tracks (for routing in the call script)
PORTAL_TRACK_WOMEN_CHILD = "women_child"
PORTAL_TRACK_OTHER = "other_cybercrime"

PORTAL_TRACKS: frozenset[str] = frozenset({PORTAL_TRACK_WOMEN_CHILD, PORTAL_TRACK_OTHER})

MAX_QUERY_LENGTH = 400
