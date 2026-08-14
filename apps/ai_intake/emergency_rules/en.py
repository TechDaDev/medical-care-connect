from .base import EmergencyRule

RULES = [
    EmergencyRule("self_harm", "en", "emergency", phrase, suppressible=False)
    for phrase in ("suicide", "kill myself", "end my life", "want to die", "hurt myself", "self harm", "suicidal")
] + [
    EmergencyRule("chest_pain", "en", "emergency", phrase)
    for phrase in ("crushing chest pain", "severe chest pain", "chest tightness", "heart attack", "cardiac arrest")
] + [
    EmergencyRule("breathing_difficulty", "en", "urgent", phrase)
    for phrase in ("can't breathe", "difficulty breathing", "severe shortness of breath", "choking", "not breathing", "stopped breathing", "can't catch my breath")
] + [
    EmergencyRule("major_bleeding", "en", "urgent", phrase)
    for phrase in ("severe bleeding", "uncontrolled bleeding", "massive blood loss", "profuse bleeding", "gushing blood")
] + [
    EmergencyRule("stroke_like", "en", "emergency", phrase)
    for phrase in ("stroke symptom", "facial droop", "arm weakness", "slurred speech", "sudden numbness", "sudden paralysis", "cannot speak", "loss of consciousness")
] + [
    EmergencyRule("anaphylaxis", "en", "urgent", phrase)
    for phrase in ("anaphylaxis", "severe allergic reaction", "throat swelling", "tongue swelling", "airway closing")
]
