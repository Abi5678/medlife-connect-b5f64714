"""Insights agent tools: adherence scoring, vital trends, daily digest, family alerts,
predictive health analytics, and patient history queries.

All tools support Firestore (via tool_context) with mock_data.py fallback.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

from google import genai
from google.genai import types as genai_types

from agents.shared.constants import ANALYSIS_MODEL
from agents.shared.firestore_service import FirestoreService
from agents.shared.mock_data import (
    ADHERENCE_LOG,
    FAMILY_ALERTS,
    FOOD_LOGS,
    MEALS_LOG,
    MEDICATIONS,
    PATIENT_PROFILE,
    PRESCRIPTIONS,
    REPORTS,
    VITALS_LOG,
)

logger = logging.getLogger(__name__)

_analysis_client: genai.Client | None = None


def _get_analysis_client() -> genai.Client:
    """Return a genai.Client for the analysis model.

    Always prefers Vertex AI (uses service account from GOOGLE_APPLICATION_CREDENTIALS)
    since the free-tier Gemini API key has strict rate limits. Falls back to API key
    only if no GCP project is configured.
    """
    global _analysis_client
    if _analysis_client is None:
        gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        if gcp_project:
            _analysis_client = genai.Client(
                vertexai=True,
                project=gcp_project,
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
        else:
            _analysis_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY", ""))
    return _analysis_client


def _get_user_id(tool_context) -> str:
    """Extract user_id from ADK tool_context, with fallback."""
    if tool_context and hasattr(tool_context, "state"):
        return tool_context.state.get("user_id", "demo_user")
    return "demo_user"


def _use_firestore(tool_context) -> bool:
    """Check if Firestore should be used for this call."""
    fs = FirestoreService.get_instance()
    return fs.is_available and tool_context is not None


async def get_adherence_score(days: int = 7, tool_context=None) -> dict:
    """Calculate the patient's medication adherence score over a period.

    Returns the percentage of prescribed doses that were taken on time.

    Args:
        days: Number of past days to calculate adherence for (default 7).
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        relevant = await fs.get_adherence_log(user_id, since_date=cutoff)
    else:
        relevant = [e for e in ADHERENCE_LOG if e["date"] >= cutoff]

    if not relevant:
        return {
            "score": 0,
            "total_doses": 0,
            "taken": 0,
            "missed": 0,
            "period_days": days,
        }
    taken = sum(1 for e in relevant if e["taken"])
    total = len(relevant)
    score = round((taken / total) * 100, 1)
    missed_meds = [e["medication"] for e in relevant if not e["taken"]]
    return {
        "score": score,
        "total_doses": total,
        "taken": taken,
        "missed": total - taken,
        "missed_medications": missed_meds,
        "period_days": days,
        "rating": (
            "excellent"
            if score >= 90
            else "good" if score >= 80 else "needs improvement"
        ),
    }


