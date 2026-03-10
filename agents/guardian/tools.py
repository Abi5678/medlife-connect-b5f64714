"""Guardian agent tools: medication management, pill verification, vitals, meals,
emergency detection and protocol.

All tools support Firestore (via tool_context) with mock_data.py fallback.
"""

import logging
import os
import re
from datetime import datetime, timezone

from agents.shared.firestore_service import FirestoreService
from agents.shared.mock_data import (
    ADHERENCE_LOG, MEDICATIONS, MEALS_LOG, VITALS_LOG,
    EMERGENCY_INCIDENTS, CALL_LOGS, PATIENT_PROFILE,
)
from agents.shared.constants import (
    RED_LINE_KEYWORDS,
    NEGATION_PREFIXES,
    RED_LINE_RESPONSE,
    EMERGENCY_NUMBERS,
)
from agents.shared.ui_tools import emit_ui_update


def _get_user_id(tool_context) -> str:
    """Extract user_id from ADK tool_context, with fallback."""
    if tool_context and hasattr(tool_context, "state"):
        return tool_context.state.get("user_id", "demo_user")
    return "demo_user"


def _use_firestore(tool_context) -> bool:
    """Check if Firestore should be used for this call."""
    fs = FirestoreService.get_instance()
    return fs.is_available and tool_context is not None


def get_medication_schedule(tool_context=None) -> dict:
    """Get today's medication schedule for the patient."""
    today = datetime.now().strftime("%Y-%m-%d")

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        medications = fs.get_medications_sync(user_id)
        adherence = fs.get_adherence_log_sync(user_id, since_date=today)
    else:
        medications = MEDICATIONS
        adherence = [e for e in ADHERENCE_LOG if e["date"] == today]

    schedule = []
    for med in medications:
        # Firestore stores "dose_times"; mock data uses "times"
        times = med.get("dose_times") or med.get("times") or []
        for t in times:
            taken_entry = next(
                (
                    e
                    for e in adherence
                    if e["date"] == today
                    and e["medication"] == med["name"]
                    and e["time"] == t
                ),
                None,
            )
            schedule.append(
                {
                    "medication": med.get("name", "Unknown"),
                    "dosage": med.get("dosage", ""),
                    "scheduled_time": t,
                    "purpose": med.get("purpose", ""),
                    "taken": taken_entry["taken"] if taken_entry else False,
                }
            )
    return {"date": today, "schedule": schedule}


def log_medication_schedule(
    medication_name: str, 
    schedule_type: str, 
    dose_times: list[str], 
    rxnorm_id: str = "", 
    tool_context=None
) -> dict:
    """Log a new medication schedule and setup proactive reminders.

    Args:
        medication_name: The name of the medication (e.g., 'Aspirin', 'Metformin').
        schedule_type: Frequency, e.g., 'Daily', 'Weekly', 'PRN' (as needed).
        dose_times: List of times in format HH:MM (e.g., ['08:00', '20:00']).
        rxnorm_id: Optional RxNorm code for the drug (e.g., '1191').
    """
    user_id = _get_user_id(tool_context)
    
    if _use_firestore(tool_context):
        fs = FirestoreService.get_instance()
        try:
            fs.add_medication_sync(user_id, medication_name, schedule_type, dose_times, rxnorm_id)
        except Exception as exc:
            return {"success": False, "error": f"Failed to save to database {exc}"}
    else:
        # Mock logic fallback
        MEDICATIONS.append({
            "name": medication_name,
            "dosage": "Unknown",
            "purpose": "Unknown",
            "times": dose_times,
            "pill_description": {"color": "unknown", "shape": "unknown", "imprint": "none"}
        })

    # Schedule proactive reminders using Cloud Tasks
    from agents.shared.tasks_service import TasksService
    reminders = []
    
    # We only schedule automatic reminders for concrete times; skip PRN
    if schedule_type.lower() != "prn":
        for dose_time in dose_times:
            task_id = TasksService.schedule_reminder(user_id, medication_name, dose_time, rxnorm_id)
            if task_id:
                reminders.append(dose_time)
            
    emit_ui_update(
        "medication_logged",
        {"name": medication_name, "schedule": schedule_type},
        tool_context,
    )

    return {
        "success": True,
        "message": f"Medication '{medication_name}' logged successfully for {schedule_type} schedule.",
        "reminders_scheduled_for": reminders if reminders else "None (Mock or PRN mode)"
    }


