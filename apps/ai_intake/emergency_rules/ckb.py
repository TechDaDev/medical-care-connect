from .base import EmergencyRule

RULES = [
    EmergencyRule(code, "ckb", severity, phrase, suppressible=code != "self_harm")
    for phrase, code, severity in (
        ("ئازاری سینە", "chest_pain", "emergency"),
        ("نەتوانم هەناسە بدەم", "breathing_difficulty", "emergency"),
        ("تەنگی هەناسە", "breathing_difficulty", "urgent"),
        ("لێدانەوەی دڵ", "chest_pain", "emergency"),
        ("خوێنێکی زۆر", "major_bleeding", "emergency"),
        ("هەوڵی خۆکوشتن", "self_harm", "emergency"),
        ("دەمەوێ خۆم بکوژم", "self_harm", "emergency"),
        ("بێهۆشی", "loss_of_consciousness", "emergency"),
    )
]
