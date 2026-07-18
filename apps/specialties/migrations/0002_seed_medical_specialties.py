from django.db import migrations
from django.utils.text import slugify


def seed_specialties(apps, schema_editor):
    Specialty = apps.get_model("specialties", "Specialty")
    specialties = [
        ("Cardiology", "Heart and cardiovascular system"),
        ("Dermatology", "Skin, hair, and nails"),
        ("Endocrinology", "Hormones and metabolic disorders"),
        ("Gastroenterology", "Digestive system"),
        ("Geriatrics", "Care of older adults"),
        ("Hematology", "Blood disorders"),
        ("Infectious Disease", "Infections and communicable diseases"),
        ("Internal Medicine", "Adult primary care"),
        ("Nephrology", "Kidney diseases"),
        ("Neurology", "Brain and nervous system"),
        ("Obstetrics & Gynecology", "Women's reproductive health"),
        ("Oncology", "Cancer diagnosis and treatment"),
        ("Ophthalmology", "Eye and vision care"),
        ("Orthopedics", "Bones, joints, and muscles"),
        ("Otolaryngology (ENT)", "Ear, nose, and throat"),
        ("Pediatrics", "Children's health"),
        ("Psychiatry", "Mental health"),
        ("Pulmonology", "Respiratory system"),
        ("Radiology", "Medical imaging"),
        ("Rheumatology", "Autoimmune and joint diseases"),
        ("Surgery — General", "General surgical procedures"),
        ("Surgery — Cardiothoracic", "Heart and chest surgery"),
        ("Surgery — Neurosurgery", "Brain and spine surgery"),
        ("Surgery — Orthopedic", "Musculoskeletal surgery"),
        ("Surgery — Plastic", "Reconstructive and cosmetic surgery"),
        ("Urology", "Urinary tract and male reproductive system"),
        ("Anesthesiology", "Anesthesia and pain management"),
        ("Emergency Medicine", "Acute and emergency care"),
        ("Family Medicine", "Comprehensive family health care"),
        ("Pathology", "Laboratory diagnosis of disease"),
        ("Physical Medicine & Rehabilitation", "Functional recovery and rehabilitation"),
        ("Sports Medicine", "Sports-related injuries and fitness"),
        ("Allergy & Immunology", "Allergic and immune system disorders"),
        ("Critical Care Medicine", "Intensive care management"),
        ("Genetics", "Genetic disorders and counseling"),
        ("Nuclear Medicine", "Radioactive substances in diagnosis and treatment"),
        ("Pain Medicine", "Management of chronic and acute pain"),
        ("Sleep Medicine", "Sleep disorders"),
        ("Vascular Medicine", "Blood vessel disorders"),
        ("Addiction Medicine", "Substance use disorders"),
    ]
    for i, (name, desc) in enumerate(specialties):
        Specialty.objects.get_or_create(
            name=name,
            defaults={"slug": slugify(name), "description": desc, "display_order": i, "is_active": True},
        )


def reverse_specialties(apps, schema_editor):
    Specialty = apps.get_model("specialties", "Specialty")
    Specialty.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("specialties", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_specialties, reverse_specialties),
    ]