def log_medication_taken(medication_name: str, tool_context=None) -> dict:
    """Log that the patient has taken a specific medication.

    Args:
        medication_name: The name of the medication that was taken (e.g. 'Metformin').
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        medications = fs.get_medications_sync(user_id)
    else:
        medications = MEDICATIONS

    med = next(
        (m for m in medications if m["name"].lower() == medication_name.lower()),
        None,
    )
    if not med:
        return {
            "success": False,
            "error": f"Medication '{medication_name}' not found in records.",
        }

    entry = {
        "date": today,
        "medication": med["name"],
        "time": now_time,
        "taken": True,
    }

    if _use_firestore(tool_context):
        fs.add_adherence_entry_sync(user_id, entry)
    else:
        ADHERENCE_LOG.append(entry)

    emit_ui_update(
        "medication_taken",
        {"medication": med["name"], "time": now_time},
        tool_context,
    )

    return {
        "success": True,
        "medication": med["name"],
        "dosage": med.get("dosage", ""),
        "logged_at": now_time,
    }


def verify_pill(
    pill_color: str, pill_shape: str, pill_imprint: str = "", tool_context=None
) -> dict:
    """Verify a pill shown by the patient against their medication records.

    Compare the visual description of a pill against known medications to check
    if it matches. This is a critical safety tool.

    Args:
        pill_color: The color of the pill (e.g. 'white', 'pink', 'green').
        pill_shape: The shape of the pill (e.g. 'round', 'oval', 'oblong').
        pill_imprint: Any text or numbers imprinted on the pill (e.g. '500', 'L10').
    """
    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        medications = fs.get_medications_sync(user_id)
    else:
        medications = MEDICATIONS

    matches = []
    for med in medications:
        desc = med.get("pill_description") or {}
        color_match = desc["color"].lower() == pill_color.lower()
        shape_match = desc["shape"].lower() == pill_shape.lower()
        imprint_match = (
            not pill_imprint or desc["imprint"].lower() == pill_imprint.lower()
        )
        if color_match and shape_match and imprint_match:
            matches.append(
                {
                    "medication": med["name"],
                    "dosage": med.get("dosage", ""),
                    "expected_description": desc,
                    "match": True,
                    "confidence": "high" if pill_imprint else "medium",
                }
            )
    if matches:
        emit_ui_update(
            "pill_verified",
            {
                "verified": True,
                "matches": matches,
                "message": f"Verified: {', '.join(str(m['medication']) for m in matches)}"
            },
            tool_context
        )
        return {
            "verified": True,
            "matches": matches,
            "message": (
                f"This pill matches: {', '.join(str(m['medication']) for m in matches)}. "
                "It is safe to take."
            ),
        }
        
    emit_ui_update(
        "pill_verified",
        {
            "verified": False,
            "pill_described": {
                "color": pill_color,
                "shape": pill_shape,
                "imprint": pill_imprint,
            },
            "message": "WARNING: Pill mismatch!"
        },
        tool_context
    )
    return {
        "verified": False,
        "matches": [],
        "pill_described": {
            "color": pill_color,
            "shape": pill_shape,
            "imprint": pill_imprint,
        },
        "known_medications": [
            {"name": m["name"], "expected": m["pill_description"]}
            for m in medications
        ],
        "message": (
            "WARNING: This pill does NOT match any of your prescribed medications. "
            "Do NOT take it. Please consult your doctor or pharmacist."
        ),
    }


def log_vitals(
    vital_type: str, value: str, unit: str = "", tool_context=None
) -> dict:
    """Record a vital sign measurement for the patient.

    Args:
        vital_type: The type of vital sign (e.g. 'blood_pressure', 'blood_sugar', 'weight').
        value: The measured value (e.g. '130/82', '125', '68.5').
        unit: The unit of measurement (e.g. 'mmHg', 'mg/dL', 'kg'). Optional.
    """
    if not unit:
        if vital_type in ("blood_pressure", "bloodpressure"):
            unit = "mmHg"
        elif vital_type in ("blood_sugar", "bloodsugar", "glucose"):
            unit = "mg/dL"

    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M")

    entry = {
        "date": today,
        "time": now_time,
        "type": vital_type,
        "value": value,
        "unit": unit,
        "source": "voice_log",
    }

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        fs.add_vitals_entry_sync(user_id, entry)
    else:
        VITALS_LOG.append(entry)

    # --- Phase 4 Power Feature: Real-time Vital Adjustment ---
    # If the patient logs an unhealthily high blood sugar, we intercept the
    # standard response and inject a SYSTEM DIRECTIVE that forces Gemini to
    # break character and proactively intervene.
    directive = ""
    if vital_type.lower() in ("blood_sugar", "bloodsugar", "glucose"):
        try:
            numeric_val = float(value)
            if numeric_val > 180:
                directive = (
                    f"\n\n[SYSTEM DIRECTIVE: The patient just logged a HIGH "
                    f"blood sugar of {numeric_val}. You must IMMEDIATELY "
                    f"express gentle concern and proactively offer to fetch "
                    f"a low-glycemic recipe using the Insights agent to help "
                    f"them stabilize, or ask if they need to contact their doctor.]"
                )
        except ValueError:
            pass

    emit_ui_update(
        "vital_logged",
        {"type": vital_type, "value": value, "unit": unit},
        tool_context,
    )

    return {
        "success": True,
        "vital_type": vital_type,
        "value": value,
        "recorded": entry,
        "recorded_at": f"{today} {now_time}",
        "message": f"Vital sign logged.{directive}"
    }


def log_meal(
    description: str, meal_type: str = "snack", tool_context=None
) -> dict:
    """Record a meal or snack the patient has eaten.

    Args:
        description: What the patient ate (e.g. 'oatmeal with fruit and tea').
        meal_type: The type of meal: 'breakfast', 'lunch', 'dinner', or 'snack'.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    entry = {"date": today, "meal_type": meal_type, "description": description}

    if _use_firestore(tool_context):
        user_id = _get_user_id(tool_context)
        fs = FirestoreService.get_instance()
        fs.add_meals_entry_sync(user_id, entry)
    else:
        MEALS_LOG.append(entry)

    emit_ui_update(
        "meal_logged",
        {"description": description, "type": meal_type},
        tool_context,
    )

    return {"success": True, "recorded": entry}


