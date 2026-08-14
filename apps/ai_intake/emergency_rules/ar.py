from .base import EmergencyRule

RULES = [
    EmergencyRule(code, "ar", severity, phrase, suppressible=code != "self_harm")
    for phrase, code, severity in (
        ("الم في الصدر", "chest_pain", "emergency"),
        ("الم صدر", "chest_pain", "emergency"),
        ("ضيق التنفس", "breathing_difficulty", "urgent"),
        ("لا استطيع التنفس", "breathing_difficulty", "emergency"),
        ("نزيف شديد", "major_bleeding", "emergency"),
        ("انتحار", "self_harm", "emergency"),
        ("اريد ان اقتل نفسي", "self_harm", "emergency"),
        ("سكته", "stroke_like", "emergency"),
        ("تخدير مفاجئ", "stroke_like", "emergency"),
        ("صعوبه في الكلام", "stroke_like", "emergency"),
        ("فقدان الوعي", "loss_of_consciousness", "emergency"),
    )
]
