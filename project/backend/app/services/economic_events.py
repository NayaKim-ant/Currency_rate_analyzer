"""Conservative sentence-level economic events; unknown fields stay unknown."""
import re

NUMBER = r"(-?\d+(?:\.\d+)?)"
PERCENT = NUMBER + r"\s*(?:%|percent\b|퍼센트)"


def economic_event(text, factor, currencies, claim_type, direction, ambiguous=False):
    event = {"indicator": factor, "currencies": currencies, "type": claim_type,
             "actual": None, "previous": None, "expected": None, "unit": None,
             "change_basis_points": None, "surprise": None, "surprise_percentage_points": None,
             "attribution": "ambiguous" if ambiguous or len(currencies) != 1 else "single_currency_factor"}
    if re.search(r"\b(?:at|between|range(?:\s+of)?)\s*" + NUMBER + r"\s*%?\s*(?:[-–]|and|to)\s*" + PERCENT, text, re.I):
        event["attribution"] = "ambiguous"
    if event["attribution"] == "ambiguous" or re.search(r"\b(?:not|never|no longer)\b|않", text, re.I):
        return event

    def unique(pattern):
        values = {float(m.group(1)) for m in re.finditer(pattern, text, re.I)}
        return values.pop() if len(values) == 1 else None

    event["previous"] = unique(r"\bfrom\s+" + PERCENT)
    if event["previous"] is None:
        event["previous"] = unique(PERCENT + r"\s*(?:previously|prior)\b")
    event["expected"] = unique(r"\b(?:expected|forecast|anticipated)\s+(?:at\s+)?" + PERCENT)
    if event["expected"] is None:
        event["expected"] = unique(PERCENT + r"\s*(?:was\s+)?(?:expected|forecast)\b")
    if claim_type == "reported":
        actual_text = re.sub(r"\b(?:expected|forecast|anticipated)\s+(?:at\s+)?" + PERCENT, "", text, flags=re.I)
        actual_values = {float(m.group(1)) for m in re.finditer(r"\b(?:to|at)\s+" + PERCENT, actual_text, re.I)}
        event["actual"] = actual_values.pop() if len(actual_values) == 1 else None
        if event["actual"] is None:
            event["actual"] = unique(PERCENT + r"\s*(?:로|에서)?\s*(?:발표|기록|동결)")
        change = unique(r"\bby\s+" + NUMBER + r"\s*(?:basis points?|bps)\b")
        if change is None:
            points = unique(r"\bby\s+" + NUMBER + r"\s*percentage points?\b")
            change = None if points is None else points * 100
        if change is not None and direction in {"increase", "decrease"}:
            event["change_basis_points"] = abs(change) * (1 if direction == "increase" else -1)
        if re.search(r"\b(?:above|higher than|exceeded|beat)\s+(?:market\s+)?expectations?\b|예상치.*웃돌", text, re.I):
            event["surprise"] = "above"
        elif re.search(r"\b(?:below|lower than|missed)\s+(?:market\s+)?expectations?\b|예상치.*밑돌", text, re.I):
            event["surprise"] = "below"
        elif re.search(r"\b(?:in line with|matched)\s+(?:market\s+)?expectations?\b", text, re.I):
            event["surprise"] = "in_line"
        if event["actual"] is not None and event["expected"] is not None:
            difference = event["actual"] - event["expected"]
            calculated = "above" if difference > 1e-8 else "below" if difference < -1e-8 else "in_line"
            if event["surprise"] is not None and event["surprise"] != calculated:
                event["surprise"] = "conflicting"
            else:
                event["surprise"] = calculated
                event["surprise_percentage_points"] = difference
    if any(event[k] is not None for k in ("actual", "previous", "expected")):
        event["unit"] = "percent"
    return event
