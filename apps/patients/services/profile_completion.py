from apps.patients.models import BloodType, PatientProfile


def calculate_profile_completion(user, profile: PatientProfile) -> dict:
    """Return one authoritative patient profile-completion calculation."""
    values = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone_number": user.phone_number,
        "date_of_birth": profile.date_of_birth,
        "gender": profile.gender,
        "preferred_language": profile.preferred_language,
        "address": profile.address,
        "emergency_contact_name": profile.emergency_contact_name,
        "emergency_contact_phone": profile.emergency_contact_phone,
        "blood_type": (
            None if profile.blood_type == BloodType.UNKNOWN else profile.blood_type
        ),
    }
    missing_fields = [name for name, value in values.items() if not value]
    return {
        "percent": round(
            (len(values) - len(missing_fields)) / len(values) * 100
        ),
        "missing_fields": missing_fields,
        "personal_information_complete": all(
            values[field]
            for field in ("first_name", "last_name", "date_of_birth", "gender")
        ),
        "contact_information_complete": all(
            values[field]
            for field in ("phone_number", "address", "preferred_language")
        ),
        "emergency_contact_complete": all(
            values[field]
            for field in (
                "emergency_contact_name",
                "emergency_contact_phone",
            )
        ),
        "basic_health_complete": all(
            values[field]
            for field in ("date_of_birth", "gender", "blood_type")
        ),
    }
