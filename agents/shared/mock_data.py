"""In-memory mock data for Phase 2 demo. Replaced by Firestore in Phase 3."""

PATIENT_PROFILE = {
    "user_id": "demo_user",
    "name": "Maria Garcia",
    "age": 72,
    "language": "hi",
    "phone": "+1-555-0199",
    "emergency_contact": [
        {
            "name": "Carlos Garcia",
            "relationship": "Son",
            "phone": "+1-555-0123",
        },
        {
            "name": "Sofia Garcia",
            "relationship": "Daughter",
            "phone": "+1-555-0456",
        },
    ],
}

MEDICATIONS = [
    {
        "id": "med_1",
        "name": "Metformin",
        "dosage": "500mg",
        "frequency": "twice daily",
        "times": ["08:00", "20:00"],
        "purpose": "diabetes / blood sugar control",
        "pill_description": {
            "color": "white",
            "shape": "round",
            "imprint": "500",
            "size": "small",
        },
        "food_instructions": "Take with food to reduce stomach upset.",
        "side_effects": [
            "nausea",
            "diarrhea",
            "stomach discomfort",
            "metallic taste",
        ],
        "interactions": {
            "lisinopril": {
                "severity": "moderate",
                "description": (
                    "Lisinopril (ACE inhibitor) can amplify Metformin's "
                    "blood-sugar-lowering effect, increasing hypoglycemia risk."
                ),
            },
            "alcohol": {
                "severity": "major",
                "description": (
                    "Alcohol with Metformin can cause dangerous lactic acidosis. "
                    "Even moderate drinking on an empty stomach is risky."
                ),
            },
        },
        "warnings": "Never drink alcohol while taking Metformin.",
    },
    {
        "id": "med_2",
        "name": "Lisinopril",
        "dosage": "10mg",
        "frequency": "once daily",
        "times": ["08:00"],
        "purpose": "blood pressure control",
        "pill_description": {
            "color": "pink",
            "shape": "round",
            "imprint": "L10",
            "size": "small",
        },
        "food_instructions": "Can be taken with or without food.",
        "side_effects": [
            "dry cough",
            "dizziness",
            "headache",
            "fatigue",
        ],
        "interactions": {
            "metformin": {
                "severity": "moderate",
                "description": (
                    "ACE inhibitors potentiate hypoglycemic effects of Metformin, "
                    "increasing low blood sugar risk in elderly patients."
                ),
            },
            "glimepiride": {
                "severity": "moderate",
                "description": (
                    "ACE inhibitors potentiate hypoglycemic effects of sulfonylureas "
                    "like Glimepiride. Monitor blood sugar closely."
                ),
            },
        },
        "warnings": "May cause dry cough. Report persistent cough to doctor.",
    },
    {
        "id": "med_3",
        "name": "Atorvastatin",
        "dosage": "20mg",
        "frequency": "once daily",
        "times": ["20:00"],
        "purpose": "cholesterol management",
        "pill_description": {
            "color": "white",
            "shape": "oval",
            "imprint": "ATV 20",
            "size": "medium",
        },
        "food_instructions": "Best taken in the evening. Can be with or without food.",
        "side_effects": [
            "muscle pain",
            "joint pain",
            "nausea",
            "elevated liver enzymes",
        ],
        "interactions": {},
        "warnings": (
            "Report unexplained muscle pain or weakness to your doctor immediately "
            "— this could indicate a rare but serious side effect."
        ),
    },
    {
        "id": "med_4",
        "name": "Glimepiride",
        "dosage": "2mg",
        "frequency": "once daily",
        "times": ["08:00"],
        "purpose": "diabetes / blood sugar control",
        "pill_description": {
            "color": "green",
            "shape": "oblong",
            "imprint": "G2",
            "size": "medium",
        },
        "food_instructions": "Take with breakfast. NEVER skip meals while on this medication.",
        "side_effects": [
            "hypoglycemia (low blood sugar)",
            "dizziness",
            "nausea",
            "weight gain",
        ],
        "interactions": {
            "lisinopril": {
                "severity": "moderate",
                "description": (
                    "Lisinopril amplifies Glimepiride's blood-sugar-lowering effect. "
                    "Highest hypoglycemia risk of all four medications when combined."
                ),
            },
        },
        "warnings": (
            "Highest hypoglycemia risk. Always eat when taking this medication. "
            "Symptoms of low sugar: shakiness, sweating, confusion, dizziness."
        ),
    },
]