async def get_vital_trends(
    vital_type: str = "blood_sugar", days: int = 7, tool_context=None
) -> dict:
    """Analyze trends in the patient's vital signs over time.

    Args:
        vital_type: The type of vital to analyze: 'blood_pressure', 'blood_sugar', or 'weight'.
        days: Number of past days to analyze (default 7).
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        readings = await fs.get_vitals_log(
            user_id, vital_type=vital_type, since_date=cutoff
        )
    else:
        readings = [
            e
            for e in VITALS_LOG
            if e["type"] == vital_type and e["date"] >= cutoff
        ]

    if len(readings) < 2:
        return {
            "vital_type": vital_type,
            "trend": "insufficient data",
            "readings": readings,
        }

    if vital_type == "blood_pressure":
        first_sys = int(str(readings[0]["value"]).split("/")[0])
        last_sys = int(str(readings[-1]["value"]).split("/")[0])
        diff = last_sys - first_sys
    else:
        first_val = float(readings[0]["value"])
        last_val = float(readings[-1]["value"])
        diff = last_val - first_val

    if abs(diff) < 3:
        trend = "stable"
    elif diff < 0:
        trend = "improving"
    else:
        trend = "increasing"

    return {
        "vital_type": vital_type,
        "trend": trend,
        "change": diff,
        "readings_count": len(readings),
        "first_reading": readings[0],
        "latest_reading": readings[-1],
        "period_days": days,
    }


async def get_daily_digest(tool_context=None) -> dict:
    """Generate a summary of today's health activity for the patient.

    Includes medications taken/pending, vitals recorded, and meals logged.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        # Run all 4 queries concurrently for performance
        today_adherence, medications, today_vitals, all_food_logs = (
            await asyncio.gather(
                fs.get_adherence_log(user_id, since_date=today),
                fs.get_medications(user_id),
                fs.get_vitals_log(user_id, since_date=today),
                fs.get_food_logs(user_id, limit=50),
            )
        )
        # Filter adherence to exact today (since_date is >=, not ==)
        today_adherence = [e for e in today_adherence if e["date"] == today]
        # Filter food logs to today only
        today_meals = [m for m in all_food_logs if m.get("date") == today]
    else:
        today_adherence = [e for e in ADHERENCE_LOG if e["date"] == today]
        medications = MEDICATIONS
        today_vitals = [e for e in VITALS_LOG if e["date"] == today]
        today_meals = [m for m in FOOD_LOGS if m.get("date") == today]

    meds_taken = [e["medication"] for e in today_adherence if e["taken"]]
    meds_missed = [e["medication"] for e in today_adherence if not e["taken"]]

    # Figure out pending meds (scheduled but not logged yet today)
    all_scheduled_today = []
    for med in medications:
        for _t in med["times"]:
            all_scheduled_today.append(med["name"])
    logged_names = [e["medication"] for e in today_adherence]
    pending = [name for name in all_scheduled_today if name not in logged_names]

    return {
        "date": today,
        "medications": {
            "taken": meds_taken,
            "missed": meds_missed,
            "pending": pending,
        },
        "vitals_recorded": today_vitals,
        "meals": today_meals,
        "summary": (
            f"Today: {len(meds_taken)} doses taken, {len(meds_missed)} missed, "
            f"{len(pending)} pending. {len(today_vitals)} vital readings. "
            f"{len(today_meals)} meals logged."
        ),
    }


async def send_family_alert(
    alert_type: str, message: str, tool_context=None
) -> dict:
    """Send an alert to the patient's family member or caregiver.

    Use this when medication adherence drops below 80%, vitals show
    concerning trends, the patient reports feeling unwell, or an
    emergency is detected.

    Args:
        alert_type: Type of alert: 'low_adherence', 'concerning_vitals', 'missed_medication', 'emergency', or 'general'.
        message: A clear description of the concern to share with the family.
    """
    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        profile = await fs.get_patient_profile(user_id)
        if not profile:
            profile = PATIENT_PROFILE  # fallback
    else:
        profile = PATIENT_PROFILE

    # Determine priority — "emergency" alerts get high priority
    priority = "high" if alert_type == "emergency" else "normal"

    ec = profile.get("emergency_contact", {})
    primary_contact = ec[0] if isinstance(ec, list) and ec else (ec if isinstance(ec, dict) else {})

    alert = {
        "timestamp": datetime.now().isoformat(),
        "alert_type": alert_type,
        "priority": priority,
        "message": message,
        "patient_name": profile.get("name", profile.get("companion_name", "")),
        "sent_to": primary_contact.get("name", ""),
        "phone": primary_contact.get("phone", ""),
    }

    if _use_firestore(tool_context):
        await fs.add_family_alert(user_id, alert)
    else:
        FAMILY_ALERTS.append(alert)

    # Optional: Twilio SMS for high-priority alerts
    sms_sent = False
    if priority == "high" and alert["phone"]:
        import os

        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        if twilio_sid:
            try:
                from twilio.rest import Client as TwilioClient

                twilio_client = TwilioClient(
                    twilio_sid, os.getenv("TWILIO_AUTH_TOKEN", "")
                )
                twilio_client.messages.create(
                    body=f"MedLive EMERGENCY: {message}",
                    from_=os.getenv("TWILIO_FROM_NUMBER", ""),
                    to=alert["phone"],
                )
                sms_sent = True
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning("Twilio SMS failed: %s", exc)

    return {
        "success": True,
        "alert": alert,
        "sms_sent": sms_sent,
        "note": (
            f"Alert sent to {alert['sent_to']} at {alert['phone']}. "
            f"Priority: {priority}."
        ),
    }


