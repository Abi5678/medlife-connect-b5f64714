"""Proactive push reminders: register FCM token + preferences, trigger job for meds/lunch."""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import firebase_admin.auth as fb_auth
from firebase_admin import messaging as fb_messaging

from agents.shared.firestore_service import FirestoreService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _skip_auth() -> bool:
    v = os.getenv("SKIP_AUTH_FOR_TESTING", "false").lower()
    return v in ("1", "true", "yes")


def _verify_token(authorization: str | None) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if _skip_auth() and (not token or token == "demo"):
        return "demo_user"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid auth token")
    try:
        decoded = fb_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {exc}")


def _verify_trigger_secret(authorization: str | None, x_secret: str | None) -> None:
    secret = os.getenv("REMINDERS_TRIGGER_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Reminders trigger not configured")
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    if (token or x_secret or "") != secret:
        raise HTTPException(status_code=403, detail="Invalid trigger secret")


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class RegisterRemindersRequest(BaseModel):
    fcm_token: str | None = None
    phone_number: str | None = None
    reminder_meds_enabled: bool = True
    reminder_lunch_enabled: bool = True
    reminder_dinner_enabled: bool = True
    reminder_glucose_enabled: bool = False
    voice_reminders_enabled: bool = False
    lunch_reminder_time: str = "12:00"
    dinner_reminder_time: str = "19:00"
    glucose_reminder_time: str = "08:00"
    timezone: str = Field(default="UTC", min_length=1)


class TestCallRequest(BaseModel):
    phone_number: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register")
async def register_reminders(
    body: RegisterRemindersRequest,
    authorization: str = Header(default=None),
):
    """Store FCM token and reminder preferences for the authenticated user.

    Call with Firebase ID token in Authorization: Bearer <id_token>.
    If fcm_token is null or empty, push is disabled and token is cleared.
    """
    uid = _verify_token(authorization)
    fs = FirestoreService.get_instance()
    if not fs.is_available:
        raise HTTPException(status_code=503, detail="Reminders require Firestore")

    # Normalize lunch time to HH:MM
    lunch = body.lunch_reminder_time.strip()
    if len(lunch) == 4 and lunch[1] == ":":
        lunch = "0" + lunch  # 9:00 -> 09:00
    try:
        h, m = lunch.split(":")
        lunch = f"{int(h):02d}:{int(m):02d}"
    except (ValueError, IndexError):
        lunch = "12:00"

    tz = body.timezone.strip() or "UTC"
    try:
        ZoneInfo(tz)
    except Exception:
        tz = "UTC"

    await fs.save_reminder_preferences(
        user_id=uid,
        fcm_token=body.fcm_token.strip() if body.fcm_token else None,
        phone_number=body.phone_number.strip() if body.phone_number else None,
        reminder_meds_enabled=body.reminder_meds_enabled,
        reminder_lunch_enabled=body.reminder_lunch_enabled,
        reminder_dinner_enabled=body.reminder_dinner_enabled,
        reminder_glucose_enabled=body.reminder_glucose_enabled,
        voice_reminders_enabled=body.voice_reminders_enabled,
        lunch_reminder_time=lunch,
        dinner_reminder_time=body.dinner_reminder_time or "19:00",
        glucose_reminder_time=body.glucose_reminder_time or "08:00",
        timezone=tz,
    )
    return {"ok": True, "message": "Reminder preferences saved"}


@router.get("/preferences")
async def get_reminder_preferences(
    authorization: str = Header(default=None),
):
    """Retrieve reminder preferences for the authenticated user."""
    uid = _verify_token(authorization)
    fs = FirestoreService.get_instance()
    profile = await fs.get_patient_profile(uid)
    if not profile:
        profile = {}
    
    return {
        "reminder_meds_enabled": profile.get("reminder_meds_enabled", True),
        "reminder_lunch_enabled": profile.get("reminder_lunch_enabled", True),
        "reminder_dinner_enabled": profile.get("reminder_dinner_enabled", True),
        "reminder_glucose_enabled": profile.get("reminder_glucose_enabled", False),
        "voice_reminders_enabled": profile.get("voice_reminders_enabled", False),
        "lunch_reminder_time": profile.get("lunch_reminder_time", "12:00"),
        "dinner_reminder_time": profile.get("dinner_reminder_time", "19:00"),
        "glucose_reminder_time": profile.get("glucose_reminder_time", "08:00"),
        "phone_number": profile.get("phone_number", ""),
        "timezone": profile.get("timezone", "UTC"),
    }


