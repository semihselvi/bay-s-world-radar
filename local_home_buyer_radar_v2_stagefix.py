from __future__ import annotations

import re

import local_home_buyer_radar_v2_precision as precision
import local_home_buyer_radar_v2 as radar


# Preserve the V2 destination-precision patch and then tighten stage detection.
_ORIGINAL_CLASSIFY_V2 = radar.classify_v2

# Covers transaction-ready equity/finance wording even when a currency amount sits
# between the finance term and "available/present/approved" wording.
READY_FLEX_RE = re.compile(
    r"(?:"
    r"pre[- ]?approved|mortgage\s+(?:approved|agreed)|cash\s+buyer|ready\s+to\s+buy|"
    r"book(?:ed)?\s+(?:a\s+)?viewing|make\s+an\s+offer|"
    r"finanzierungsbestätigung|finanzierung.{0,45}(?:steht|bestätigt|genehmigt|gesichert)|"
    r"eigenkapital.{0,55}(?:vorhanden|verfügbar|verfuegbar|gesichert)|kaufzusage|"
    r"hypotheek.{0,45}(?:akkoord|rond|goedgekeurd)|financiering.{0,45}(?:rond|goedgekeurd)|"
    r"eigen\s+geld.{0,55}(?:beschikbaar|aanwezig)|"
    r"prêt\s+hypothécaire.{0,45}(?:accordé|approuvé)|pret\s+hypothecaire.{0,45}(?:accorde|approuve)|"
    r"financement.{0,45}(?:approuvé|accordé|approuve|accorde)|apport.{0,55}(?:disponible|prêt|pret)|"
    r"hypothek.{0,45}(?:bestätigt|genehmigt|gesichert)"
    r")",
    re.I | re.S,
)


def _active_evidence(requirements: dict) -> int:
    """Count concrete search signals that indicate active house hunting."""
    keys = ("budget", "city", "financing", "timeframe", "bedrooms")
    return sum(1 for key in keys if requirements.get(key))


def classify_v2(profile: str, item: dict):
    lead = _ORIGINAL_CLASSIFY_V2(profile, item)
    if lead is None:
        return None

    text = radar.base.plain(
        f"{item.get('title','')} {item.get('text','')} {item.get('author','')}"
    )
    requirements = dict(lead.get("requirements") or {})
    ready = bool(READY_FLEX_RE.search(text))

    # The base classifier has already verified that this is an actual buyer.
    # If that buyer also provides at least two concrete search constraints, treat
    # them as ACTIVE even when the exact terse-direct-demand regex did not fire.
    stage = lead.get("buyer_stage", "RESEARCH")
    if ready:
        stage = "READY"
    elif stage == "RESEARCH" and _active_evidence(requirements) >= 2:
        stage = "ACTIVE"

    classification = lead.get("classification", "WARM")
    intent = int(lead.get("intent_score") or 0)
    if ready:
        classification = "HOT"
        intent = max(intent, 94)

    return {
        **lead,
        "buyer_stage": stage,
        "classification": classification,
        "intent_score": intent,
        "radar_version": "2.1-stage-readiness-fix",
    }


# Patch the V2 engine so radar.run() uses the corrected classifier.
radar.classify_v2 = classify_v2

# Expose the same public helpers used by tests/workflows.
extract_requirements = radar.extract_requirements
semantic_key = radar.semantic_key
selected_queries = radar.selected_queries


def run():
    return radar.run()


if __name__ == "__main__":
    run()