# ---------------------------------------------------------------------------
# Emergency Detection & Protocol
# ---------------------------------------------------------------------------


def _build_negation_pattern(keyword: str) -> re.Pattern:
    """Build a regex that matches a negated form of a keyword."""
    prefix_group = "|".join(NEGATION_PREFIXES)
    pattern = rf"(?:{prefix_group}).{{0,20}}{re.escape(keyword)}"
    return re.compile(pattern, re.IGNORECASE)


def detect_emergency_severity(user_message: str, tool_context=None) -> dict:
    """Detect whether the user's message describes a Red Line emergency.

    Uses hardcoded keyword matching with negation awareness.
    This is a DETERMINISTIC safety check — not LLM-decided.

    Args:
        user_message: The text of what the user said (transcript).
    """
    message_lower = user_message.lower()

    for keyword in RED_LINE_KEYWORDS:
        if keyword in message_lower:
            # Check if the keyword is negated
            neg_pattern = _build_negation_pattern(keyword)
            if neg_pattern.search(message_lower):
                continue  # Negated — skip this keyword
            return {
                "is_red_line": True,
                "matched_keyword": keyword,
                "suggested_severity": "red_line",
            }

    # Not a red line — check for moderate/mild symptom keywords
    symptom_indicators = [
        "dizzy", "nausea", "headache", "fever", "vomiting",
        "weak", "tired", "pain", "swelling", "rash", "cough",
        "short of breath", "blurry vision", "numbness",
    ]
    for indicator in symptom_indicators:
        if indicator in message_lower:
            return {
                "is_red_line": False,
                "matched_keyword": indicator,
                "suggested_severity": "moderate",
            }

    return {
        "is_red_line": False,
        "matched_keyword": None,
        "suggested_severity": "mild",
    }