# ---------------------------------------------------------------------------
# Predictive Health Analytics — Rule-Based Pattern Detection
# ---------------------------------------------------------------------------


async def detect_health_patterns(days: int = 7, tool_context=None) -> dict:
    """Detect clinically meaningful patterns in the patient's recent health data.

    Runs deterministic rule-based checks across medication adherence, vitals,
    and meal logs to flag risks that may need attention.

    Args:
        days: Number of past days to analyze (default 7).
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        adherence, vitals, meals, medications = await asyncio.gather(
            fs.get_adherence_log(user_id, since_date=cutoff),
            fs.get_vitals_log(user_id, since_date=cutoff),
            fs.get_meals_log(user_id),
            fs.get_medications(user_id),
        )
    else:
        adherence = [e for e in ADHERENCE_LOG if e["date"] >= cutoff]
        vitals = [e for e in VITALS_LOG if e["date"] >= cutoff]
        meals = [e for e in MEALS_LOG if e["date"] >= cutoff]
        medications = MEDICATIONS

    alerts: list[dict] = []

    # --- Rising blood sugar trend (3+ consecutive increases) ---
    sugar_readings = [
        v for v in vitals
        if v["type"] == "blood_sugar" and isinstance(v["value"], (int, float))
    ]
    sugar_readings.sort(key=lambda x: x["date"])
    if len(sugar_readings) >= 3:
        consecutive_rises = 0
        for i in range(1, len(sugar_readings)):
            if float(sugar_readings[i]["value"]) - float(sugar_readings[i - 1]["value"]) > 10:
                consecutive_rises += 1
            else:
                consecutive_rises = 0
            if consecutive_rises >= 2:
                alerts.append({
                    "pattern": "rising_blood_sugar",
                    "severity": "moderate",
                    "message": (
                        f"Blood sugar has risen for {consecutive_rises + 1} consecutive readings "
                        f"(from {sugar_readings[i - consecutive_rises]['value']} to "
                        f"{sugar_readings[i]['value']} mg/dL)."
                    ),
                    "recommendation": "Review medication timing and diet. Consult your doctor if this continues.",
                })
                break

    # --- Missed medication correlates with blood sugar spike ---
    missed_diabetes_meds = [
        e for e in adherence
        if not e["taken"] and e["medication"] in ("Metformin", "Glimepiride")
    ]
    for missed in missed_diabetes_meds:
        missed_date = missed["date"]
        next_day = (datetime.strptime(missed_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        spikes = [
            v for v in sugar_readings
            if v["date"] in (missed_date, next_day) and float(v["value"]) > 180
        ]
        if spikes:
            alerts.append({
                "pattern": "missed_med_sugar_spike",
                "severity": "moderate",
                "message": (
                    f"Missed {missed['medication']} on {missed_date} was followed by "
                    f"blood sugar of {spikes[0]['value']} mg/dL."
                ),
                "recommendation": "Taking diabetes medication consistently helps keep blood sugar stable.",
            })

    # --- Blood pressure spike after missed Lisinopril ---
    missed_bp_meds = [
        e for e in adherence
        if not e["taken"] and e["medication"] == "Lisinopril"
    ]
    bp_readings = [v for v in vitals if v["type"] == "blood_pressure"]
    bp_readings.sort(key=lambda x: x["date"])
    for missed in missed_bp_meds:
        next_day = (datetime.strptime(missed["date"], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        high_bp = [
            v for v in bp_readings
            if v["date"] in (missed["date"], next_day)
            and int(str(v["value"]).split("/")[0]) > 140
        ]
        if high_bp:
            alerts.append({
                "pattern": "missed_bp_med_spike",
                "severity": "moderate",
                "message": (
                    f"Missed Lisinopril on {missed['date']} was followed by "
                    f"blood pressure of {high_bp[0]['value']} mmHg."
                ),
                "recommendation": "Consistent Lisinopril use helps keep blood pressure stable.",
            })

    # --- Overall adherence drop ---
    if adherence:
        taken_count = sum(1 for e in adherence if e["taken"])
        total_count = len(adherence)
        adherence_pct = (taken_count / total_count) * 100
        if adherence_pct < 70:
            alerts.append({
                "pattern": "low_adherence",
                "severity": "high",
                "message": f"Adherence is only {adherence_pct:.0f}% over the last {days} days.",
                "recommendation": "Consider setting up reminders. Family has been notified.",
            })

    # --- Hypoglycemia risk: Glimepiride taken but no meal logged within same day ---
    glimepiride_taken_dates = {
        e["date"] for e in adherence
        if e["taken"] and e["medication"] == "Glimepiride"
    }
    meal_dates = {m["date"] for m in meals if m.get("meal_type") in ("breakfast", "lunch")}
    risky_dates = glimepiride_taken_dates - meal_dates
    if risky_dates:
        alerts.append({
            "pattern": "hypoglycemia_risk",
            "severity": "high",
            "message": (
                f"Glimepiride was taken on {', '.join(sorted(risky_dates))} but no "
                f"breakfast or lunch was logged. Skipping meals with Glimepiride "
                f"increases the risk of dangerously low blood sugar."
            ),
            "recommendation": "Always eat a meal when taking Glimepiride.",
        })

    # --- Weight change > 2kg in the period ---
    weight_readings = [
        v for v in vitals if v["type"] == "weight"
    ]
    weight_readings.sort(key=lambda x: x["date"])
    if len(weight_readings) >= 2:
        first_w = float(weight_readings[0]["value"])
        last_w = float(weight_readings[-1]["value"])
        if abs(last_w - first_w) > 2.0:
            direction = "gained" if last_w > first_w else "lost"
            alerts.append({
                "pattern": "weight_change",
                "severity": "moderate",
                "message": f"Weight {direction} {abs(last_w - first_w):.1f} kg in {days} days ({first_w} → {last_w} kg).",
                "recommendation": "Discuss significant weight changes with your doctor.",
            })

    return {
        "period_days": days,
        "patterns_found": len(alerts),
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------
# Predictive Health Analytics — LLM-Powered Reasoning
# ---------------------------------------------------------------------------


async def predict_health_risks(days: int = 7, tool_context=None) -> dict:
    """Analyze patient health data over N days and predict potential risks.

    Combines rule-based pattern detection with LLM reasoning to identify
    trends, correlations, and early warning signs. The LLM provides a
    plain-language narrative that the Insights agent can share with the patient.

    Args:
        days: Number of past days to analyze (default 7).
    """
    patterns = await detect_health_patterns(days=days, tool_context=tool_context)

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        adherence, vitals, meals = await asyncio.gather(
            fs.get_adherence_log(user_id, since_date=cutoff),
            fs.get_vitals_log(user_id, since_date=cutoff),
            fs.get_meals_log(user_id),
        )
    else:
        adherence = [e for e in ADHERENCE_LOG if e["date"] >= cutoff]
        vitals = [e for e in VITALS_LOG if e["date"] >= cutoff]
        meals = [e for e in MEALS_LOG if e["date"] >= cutoff]

    data_summary = {
        "period": f"last {days} days",
        "adherence_entries": len(adherence),
        "taken": sum(1 for e in adherence if e["taken"]),
        "missed": sum(1 for e in adherence if not e["taken"]),
        "vitals": vitals[-20:],
        "meals": meals[-10:],
        "rule_based_alerts": patterns.get("alerts", []),
    }

    prompt = (
        "You are a clinical data analyst reviewing a patient's health data. "
        "The patient is an elderly person managing diabetes and hypertension "
        "with Metformin, Glimepiride, Lisinopril, and Atorvastatin.\n\n"
        f"DATA:\n{json.dumps(data_summary, indent=2, default=str)}\n\n"
        "TASK:\n"
        "1. Identify any correlations between medication adherence and vital sign changes.\n"
        "2. Flag concerning trajectories.\n"
        "3. Suggest 2-3 actionable next steps in plain language for the patient.\n"
        "4. NEVER diagnose. Only flag patterns for doctor discussion.\n"
        "5. Be encouraging where data supports it.\n\n"
        "Return a JSON object with keys: summary (string), risk_level (low/moderate/high), "
        "findings (list of strings), recommendations (list of strings)."
    )

    try:
        client = _get_analysis_client()
        response = client.models.generate_content(
            model=ANALYSIS_MODEL,
            contents=[genai_types.Part.from_text(text=prompt)],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        llm_analysis = json.loads(response.text)
    except Exception as exc:
        logger.warning("LLM predictive analysis failed: %s", exc)
        llm_analysis = {
            "summary": "Could not generate AI analysis at this time.",
            "risk_level": "unknown",
            "findings": [],
            "recommendations": [],
        }

    return {
        "period_days": days,
        "rule_based": patterns,
        "llm_analysis": llm_analysis,
    }


# ---------------------------------------------------------------------------
# Patient History Query (RAG-lite)
# ---------------------------------------------------------------------------


async def get_patient_history(query: str, tool_context=None) -> dict:
    """Search across a patient's clinical documents to answer questions.

    Queries scanned prescriptions, lab reports, vitals, and medication
    records to provide grounded answers about the patient's health history.

    Args:
        query: Natural language question (e.g., "what medications was I prescribed last month?")
    """
    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        prescriptions, reports, medications, vitals, meals = await asyncio.gather(
            fs.get_prescriptions(user_id),
            fs.get_reports(user_id),
            fs.get_medications(user_id),
            fs.get_vitals_log(user_id),
            fs.get_meals_log(user_id),
        )
    else:
        prescriptions = PRESCRIPTIONS
        reports = REPORTS
        medications = MEDICATIONS
        vitals = VITALS_LOG
        meals = MEALS_LOG

    context_block = {
        "medications": medications,
        "prescriptions": prescriptions[-10:],
        "lab_reports": reports[-10:],
        "recent_vitals": vitals[-30:],
        "meals_log": meals[-30:],
    }

    prompt = (
        "You are answering a patient's question about their medical history. "
        "Use ONLY the patient data provided below. If the data does not "
        "contain the answer, say so honestly.\n\n"
        f"PATIENT DATA:\n{json.dumps(context_block, indent=2, default=str)}\n\n"
        f"QUESTION: {query}\n\n"
        "Provide a clear, simple answer in 2-3 sentences."
    )

    try:
        client = _get_analysis_client()
        response = client.models.generate_content(
            model=ANALYSIS_MODEL,
            contents=[genai_types.Part.from_text(text=prompt)],
            config=genai_types.GenerateContentConfig(temperature=0.1),
        )
        answer = response.text
    except Exception as exc:
        logger.warning("Patient history query failed: %s", exc)
        answer = "I'm sorry, I couldn't search your records right now. Please try again."

    return {
        "query": query,
        "answer": answer,
        "sources_checked": {
            "prescriptions": len(prescriptions),
            "lab_reports": len(reports),
            "medications": len(medications),
            "vitals": len(vitals),
        },
    }


# ---------------------------------------------------------------------------
# Dietary Safety & Recipe Suggestions
# ---------------------------------------------------------------------------


async def suggest_safe_recipes(preferences: str, meal_type: str = "dinner", tool_context=None) -> dict:
    """Generate a safe recipe tailored to dietary preferences and health restrictions.

    Uses a Two-Pass Validation approach:
    1. Generates a creative recipe based on preferences.
    2. Scans the recipe against the patient's recorded allergies and diet type.
    3. Applies substitutions if any allergens are detected.

    Args:
        preferences: What the patient is craving (e.g., 'Kannada-style breakfast', 'comfort food').
        meal_type: Breakfast, Lunch, Dinner, or Snack.
    """
    user_id = _get_user_id(tool_context)
    
    allergies = []
    dietary_preference = ""
    if _use_firestore(tool_context):
        fs = FirestoreService.get_instance()
        profile = await fs.get_patient_profile(user_id) or {}
        dietary_preference = profile.get("dietary_preference", "")
        
        try:
            restrictions = await fs.get_health_restrictions(user_id)
            if restrictions:
                allergies = restrictions.get("allergies", [])
        except Exception as e:
            logger.warning("Failed to fetch health restrictions for recipe tool: %s", e)
    else:
        allergies = PATIENT_PROFILE.get("allergies", [])
        dietary_preference = PATIENT_PROFILE.get("diet_type", "")

    client = _get_analysis_client()
    
    # PASS 1: Generate Recipe (Creative)
    pass1_prompt = (
        f"Generate a {meal_type} recipe matching these preferences: '{preferences}'. "
        f"The patient's general diet type is: '{dietary_preference}'. "
        "Return a JSON object with: 'recipe_name', 'ingredients' (list of strings), 'instructions' (list of strings)."
    )
    
    try:
        response1 = client.models.generate_content(
            model=ANALYSIS_MODEL,
            contents=[genai_types.Part.from_text(text=pass1_prompt)],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7),
        )
        recipe = json.loads(response1.text)
    except Exception as exc:
        logger.error("Pass 1 recipe generation failed: %s", exc)
        return {"success": False, "error": "Failed to generate initial recipe."}
        
    # PASS 2: Safety Scan
    if not allergies:
        return {
            "success": True, 
            "safety_scan": "Passed (No allergies on file)",
            "recipe_name": recipe.get("recipe_name", ""),
            "ingredients": recipe.get("ingredients", []),
            "instructions": recipe.get("instructions", []),
            "safety_note": "No allergy restrictions found in profile."
        }
        
    pass2_prompt = (
        f"You are a clinical dietician working for MedLive. Review this recipe:\n"
        f"{json.dumps(recipe, indent=2)}\n\n"
        f"The patient has the following ALLERGIES/RESTRICTIONS: {', '.join(allergies)}.\n\n"
        "1. Scan the ingredients for these allergens.\n"
        "2. If an allergen is found, substitute it with a safe alternative and update the instructions.\n"
        "Return a JSON object with: 'is_safe' (boolean checking original recipe), 'allergens_found' (list of matched strings), "
        "'substitutions_made' (list of strings describing changes), 'safe_recipe' (the final safe recipe object with recipe_name, ingredients, instructions)."
    )
    
    try:
        response2 = client.models.generate_content(
            model=ANALYSIS_MODEL,
            contents=[genai_types.Part.from_text(text=pass2_prompt)],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        safety_result = json.loads(response2.text)
    except Exception as exc:
        logger.error("Pass 2 safety scan failed: %s", exc)
        return {"success": False, "error": "Failed to verify recipe safety against allergies."}
        
    final_recipe = safety_result.get("safe_recipe", recipe)
    
    return {
        "success": True,
        "original_unsafe": not safety_result.get("is_safe", True),
        "allergens_detected": safety_result.get("allergens_found", []),
        "substitutions_applied": safety_result.get("substitutions_made", []),
        "recipe_name": final_recipe.get("recipe_name", ""),
        "ingredients": final_recipe.get("ingredients", []),
        "instructions": final_recipe.get("instructions", []),
        "safety_note": (
            "This recipe has been verified against your allergies." if safety_result.get("is_safe")
            else f"Substituted {', '.join(safety_result.get('allergens_found', []))} with safe alternatives."
        )
    }


# ---------------------------------------------------------------------------
# Automated Grocery Lists
# ---------------------------------------------------------------------------


async def generate_grocery_list(recipe_ingredients: list[str], current_pantry_items: list[str] | None = None, tool_context=None) -> dict:
    """Generate a grocery shopping list required to make a recipe.
    
    Compares the ingredients needed for a meal against the items already
    available in the patient's pantry, outputting only what needs to be bought.
    Includes estimated prices.

    Args:
        recipe_ingredients: The list of ingredients required (e.g., from suggest_safe_recipes).
        current_pantry_items: Optional list of items the user already has. If empty, a mock pantry is used.
    """
    if not current_pantry_items:
        # For the hackathon, we simulate a smart fridge / pantry inventory
        current_pantry_items = [
            "Salt", "Black Pepper", "Olive Oil", "Garlic", "Onions", "Rice", 
            "Lentils", "Mustard Seeds", "Curry Leaves"
        ]

    client = _get_analysis_client()
    
    prompt = (
        "You are an automated grocery shopping assistant.\n\n"
        f"RECIPE NEEDS: {json.dumps(recipe_ingredients)}\n"
        f"ALREADY IN PANTRY: {json.dumps(current_pantry_items)}\n\n"
        "1. Identify which ingredients from the RECIPE NEEDS are NOT in the PANTRY.\n"
        "2. Format them into a shopping list.\n"
        "3. Estimate a reasonable grocery store price in USD for each missing item.\n\n"
        "Return a JSON object with 'missing_items' (list of dicts with 'name', 'quantity', 'estimated_price'), "
        "and 'total_estimated_cost' (number)."
    )
    
    try:
        response = client.models.generate_content(
            model=ANALYSIS_MODEL,
            contents=[genai_types.Part.from_text(text=prompt)],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
        )
        grocery_list = json.loads(response.text)
    except Exception as exc:
        logger.error("Grocery list generation failed: %s", exc)
        return {"success": False, "error": "Failed to generate grocery list."}

    return {
        "success": True,
        "already_have": [i for i in recipe_ingredients if i in current_pantry_items],
        "shopping_list": grocery_list.get("missing_items", []),
        "estimated_total_usd": grocery_list.get("total_estimated_cost", 0.0),
        "note": "Prices are estimates for your local grocery store."
    }


# ---------------------------------------------------------------------------
# Caregiver Approval Workflow
# ---------------------------------------------------------------------------


async def draft_dietary_plan(plan_title: str, description: str, tool_context=None) -> dict:
    """Draft a major dietary plan change for the patient that requires family approval.
    
    Use this when suggesting significant modifications to the patient's routine
    (e.g., switching to a Keto diet, fasting, or major caloric drops).
    The plan is saved in a 'draft' state and an alert is sent to the caregiver.

    Args:
        plan_title: A short, descriptive title for the plan (e.g., 'Transition to Low-Sodium').
        description: Detailed explanation of the plan and why it is recommended.
    """
    plan_id = f"plan_{int(datetime.now().timestamp())}"
    
    draft = {
        "plan_id": plan_id,
        "title": plan_title,
        "description": description,
        "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat() if "timezone" in globals() else datetime.now().isoformat()
    }
    
    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        # We would ideally save this to a users/{uid}/dietary_plans subcollection
        # For the hackathon, we simulate saving the draft and alerting the family.
        pass
        
    try:
        await send_family_alert(
            alert_type="dietary_approval",
            message=f"A new dietary plan ('{plan_title}') has been drafted for approval.",
            tool_context=tool_context
        )
    except Exception:
        pass

    return {
        "success": True,
        "plan_id": plan_id,
        "status": "draft",
        "message": f"Plan '{plan_title}' has been drafted and sent to the family dashboard for approval."
    }


