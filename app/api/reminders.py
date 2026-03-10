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
    v = os.getenv("SKIP_AUTH_FOR_TESTING", "true").lower()
    return v not in ("0", "false", "no")


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
    reminder_meds_enabled: bool = True
    reminder_lunch_enabled: bool = True
    lunch_reminder_time: str = "12:00"
    timezone: str = Field(default="UTC", min_length=1)


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
        reminder_meds_enabled=body.reminder_meds_enabled,
        reminder_lunch_enabled=body.reminder_lunch_enabled,
        lunch_reminder_time=lunch,
        timezone=tz,
    )
    return {"ok": True, "message": "Reminder preferences saved"}


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

        token = sub.get("fcm_token")
        if not token:
            continue

        # Meds: distinct medication times that fall in current 15-min window
        if sub.get("reminder_meds_enabled"):
            meds = await fs.get_medications(uid)
            med_times = set()
            for m in meds:
                for t in m.get("times", []):
                    if isinstance(t, str) and len(t) >= 4:
                        med_times.add(t[:5] if len(t) > 5 else t)  # "08:00" or "8:00" -> "08:00"
            for mt in med_times:
                # Normalize to HH:MM
                if len(mt) == 4:
                    mt = "0" + mt
                if mt == slot_str:
                    title = "Time for your medications"
                    body = "Your doses are due. Tap to open MedLive and log."
                    url = f"{app_url}/?checkin=true&type=meds"
                    try:
                        msg = fb_messaging.Message(
                            notification=fb_messaging.Notification(title=title, body=body),
                            data={"url": url},
                            token=token,
                        )
                        fb_messaging.send(msg)
                        sent += 1
                        logger.info("FCM meds reminder sent to uid=%s", uid)
                    except Exception as e:
                        logger.warning("FCM send failed for uid=%s: %s", uid, e)
                    break  # one meds reminder per user per run

        # Lunch: if lunch_reminder_time matches current slot
        if sub.get("reminder_lunch_enabled"):
            lunch_time = (sub.get("lunch_reminder_time") or "12:00").strip()
            if len(lunch_time) == 4:
                lunch_time = "0" + lunch_time
            if lunch_time == slot_str:
                title = "Log your lunch"
                body = "Tap to log your meal in MedLive."
                url = f"{app_url}/?checkin=true&type=lunch"
                try:
                    msg = fb_messaging.Message(
                        notification=fb_messaging.Notification(title=title, body=body),
                        data={"url": url},
                        token=token,
                    )
                    fb_messaging.send(msg)
                    sent += 1
                    logger.info("FCM lunch reminder sent to uid=%s", uid)
                except Exception as e:
                    logger.warning("FCM send failed for uid=%s: %s", uid, e)

    return {"ok": True, "sent": sent}
