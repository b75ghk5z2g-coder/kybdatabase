"""AML screening result evaluation for the client audit (Step 2).
Reads matches produced by AMLIndex (local OpenSanctions-backed index built from
OPENSANCTIONS_FULL / OPENSANCTIONS_PEPS datasets + national sanction lists)
and derives a single audit verdict per screened name.

Risk model (GT 3-tier, gt status.py):
- RED   : confirmed sanction match (is_sanction and score >= 85)
- ORANGE: sanction hit below threshold, PEP, tax debtor, or score 65-84
- GREEN : clean (no match or score < 65)
"""

CRITICAL_PCT = 85   # any is_sanction match >= this -> RED / CRITICAL
HIGH_PCT = 80       # sanction match 80-84 -> HIGH (renders ORANGE in tier layer)
MEDIUM_PCT = 50
LOW_PCT = 30


def evaluate_screening(matches: list) -> dict:
    """Convert AMLIndex match list into {status, risk_pct, source, match_name,
    sanctioned, pep, debtor}.

    LOOKS AT ALL MATCHES (not just the top): if ANY match is a confirmed
    sanction, the whole screening is marked as sanctioned (aligned with
    engine/risk.py and the GT 3-tier model)."""
    if not matches:
        return {"status": "NEGATIVE", "risk_pct": 0, "source": "", "match_name": "",
                "sanctioned": False, "pep": False, "debtor": False}

    top = matches[0]
    top_score = float(top.get("score", 0) or 0)

    # Any sanctioned / PEP / debtor hit anywhere in the candidate list wins over
    # the raw numeric ranking (prevents false negatives from top non-sanction hits).
    sanctioned = any(bool(m.get("is_sanction")) for m in matches)
    pep = any(bool(m.get("is_pep") and not m.get("is_sanction")) for m in matches)
    debtor = any(bool(m.get("is_debtor")) for m in matches)

    best_sanction = next((m for m in matches if m.get("is_sanction")), None)
    best = best_sanction
    if best is None:
        best_pep = next((m for m in matches if m.get("is_pep")), None)
        best = best_pep or top

    score = float(best.get("score", 0) or 0)
    if not score:
        score = top_score
    title = best.get("name", "") or top.get("name", "")
    source = best.get("source", "")

    # Query carried a DOB but a PEP/sanction hit has no birthdate to confirm
    # it is the same person -> same-name, unverifiable. Prevents a false
    # "confirmed PEP MEDIUM" for a namesake (e.g. Ján Hrubý 10.01.1976 vs
    # sk_nrsr_poslanci born 1987-08-14). Sanctions stay hard (never downgrade).
    unverified_dob = any(bool(m.get("dob_unverified")) for m in matches
                         if m.get("is_pep") and not m.get("is_sanction"))

    if sanctioned and score >= CRITICAL_PCT:
        status = "CRITICAL_RISK"   # RED
    elif sanctioned or (not pep and score >= HIGH_PCT):
        status = "HIGH"            # ORANGE (sanction hit < 85 or strong non-sanction)
    elif pep or debtor or score >= MEDIUM_PCT:
        status = "MEDIUM"          # ORANGE
        strong_non_pep = any(not m.get("is_pep") and not m.get("is_sanction")
                             and not m.get("is_debtor")
                             and float(m.get("score", 0) or 0) >= MEDIUM_PCT
                             for m in matches)
        if unverified_dob and pep and not debtor and not strong_non_pep:
            status = "LOW"         # PEP by name only, age not confirmable
    elif score >= LOW_PCT:
        status = "LOW"
    else:
        status = "NEGATIVE"        # GREEN

    return {
        "status": status,
        "risk_pct": round(score, 1),
        "source": source,
        "match_name": title,
        "sanctioned": sanctioned,
        "pep": pep,
        "debtor": debtor,
        "unverified_dob": unverified_dob,
        "sanction_match": best_sanction.get("name", "") if best_sanction else "",
    }