@router.post("/trigger")
async def trigger_reminders(
    authorization: str = Header(default=None),
    x_cloud_scheduler_secret: str = Header(default=None, alias="X-CloudScheduler-Secret"),
):
    """Internal endpoint for Cloud Scheduler. Sends FCM push to users whose
    local time matches a meds slot or lunch reminder. Secured by shared secret.
    """
    _verify_trigger_secret(authorization, x_cloud_scheduler_secret)
    fs = FirestoreService.get_instance()
    if not fs.is_available:
        return {"ok": False, "sent": 0, "reason": "Firestore unavailable"}

    app_url = os.getenv("MEDLIVE_APP_URL", "http://localhost:8000").rstrip("/")
    subscribers = await fs.list_reminder_subscribers()
    sent = 0

    for sub in subscribers:
        uid = sub["user_id"]
        tz_name = sub.get("timezone") or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        local_time_str = now.strftime("%H:%M")  # e.g. 08:05
        local_hour = now.hour
        local_min = now.minute
        # Current 15-min slot: e.g. 08:00-08:14 -> slot "08:00"
        slot_min = (local_min // 15) * 15
        slot_str = f"{local_hour:02d}:{slot_min:02d}"

        fcm_token = sub.get("fcm_token")
        if not fcm_token and not sub.get("voice_reminders_enabled"):
            continue

        patient_name = sub.get("name") or "there"
        patient_phone = sub.get("phone_number") or ""
        voice_enabled = sub.get("voice_reminders_enabled") and bool(patient_phone)
        
        from app.services.twilio_service import TwilioVoiceService
        base_url = app_url.rstrip("/")

        # Helper to trigger voice
        async def _maybe_call(type_label: str):
            if voice_enabled:
                twiml_url = f"{base_url}/api/calling/twiml/reminder?name={patient_name}&type={type_label}"
                await TwilioVoiceService.make_outbound_call(patient_phone, twiml_url)
                logger.info("Twilio voice reminder triggered for uid=%s type=%s", uid, type_label)

        # Meds: distinct medication times that fall in current 15-min window
        if sub.get("reminder_meds_enabled"):
            meds = await fs.get_medications(uid)
            med_times = set()
            for m in meds:
                for t in m.get("times", []):
                    if isinstance(t, str) and len(t) >= 4:
                        med_times.add(t[:5] if len(t) > 5 else t)
            for mt in med_times:
                if len(mt) == 4: mt = "0" + mt
                if mt == slot_str:
                    # Push
                    if fcm_token:
                        try:
                            msg = fb_messaging.Message(
                                notification=fb_messaging.Notification(title="Time for your medications", body="Your doses are due."),
                                data={"url": f"{app_url}/?checkin=true&type=meds"},
                                token=fcm_token,
                            )
                            fb_messaging.send(msg)
                            sent += 1
                        except Exception: pass
                    # Voice
                    await _maybe_call("meds")
                    break

        # Other Slot-based reminders
        reminders_to_check = [
            ("reminder_lunch_enabled", "lunch_reminder_time", "lunch", "Time for lunch"),
            ("reminder_dinner_enabled", "dinner_reminder_time", "dinner", "Time for dinner"),
            ("reminder_glucose_enabled", "glucose_reminder_time", "glucose", "Glucose test reminder"),
        ]

        for pref_key, time_key, type_label, push_title in reminders_to_check:
            if sub.get(pref_key):
                r_time = (sub.get(time_key) or "12:00").strip()
                if len(r_time) == 4: r_time = "0" + r_time
                if r_time == slot_str:
                    # Push
                    if fcm_token:
                        try:
                            msg = fb_messaging.Message(
                                notification=fb_messaging.Notification(title=push_title, body=f"It's time for your {type_label}."),
                                data={"url": f"{app_url}/?checkin=true&type={type_label}"},
                                token=fcm_token,
                            )
                            fb_messaging.send(msg)
                            sent += 1
                        except Exception: pass
                    # Voice
                    await _maybe_call(type_label)

    return {"ok": True, "sent": sent}


@router.post("/test-call")
async def test_voice_call(
    body: TestCallRequest = None,
    authorization: str = Header(default=None),
):
    """Trigger an immediate test voice call to the authenticated user."""
    uid = _verify_token(authorization)
    fs = FirestoreService.get_instance()
    profile = await fs.get_patient_profile(uid)
    if not profile:
        profile = {}
    
    # Use phone from body if provided, otherwise from profile
    phone = (body.phone_number if body else None) or profile.get("phone_number")
    
    if not phone:
        raise HTTPException(status_code=400, detail="No phone number provided or found in profile")
        
    name = profile.get("name") or "there"
    from app.services.twilio_service import TwilioVoiceService
    
    app_url = os.getenv("MEDLIVE_APP_URL", "http://localhost:8000").rstrip("/")
    twiml_url = f"{app_url}/api/calling/twiml/reminder?name={name}&type=test"
    
    sid = await TwilioVoiceService.make_outbound_call(phone, twiml_url)
    if not sid:
        raise HTTPException(status_code=500, detail="Twilio call failed. Check server logs.")
        
    return {"ok": True, "call_sid": sid}
