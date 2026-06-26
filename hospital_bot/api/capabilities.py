# capabilities.py  — add this new file
PATIENT_CAPABILITIES = {
    "appointments": "Check your upcoming and pending appointments",
    "doctor":       "Find your assigned doctor",
    "lab_results":  "View your recent lab results",
    "booking":      "Book new appointments with your doctor",
    "medical_qa":   "Answer general health and medication questions",
}

# Human-readable list for the LLM
def capabilities_summary() -> str:
    return ", ".join(PATIENT_CAPABILITIES.values())

# Locked scope sentence injected into the system prompt
def scope_rule() -> str:
    items = "\n".join(f"  - {v}" for v in PATIENT_CAPABILITIES.values())
    return (
        "CRITICAL SCOPE RULE: You are a patient-facing assistant. "
        "You ONLY help patients with the following:\n"
        f"{items}\n"
        "You NEVER describe internal hospital protocols, staff directories, "
        "emergency codes, or operational documents to patients. "
        "If asked what you can do, respond ONLY with the list above."
    )