# Mutable at runtime — tools append to these lists
ADHERENCE_LOG: list[dict] = [
    {"date": "2026-03-01", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-01", "medication": "Metformin", "time": "20:00", "taken": True},
    {"date": "2026-03-01", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-01", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-01", "medication": "Glimepiride", "time": "08:00", "taken": True},
    # 2nd — missed evening Metformin
    {"date": "2026-03-02", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-02", "medication": "Metformin", "time": "20:00", "taken": False},
    {"date": "2026-03-02", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-02", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-02", "medication": "Glimepiride", "time": "08:00", "taken": True},
    # 3rd — all taken
    {"date": "2026-03-03", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-03", "medication": "Metformin", "time": "20:00", "taken": True},
    {"date": "2026-03-03", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-03", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-03", "medication": "Glimepiride", "time": "08:00", "taken": True},
    # 4th — missed Glimepiride
    {"date": "2026-03-04", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-04", "medication": "Metformin", "time": "20:00", "taken": True},
    {"date": "2026-03-04", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-04", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-04", "medication": "Glimepiride", "time": "08:00", "taken": False},
    # 5th–7th — all taken
    {"date": "2026-03-05", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-05", "medication": "Metformin", "time": "20:00", "taken": True},
    {"date": "2026-03-05", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-05", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-05", "medication": "Glimepiride", "time": "08:00", "taken": True},
    {"date": "2026-03-06", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-06", "medication": "Metformin", "time": "20:00", "taken": True},
    {"date": "2026-03-06", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-06", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-06", "medication": "Glimepiride", "time": "08:00", "taken": True},
    {"date": "2026-03-07", "medication": "Metformin", "time": "08:00", "taken": True},
    {"date": "2026-03-07", "medication": "Metformin", "time": "20:00", "taken": True},
    {"date": "2026-03-07", "medication": "Lisinopril", "time": "08:00", "taken": True},
    {"date": "2026-03-07", "medication": "Atorvastatin", "time": "20:00", "taken": True},
    {"date": "2026-03-07", "medication": "Glimepiride", "time": "08:00", "taken": True},
]

VITALS_LOG: list[dict] = [
    {"date": "2026-03-01", "type": "blood_pressure", "value": "138/88", "unit": "mmHg"},
    {"date": "2026-03-01", "type": "blood_sugar", "value": 145, "unit": "mg/dL"},
    {"date": "2026-03-02", "type": "blood_pressure", "value": "135/85", "unit": "mmHg"},
    {"date": "2026-03-02", "type": "blood_sugar", "value": 138, "unit": "mg/dL"},
    {"date": "2026-03-03", "type": "blood_pressure", "value": "130/82", "unit": "mmHg"},
    {"date": "2026-03-03", "type": "blood_sugar", "value": 132, "unit": "mg/dL"},
    {"date": "2026-03-04", "type": "blood_pressure", "value": "132/84", "unit": "mmHg"},
    {"date": "2026-03-04", "type": "blood_sugar", "value": 140, "unit": "mg/dL"},
    {"date": "2026-03-05", "type": "weight", "value": 68.5, "unit": "kg"},
    {"date": "2026-03-05", "type": "blood_pressure", "value": "128/80", "unit": "mmHg"},
    {"date": "2026-03-05", "type": "blood_sugar", "value": 125, "unit": "mg/dL"},
    {"date": "2026-03-06", "type": "blood_pressure", "value": "130/82", "unit": "mmHg"},
    {"date": "2026-03-06", "type": "blood_sugar", "value": 130, "unit": "mg/dL"},
    {"date": "2026-03-07", "type": "blood_pressure", "value": "126/79", "unit": "mmHg"},
    {"date": "2026-03-07", "type": "blood_sugar", "value": 122, "unit": "mg/dL"},
]

MEALS_LOG: list[dict] = [
    {"date": "2026-03-07", "meal_type": "breakfast", "description": "Oatmeal with berries, green tea"},
    {"date": "2026-03-07", "meal_type": "lunch", "description": "Grilled chicken salad, water"},
]

FAMILY_ALERTS: list[dict] = []

PRESCRIPTIONS: list[dict] = []

REPORTS: list[dict] = []

EMERGENCY_INCIDENTS: list[dict] = []

CALL_LOGS: list[dict] = []

APPOINTMENTS: list[dict] = []

FOOD_LOGS: list[dict] = []