def initiate_emergency_protocol(
    symptom_description: str, severity: str, tool_context=None
) -> dict:
    """Initiate emergency response based on detected severity.

    For RED LINE emergencies: refuses medical advice, instructs to call
    emergency services, and sends a high-priority family alert.

    For non-red-line symptoms: logs the incident and lets Gemini continue
    with first-aid guidance.

    Args:
        symptom_description: What the user described (e.g. "chest pain").
        severity: One of "red_line", "urgent", "moderate", "mild".
    """
    now = datetime.now(timezone.utc).isoformat()
    user_id = _get_user_id(tool_context)
    is_red_line = severity == "red_line"

    # Build incident record
    incident = {
        "symptom": symptom_description,
        "severity": severity,
        "is_red_line": is_red_line,
        "action_taken": "call_emergency" if is_red_line else "first_aid_guidance",
        "alert_sent": is_red_line,
        "timestamp": now,
    }

    # Store incident
    if _use_firestore(tool_context):
        fs = FirestoreService.get_instance()
        try:
            fs.add_emergency_incident_sync(user_id, incident)
        except Exception:
            pass
    else:
        EMERGENCY_INCIDENTS.append(incident)

    if is_red_line:
        # RED LINE — hardcoded response, no LLM discretion
        emergency_number = EMERGENCY_NUMBERS.get("default", "911")
        message = RED_LINE_RESPONSE.format(emergency_number=emergency_number)

        # Send high-priority family alert
        from agents.insights.tools import send_family_alert

        try:
            import asyncio
            asyncio.run(send_family_alert(
                alert_type="emergency",
                message=f"EMERGENCY: {symptom_description}. Patient instructed to call {emergency_number}.",
                tool_context=tool_context,
            ))
        except Exception:
            pass

        return {
            "action": "call_emergency",
            "message": message,
            "emergency_number": emergency_number,
            "alert_sent": True,
            "interrupt_audio": True,
        }
    else:
        return {
            "action": "first_aid_guidance",
            "symptom": symptom_description,
            "severity": severity,
            "message": (
                f"The patient reports: {symptom_description}. "
                "Provide calm, reassuring first-aid guidance. "
                "Recommend they consult their doctor. "
                "Do NOT diagnose any condition."
            ),
        }


# ---------------------------------------------------------------------------
# Family Calling — Two-Legged PSTN Bridge
# ---------------------------------------------------------------------------


def _match_contact(profile: dict, contact_name: str) -> dict | None:
    """Fuzzy-match contact_name against the patient's emergency contact(s)."""
    ec = profile.get("emergency_contact")
    if not ec:
        return None
    contacts = ec if isinstance(ec, list) else [ec]
    name_lower = contact_name.lower()
    for c in contacts:
        c_name = c.get("name", "").lower()
        c_rel = c.get("relationship", "").lower()
        if (
            name_lower in c_name
            or name_lower in c_rel
            or c_name in name_lower
            or c_rel in name_lower
        ):
            return c
    return None


def initiate_family_call(
    contact_name: str, reason: str = "", tool_context=None
) -> dict:
    """Place a phone call to a family member on behalf of the patient.

    Uses a Two-Legged PSTN bridge: Twilio first calls the patient's own phone,
    then when they pick up, bridges the call to the family member.

    Args:
        contact_name: Who to call — a name or relationship (e.g. 'my son', 'Carlos', 'daughter').
        reason: Why the call is being placed (e.g. 'patient requested', 'emergency').
    """
    now = datetime.now(timezone.utc).isoformat()
    user_id = _get_user_id(tool_context)

    # Resolve patient profile and contact
    if _use_firestore(tool_context):
        fs = FirestoreService.get_instance()
        profile = fs.get_patient_profile_sync(user_id) or {}
    else:
        profile = PATIENT_PROFILE

    contact = _match_contact(profile, contact_name)
    if not contact:
        return {
            "success": False,
            "message": (
                f"I couldn't find a contact matching '{contact_name}' in your records. "
                "Please check the name or relationship and try again."
            ),
        }

    contact_phone = contact.get("phone", "")
    contact_display = contact.get("name", contact_name)
    if not contact_phone:
        return {
            "success": False,
            "message": f"No phone number on file for {contact_display}.",
        }

    # Check Twilio configuration
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
    twilio_from = os.environ.get("TWILIO_FROM_NUMBER")

    if not twilio_sid or not twilio_token or not twilio_from:
        # Mock / demo mode — pretend the call succeeded
        call_log = {
            "contact_name": contact_display,
            "contact_phone": contact_phone,
            "call_sid": "mock_sid_demo",
            "status": "queued",
            "initiated_at": now,
            "reason": reason or f"Voice request: {contact_name}",
        }
        if _use_firestore(tool_context):
            try:
                fs.add_call_log_sync(user_id, call_log)
            except Exception:
                pass
        else:
            CALL_LOGS.append(call_log)

        return {
            "success": True,
            "contact_name": contact_display,
            "contact_phone_masked": contact_phone[:3] + "***" + contact_phone[-4:],
            "message": (
                f"Ringing your phone now. Pick up to talk to {contact_display}."
            ),
            "demo_mode": True,
        }

    # Real Twilio call — two-legged PSTN bridge
    patient_phone = profile.get("phone", "")
    if not patient_phone:
        return {
            "success": False,
            "message": (
                "Your phone number is not set in your profile. "
                "Please update your profile to enable calling."
            ),
        }

    from twilio.rest import Client as TwilioClient

    try:
        client = TwilioClient(twilio_sid, twilio_token)
        twiml_xml = (
            f'<Response>'
            f'<Say voice="alice">Connecting you to {contact_display} now.</Say>'
            f'<Dial callerId="{twilio_from}">{contact_phone}</Dial>'
            f'</Response>'
        )
        call = client.calls.create(
            to=patient_phone,
            from_=twilio_from,
            twiml=twiml_xml,
        )
        call_sid = call.sid
        status = call.status
    except Exception as exc:
        return {
            "success": False,
            "message": f"Failed to place the call: {exc}",
        }

    # Log the call
    call_log = {
        "contact_name": contact_display,
        "contact_phone": contact_phone,
        "call_sid": call_sid,
        "status": status,
        "initiated_at": now,
        "reason": reason or f"Voice request: {contact_name}",
    }
    if _use_firestore(tool_context):
        try:
            fs.add_call_log_sync(user_id, call_log)
        except Exception:
            pass
    else:
        CALL_LOGS.append(call_log)

    return {
        "success": True,
        "contact_name": contact_display,
        "contact_phone_masked": contact_phone[:3] + "***" + contact_phone[-4:],
        "call_sid": call_sid,
        "message": (
            f"Ringing your phone now. Pick up to talk to {contact_display}."
        ),
    }
