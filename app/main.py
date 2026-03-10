"""MedLive FastAPI Application.

WebSocket server for bidirectional voice/video streaming with Gemini Live API
via Google ADK. Based on the ADK bidi-demo reference pattern.

Four-phase lifecycle:
1. Application Init: Agent, SessionService, Runner
2. Session Init: LiveRequestQueue, RunConfig
3. Bidi-Streaming: Upstream (client -> Gemini) + Downstream (Gemini -> client)
4. Termination: Graceful cleanup
"""

import asyncio
import base64
import json
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

# Load .env BEFORE any agent imports so constants.py picks up env vars
load_dotenv()

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types
from firebase_admin import messaging

from agents.agent import root_agent
from agents.shared.constants import APP_NAME, RED_LINE_KEYWORDS, NEGATION_PREFIXES
from agents.shared.firestore_service import FirestoreService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Firebase Admin SDK (token verification for WebSocket + REST auth)
# ---------------------------------------------------------------------------

import firebase_admin
from firebase_admin import credentials as fb_credentials
from firebase_admin import auth as fb_auth

if not firebase_admin._apps:
    _cred_path = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", "credentials/firebase-admin-sdk.json"
    )
    firebase_admin.initialize_app(fb_credentials.Certificate(_cred_path))
    logger.info("Firebase Admin SDK initialized")


def _verify_firebase_token(token: str) -> dict:
    """Verify Firebase ID token; returns decoded claims dict."""
    return fb_auth.verify_id_token(token)


# ---------------------------------------------------------------------------
# Phase 1: Application Initialization
# ---------------------------------------------------------------------------

app = FastAPI(title="MedLive", description="Real-time AI Health Guardian")

# CORS: allow React dev server + production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firestore if enabled (routes tool data through GCP Firestore)
if os.getenv("USE_FIRESTORE", "false").lower() == "true":
    FirestoreService.get_instance().initialize()


# Middleware: Prevent browser caching of static files during development.
# Without this, updated JS files return 304 Not Modified and bugs persist.
class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )
            response.headers["Pragma"] = "no-cache"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# Mount API routers
from app.api.avatar import router as avatar_router
from app.api.family import router as family_router
from app.api.reminders import router as reminders_router
from app.api.scan import router as scan_router
from app.api.calling import router as calling_router
from app.api.food import router as food_router
from app.api.medications import router as medications_router

app.include_router(avatar_router)
app.include_router(family_router)
app.include_router(reminders_router)
app.include_router(scan_router)
app.include_router(calling_router)
app.include_router(food_router)
app.include_router(medications_router)

# Session service (will upgrade to Firestore-backed in Phase 3)
session_service = InMemorySessionService()

# ADK Runner
runner = Runner(
    app_name=APP_NAME,
    agent=root_agent,
    session_service=session_service,
)

# Serve static files (REPLACE WITH Vite dist soon)
# STATIC_DIR = Path(__file__).parent / "static"
# app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    """Serve the modern React UI (from Vite dist)."""
    REACT_INDEX = Path(__file__).parent.parent / "dist" / "index.html"
    if REACT_INDEX.exists():
        return FileResponse(str(REACT_INDEX))
    # Fallback to legacy if dist is missing
    return JSONResponse({"status": "error", "message": "Frontend build (dist/index.html) not found. Run 'npm run build'."})


@app.get("/health")
async def health_check():
    """Cloud Run health check endpoint."""
    return {"status": "healthy", "app": APP_NAME}


def _skip_auth_for_testing() -> bool:
    """True when auth is disabled for testing. Set SKIP_AUTH_FOR_TESTING=0 or false to enable auth."""
    v = os.getenv("SKIP_AUTH_FOR_TESTING", "true").lower()
    if v in ("0", "false", "no"):
        return False
    return True  # default to skip auth for easier local testing


@app.get("/api/config")
async def get_public_config():
    """Public config for the frontend (e.g. VAPID key for FCM, skipAuth for testing)."""
    return {
        "vapidKey": os.getenv("VAPID_KEY", ""),
        "skipAuth": _skip_auth_for_testing(),
    }


# Legacy dashboard redirecting to new one
@app.get("/dashboard")
async def dashboard_page():
    """Redirect to new React dashboard."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/")


# ---------------------------------------------------------------------------
# Auth + Profile REST Endpoints
# ---------------------------------------------------------------------------


def _extract_uid(authorization: str | None) -> str:
    """Verify 'Bearer <idToken>' header and return Firebase UID (or demo_user when skip auth)."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if _skip_auth_for_testing() and (not token or token == "demo"):
        return "demo_user"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    try:
        decoded = _verify_firebase_token(token)
        return decoded["uid"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")


@app.get("/api/auth/profile")
async def get_profile(authorization: str = Header(default=None)):
    """Return the Firestore profile for the authenticated user.

    Returns 404 if this is a first-time user (no profile yet).
    """
    uid = _extract_uid(authorization)
    fs = FirestoreService.get_instance()

    if not fs.is_available:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    profile = await fs.get_or_create_profile(uid)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found (first-time user)")

    return JSONResponse(profile)


@app.post("/api/auth/profile")
async def save_profile(
    body: dict,
    authorization: str = Header(default=None),
):
    """Save / update the authenticated user's profile after onboarding.

    Accepts any subset of: language, companion_name, avatar_b64, family_link_code.
    """
    uid = _extract_uid(authorization)
    fs = FirestoreService.get_instance()

    if not fs.is_available:
        raise HTTPException(status_code=503, detail="Firestore unavailable")

    # Only allow safe profile fields (block internal Firestore fields)
    allowed_profile = {"language", "companion_name", "avatar_b64", "family_link_code", "display_name", "voice_name"}
    filtered_profile = {k: v for k, v in body.items() if k in allowed_profile}

    if filtered_profile:
        await fs.save_user_profile(uid, filtered_profile)

    # Handle health restrictions separately per schema
    if "allergies" in body or "dietary_preference" in body or "current_medications" in body:
        # Expecting allergies as a comma separated string from the frontend form
        allergies_str = body.get("allergies", "")
        allergies = [a.strip() for a in allergies_str.split(",") if a.strip()]
        diet = body.get("dietary_preference", "")
        meds = body.get("current_medications", "")
        await fs.save_health_restrictions(uid, allergies, diet, meds)

    if not filtered_profile and "allergies" not in body and "dietary_preference" not in body and "current_medications" not in body:
        raise HTTPException(status_code=400, detail="No valid profile or health fields provided")

    return {"status": "ok", "uid": uid, "updated": list(filtered_profile.keys()) + ["health"]}


# ---------------------------------------------------------------------------
# Proactive Reminders (Cloud Tasks Webhook)
# ---------------------------------------------------------------------------


@app.post("/api/tasks/reminder")
async def handle_medication_reminder(request: Request):
    """Webhook for Google Cloud Tasks to hit when it's time to take medication."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    uid = data.get("uid")
    medication_name = data.get("medication_name")
    
    if not uid or not medication_name:
        raise HTTPException(status_code=400, detail="Missing uid or medication_name")
        
    logger.info("Processing Cloud Task reminder for %s: %s", uid, medication_name)
    
    # 1. Fetch user profile to get FCM device token
    fs = FirestoreService.get_instance()
    profile = await fs.get_patient_profile(uid)
    fcm_token = profile.get("fcm_token") if profile else None
    
    # Construct Proactive Audio Prompt
    proactive_msg = f"[SYSTEM INJECTION: The patient just opened the app from a push notification reminding them to take their {medication_name}. Proactively greet them and remind them to take it, without waiting for them to speak first.]"
    
    if not fcm_token:
        # Mock mode if no active device token is registered
        logger.warning("[MOCK PUSH] Would send push to %s => %s", uid, medication_name)
        return {"status": "mock_push_sent", "proactive_prompt": proactive_msg}
        
    # 2. Send FCM Push Notification
    message = messaging.Message(
        notification=messaging.Notification(
            title="Medication Reminder",
            body=f"It's time to take your {medication_name}.",
        ),
        data={
            "action": "open_medlive",
            "proactive_prompt": proactive_msg
        },
        token=fcm_token,
    )
    
    try:
        response = messaging.send(message)
        logger.info("Successfully sent FCM message: %s", response)
        return {"status": "ok", "message_id": response}
    except Exception as e:
        logger.error("FCM sending failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Family Dashboard REST Endpoint
# ---------------------------------------------------------------------------


@app.get("/api/dashboard")
async def get_dashboard_data(
    patient_uid: str,
    authorization: str = Header(default=None),
):
    """Return live health data for the family caregiver dashboard.

    The requester must be:
    - The patient themselves (own data), OR
    - A family member who has verified a family link code for this patient.

    Returns a JSON dict with keys:
        adherence           – 7-day medication adherence score
        blood_sugar_trend   – blood sugar readings trend
        blood_pressure_trend – blood pressure readings trend
        digest              – today's digest (medications, vitals, meals)
    """
    # 1. Authenticate requester
    requester_uid = _extract_uid(authorization)

    # 2. Authorise: self-view OR family member check
    if requester_uid != patient_uid:
        fs = FirestoreService.get_instance()
        if fs.is_available:
            linked = await fs.is_family_linked(requester_uid, patient_uid)
            if not linked:
                raise HTTPException(
                    status_code=403, detail="Not linked to this patient"
                )

    # 3. Fetch live data by calling insights tools directly.
    #    We build a minimal tool_context-like object that routes Firestore
    #    queries to the correct patient UID.
    from agents.insights.tools import (
        get_adherence_score,
        get_vital_trends,
        get_daily_digest,
    )
    from agents.shared.mock_data import PATIENT_PROFILE as _mock_profile

    class _ToolCtx:
        state = {"user_id": patient_uid}

    # In demo / skip-auth mode force mock data by passing no tool_context,
    # so the insights tools bypass Firestore (which has no health records for
    # demo_user) and fall back to mock_data.py instead.
    ctx = None if _skip_auth_for_testing() else _ToolCtx()

    # Default fallback data for when Firestore has no records
    _default_adherence = {"taken": 0, "missed": 0, "total_doses": 0, "score": 0, "rating": "No data"}
    _default_trend = {"trend": "stable", "readings": [], "latest_reading": None}
    _default_digest = {"medications": {"taken": [], "missed": [], "pending": []}, "vitals": [], "meals": []}

    # Resolve patient name (Firestore profile → mock data fallback)
    patient_name = _mock_profile.get("name", "")
    fs = FirestoreService.get_instance()
    if fs.is_available:
        try:
            profile = await fs.get_patient_profile(patient_uid)
            if profile:
                patient_name = profile.get("name", profile.get("companion_name", patient_name))
        except Exception:
            pass

    try:
        adherence, blood_sugar_trend, bp_trend, digest = await asyncio.gather(
            get_adherence_score(days=7, tool_context=ctx),
            get_vital_trends("blood_sugar", days=7, tool_context=ctx),
            get_vital_trends("blood_pressure", days=7, tool_context=ctx),
            get_daily_digest(tool_context=ctx),
        )
    except Exception as exc:
        logger.warning("Dashboard data fetch failed for uid=%s: %s", patient_uid, exc)
        adherence = _default_adherence
        blood_sugar_trend = _default_trend
        bp_trend = _default_trend
        digest = _default_digest

    return JSONResponse({
        "patient_name": patient_name,
        "adherence": adherence or _default_adherence,
        "blood_sugar_trend": blood_sugar_trend or _default_trend,
        "blood_pressure_trend": bp_trend or _default_trend,
        "digest": digest or _default_digest,
    })


# ---------------------------------------------------------------------------
# Phase 10: Appointments API
# ---------------------------------------------------------------------------


@app.get("/api/appointments")
async def get_appointments(
    patient_uid: str,
    authorization: str = Header(default=None),
):
    """Return upcoming appointments for a patient.

    Auth logic mirrors /api/dashboard.
    """
    requester_uid = _extract_uid(authorization)

    if requester_uid != patient_uid:
        fs = FirestoreService.get_instance()
        if fs.is_available:
            linked = await fs.is_family_linked(requester_uid, patient_uid)
            if not linked:
                raise HTTPException(
                    status_code=403, detail="Not linked to this patient"
                )

    # Fetch appointments
    fs = FirestoreService.get_instance()
    if fs.is_available:
        try:
            appointments = await fs.get_appointments(patient_uid)
        except Exception as exc:
            logger.warning("Appointments fetch failed for uid=%s: %s", patient_uid, exc)
            appointments = []
    else:
        from agents.shared.mock_data import APPOINTMENTS
        appointments = [a for a in APPOINTMENTS if a.get("patient_uid") == patient_uid]

    return JSONResponse({"appointments": appointments})


# ---------------------------------------------------------------------------
# Phase 2-4: WebSocket Bidi-Streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Bidirectional voice/video streaming via WebSocket.

    Client sends JSON messages:
        {"type": "audio", "data": "<base64 PCM 16kHz mono>"}
        {"type": "image", "data": "<base64 JPEG>", "mimeType": "image/jpeg"}
        {"type": "text",  "text": "hello"}

    Server sends ADK LiveEvent JSON (contains audio, text, transcriptions, etc.)

    Query params:
        ?token={Firebase ID Token}   (required; verified server-side)
        ?persona=en|hi|kn|es          (optional; fallback if no Firestore profile)
    """
    # --- Auth gate ---
    # NOTE: websocket.accept() must be called BEFORE websocket.close() with a
    # custom code; otherwise Starlette returns HTTP 403 and the browser never
    # sees the WS close frame, so the JS onclose(4401) redirect never fires.
    token = websocket.query_params.get("token", "")
    if _skip_auth_for_testing() and (not token or token == "demo"):
        uid = user_id  # use path param as uid (client sends /ws/demo_user)
    elif not token:
        await websocket.accept()
        await websocket.close(code=4401, reason="Missing auth token")
        return
    else:
        try:
            decoded = _verify_firebase_token(token)
            uid = decoded["uid"]
        except Exception as exc:
            logger.warning("WS auth failed: %s", exc)
            await websocket.accept()
            await websocket.close(code=4401, reason="Invalid auth token")
            return

    await websocket.accept()
    session_id = str(uuid.uuid4())

    # --- Load profile from Firestore for language + companion_name ---
    fs = FirestoreService.get_instance()
    language = "English"
    companion_name = "Health Companion"
    voice_name = "Aoede" # Default
    onboarding_complete = False
    patient_name = ""

    if fs.is_available:
        try:
            profile = await fs.get_patient_profile(uid)
            if profile:
                language = profile.get("language", language)
                companion_name = profile.get("companion_name", companion_name)
                voice_name = profile.get("voice_name", voice_name)
                onboarding_complete = profile.get("onboarding_complete", False)
                patient_name = profile.get("name", "")
        except Exception as e:
            logger.warning("Could not load profile for uid=%s: %s", uid, e)

    q_patient_name = websocket.query_params.get("patient_name")
    if q_patient_name and (_skip_auth_for_testing() or not patient_name):
        patient_name = q_patient_name
        onboarding_complete = True

    # Fallback: Trust frontend's persona query param if DB values are defaults
    persona = websocket.query_params.get("persona")
    PERSONA_DEFAULTS = {
        "hi": ("Hindi", "Dr. Priya", "Aoede"),
        "es": ("Spanish", "Enfermera Elena", "Aoede"),
        "kn": ("Kannada", "ಆರೋಗ್ಯ ಸಂಗಾತಿ", "Aoede"),
        "en": ("English", "Dr. Chen", "Aoede"),
    }
    if persona and persona in PERSONA_DEFAULTS:
        fallback_lang, fallback_name, fallback_voice = PERSONA_DEFAULTS[persona]
        # In demo/skip-auth mode always trust the frontend persona param (Firestore
        # may have a stale language from a previous session that cannot be updated).
        # In auth mode only override when the DB still has the default "English".
        if language == "English" or _skip_auth_for_testing():
            language = fallback_lang
        if companion_name == "Health Companion":
            companion_name = fallback_name
        if voice_name == "Aoede":
            voice_name = fallback_voice

    logger.info(
        "WebSocket connected: uid=%s session=%s language=%s companion=%s voice=%s",
        uid, session_id, language, companion_name, voice_name
    )

    # --- Phase 2: Session Initialization ---
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=uid,
        session_id=session_id,
        state={
            "user_id": uid,
            "session_id": session_id,
            "language": language,
            "companion_name": companion_name,
            "onboarding_complete": onboarding_complete,
            "patient_name": patient_name,
        },
    )

    live_request_queue = LiveRequestQueue()
    session.state["live_request_queue"] = live_request_queue

    # --- Phase 2.1: Avatar Initialization ---
    avatar_b64 = None
    if fs.is_available:
        try:
            # Check if user already has an avatar
            profile = await fs.get_patient_profile(uid)
            if profile and profile.get("avatar_b64"):
                avatar_b64 = profile["avatar_b64"]
            else:
                # Generate a friendly random avatar based on companion name
                from app.api.avatar import generate_avatar
                from fastapi import Form
                
                logger.info(f"Generating new avatar for {companion_name}...")
                avatar_response = await generate_avatar(
                    companion_name=companion_name,
                    avatar_description="A friendly medical professional with a warm smile"
                )
                if isinstance(avatar_response, JSONResponse):
                    resp_data = json.loads(avatar_response.body)
                    avatar_b64 = resp_data.get("avatar_b64")
                    if avatar_b64:
                        await fs.save_user_profile(uid, {"avatar_b64": avatar_b64})
        except Exception as e:
            logger.warning(f"Avatar generation/retrieval failed: {e}")

    # Dispatch avatar to frontend immediately
    if avatar_b64:
        await websocket.send_text(json.dumps({
            "target": "avatar_update", 
            "avatar_b64": avatar_b64,
            "companion_name": companion_name
        }))

    # --- Phase 2.5: Proactive Audio Injection ---
    # Priority: explicit query param > smart routing based on profile
    proactive_prompt = websocket.query_params.get("proactive_prompt")
    if proactive_prompt:
        logger.info("Injecting explicit proactive prompt: %s", proactive_prompt)
    elif not onboarding_complete:
        proactive_prompt = (
            f"[SYSTEM: This is a brand-new user who has NOT completed onboarding. "
            f"Transfer them to the onboarding agent immediately. Say something brief "
            f"in {language} like 'Welcome! Let me help you get set up.' and hand off.]"
        )
        logger.info("New user detected — injecting onboarding auto-start prompt in %s", language)
    elif patient_name:
        proactive_prompt = (
            f"[SYSTEM: Welcome back! The patient's name is {patient_name}. "
            f"They have already completed onboarding. Greet them warmly by name "
            f"and ask how you can help today. Be personable.]"
        )
        logger.info("Returning user '%s' — injecting warm greeting prompt", patient_name)

    if proactive_prompt:
        content = types.Content(
            parts=[types.Part(text=proactive_prompt)]
        )
        live_request_queue.send_content(content)

    # Wellness/exercise sessions get a calmer voice and affective dialog enabled
    # so the model naturally softens its tone to match the meditative context.
    is_wellness_session = proactive_prompt and "WELLNESS_SESSION_START" in proactive_prompt
    if is_wellness_session:
        voice_name = "Kore"  # Soft, gentle voice — best for guided wellness
        logger.info("Wellness session detected — using Kore voice + affective dialog")

    # RunConfig for native audio bidi-streaming
    # VAD: endOfSpeechSensitivity=LOW so the model commits end-of-turn with shorter
    # silence; silenceDurationMs=400ms balances latency vs allowing natural pauses.
    # For wellness sessions, increase silence_duration_ms so the agent pauses longer
    # between cues, creating a more meditative rhythm.
    silence_ms = 800 if is_wellness_session else 400
    realtime_input_config = types.RealtimeInputConfig(
        automatic_activity_detection=types.AutomaticActivityDetection(
            end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
            silence_duration_ms=silence_ms,
        )
    )
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=realtime_input_config,
        # enable_affective_dialog lets the model adjust its vocal tone to match
        # emotional context — for wellness it naturally becomes calmer and warmer.
        enable_affective_dialog=True,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name,  # Dynamic voice (Kore for wellness)
                )
            )
        ),
    )

    # --- Phase 3: Upstream + Downstream Tasks ---

    def _scan_red_line(text: str) -> str | None:
        """Deterministic keyword scan for life-threatening emergencies.

        Returns the matched keyword or None. Respects negation prefixes
        so "I don't have chest pain" does not trigger a false alarm.
        """
        import re
        text_lower = text.lower()
        for keyword in RED_LINE_KEYWORDS:
            if keyword in text_lower:
                prefix_group = "|".join(NEGATION_PREFIXES)
                neg_pattern = re.compile(
                    rf"(?:{prefix_group}).{{0,20}}{re.escape(keyword)}",
                    re.IGNORECASE,
                )
                if neg_pattern.search(text_lower):
                    continue
                return keyword
        return None

    # Shared state for diagnostics: downstream can log when first response arrives after audio
    upstream_audio_chunks = []

    async def upstream_task():
        """Client -> Server -> LiveRequestQueue."""
        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "audio":
                    try:
                        audio_bytes = base64.b64decode(msg["data"])
                    except Exception as e:
                        logger.warning("Upstream audio decode failed: %s", e)
                        continue
                    upstream_audio_chunks.append(len(audio_bytes))
                    n = len(upstream_audio_chunks)
                    if n <= 10 or n % 50 == 0:
                        logger.info(
                            "Upstream audio #%s: %s bytes (total so far: %s)",
                            n, len(audio_bytes), sum(upstream_audio_chunks),
                        )
                    if n == 500:
                        logger.warning(
                            "No response yet after 500 upstream audio chunks. "
                            "If you spoke, the model may not be replying to audio."
                        )
                    live_request_queue.send_realtime(
                        types.Blob(
                            mime_type="audio/pcm;rate=16000",
                            data=audio_bytes,
                        )
                    )

                elif msg_type == "image":
                    image_bytes = base64.b64decode(msg["data"])
                    mime = msg.get("mimeType", "image/jpeg")
                    live_request_queue.send_realtime(
                        types.Blob(mime_type=mime, data=image_bytes)
                    )

                elif msg_type == "end_turn":
                    # DEPRECATED: Gemini native audio API uses automatic activity detection (VAD).
                    # Explicit activity control (send_activity_end) is not supported and will
                    # crash the connection with APIError 1007.
                    logger.info("Received end_turn from client (ignored due to auto-VAD)")

                elif msg_type == "text":
                    user_text = msg["text"]
                    logger.info("Upstream text received (e.g. greeting): %s", user_text[:80] + "..." if len(user_text) > 80 else user_text)
                    red_line_hit = _scan_red_line(user_text)
                    if red_line_hit:
                        logger.warning(
                            "RED LINE detected in text (keyword=%s), "
                            "injecting emergency directive",
                            red_line_hit,
                        )
                        user_text = (
                            f"[SYSTEM: RED LINE EMERGENCY DETECTED — "
                            f"patient said '{red_line_hit}'. You MUST call "
                            f"initiate_emergency_protocol immediately with "
                            f"severity='red_line' and symptom_description="
                            f"'{red_line_hit}'. Do NOT provide medical advice.]"
                        )

                    # gemini-live-2.5-flash-native-audio completely ignores text input
                    # (both send_content and text/plain blob). We must synthesize the
                    # text to audio and send it as a PCM stream to force a response.
                    try:
                        import tempfile
                        import subprocess
                        import wave

                        # Use macOS native 'say' command for zero-dependency, free, offline TTS
                        # to bypass Gemini Native Audio's inability to read text inputs.
                        # --file-format=WAVE is required: without it 'say' produces AIFF
                        # even with a .wav extension, causing wave.open() to fail silently.
                        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
                            subprocess.run(
                                [
                                    "say", "-o", f.name,
                                    "--data-format=LEI16@16000",
                                    "--file-format=WAVE",
                                    user_text,
                                ],
                                check=True
                            )
                            with wave.open(f.name, "rb") as w:
                                pcm_audio = w.readframes(w.getnframes())

                        live_request_queue.send_realtime(
                            types.Blob(
                                mime_type="audio/pcm;rate=16000",
                                data=pcm_audio,
                            )
                        )
                        # Pad with 500 ms of silence so VAD detects end-of-speech
                        # and triggers model inference. Without this the model may
                        # never see the end-of-turn boundary after short TTS clips.
                        _silence = bytes(int(16000 * 0.5) * 2)  # 500 ms @ 16kHz 16-bit mono
                        live_request_queue.send_realtime(
                            types.Blob(mime_type="audio/pcm;rate=16000", data=_silence)
                        )
                        logger.info("Synthesized %d bytes of PCM audio from text using macOS 'say' and sent to Gemini (+ 500ms silence pad)", len(pcm_audio))
                    except Exception as e:
                        logger.error("TTS conversion failed for text input: %s", e)

        except WebSocketDisconnect:
            logger.info(f"Client disconnected: uid={uid}")
        except Exception as e:
            logger.error(f"Upstream error: {e}")

    async def downstream_task():
        """LiveRequestQueue -> ADK Runner -> Client."""
        first_audio_logged = False
        gemini_ready_sent = False
        logger.info("Downstream task started, waiting for events from runner.run_live...")
        try:
            session_obj = await session_service.get_session(
                app_name=APP_NAME, 
                user_id=uid, 
                session_id=session_id
            )
            async for event in runner.run_live(
                user_id=uid,
                session_id=session_id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                # 1. Check for Generative UI updates injected by tools
                # a) Session-state-based events (onboarding/guardian tools)
                session_obj = await session_service.get_session(
                    app_name=APP_NAME, user_id=uid, session_id=session_id
                )
                ui_events = session_obj.state.pop("ui_events", [])

                # b) Global-queue-based events (booking tools — bypasses ADK
                #    session state which doesn't propagate in run_live mode)
                from agents.booking.tools import BOOKING_UI_QUEUE
                booking_events = BOOKING_UI_QUEUE.pop(uid, [])
                ui_events.extend(booking_events)

                if ui_events:
                    logger.info(f"Found {len(ui_events)} UI events to dispatch")
                for ui_event in ui_events:
                    try:
                        await websocket.send_text(json.dumps(ui_event))
                        logger.info(f"Dispatched UI Event: {ui_event['target']}")
                    except Exception as e:
                        logger.error(f"Failed to send UI event: {e}")
                        
                # 2. Check for Voice Settings Change (triggers WS Re-Init)
                new_voice = session_obj.state.pop("new_voice_name", None)
                if new_voice:
                    logger.info(f"Voice changed to {new_voice}. Closing WS (code 4005) to force client re-init.")
                    try:
                        await websocket.close(code=4005, reason="voice_settings_changed")
                    except Exception:
                        pass
                    return  # Break the run_live loop gracefully

                # First event means Gemini Live is connected — tell the client
                if not gemini_ready_sent:
                    try:
                        await websocket.send_text('{"type":"ready"}')
                        gemini_ready_sent = True
                        logger.info("Gemini Live ready signal sent to client")
                    except Exception:
                        pass

                # Serialize ADK event and send to client
                try:
                    # Detect event types for logging
                    has_audio = False
                    has_text = False
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.inline_data:
                                has_audio = True
                            if part.text:
                                has_text = True

                    # Log transcription text for debugging duplication
                    input_tx_text = (
                        event.input_transcription.text
                        if event.input_transcription
                        else None
                    )
                    output_tx_text = (
                        event.output_transcription.text
                        if event.output_transcription
                        else None
                    )
                    # Diagnostic: log every input_transcription so we can confirm speech is recognized
                    if input_tx_text:
                        logger.info(
                            "input_transcription received: %s",
                            repr(input_tx_text)[:120],
                        )
                    # Log only events that indicate model response (audio or turn_complete) to reduce noise
                    if has_audio or event.turn_complete or (output_tx_text and len(output_tx_text) > 20):
                        first_after_audio = bool(upstream_audio_chunks) and (has_audio or event.turn_complete)
                        logger.info(
                            "Response event: audio=%s turn_complete=%s output_tx=%s first_after_speech=%s",
                            has_audio,
                            event.turn_complete,
                            repr(output_tx_text)[:60] if output_tx_text else None,
                            first_after_audio,
                        )


                    event_json = event.model_dump_json(
                        exclude_none=True, by_alias=True
                    )

                    # Log the first audio event's JSON to verify structure
                    if has_audio and not first_audio_logged:
                        logger.info(
                            f"SAMPLE audio event JSON (first 500 chars): "
                            f"{event_json[:500]}"
                        )
                        first_audio_logged = True

                    await websocket.send_text(event_json)

                    # CRITICAL: If turn is complete, ensure we are ready for the next one
                    # Some versions of ADK might need a tiny nudge or state reset here
                    if event.turn_complete:
                        logger.info("Turn complete - session ready for next input")
                        # We don't close the queue, just let the loop continue
                        
                except RuntimeError:
                    # WebSocket already closed — downstream task ends cleanly
                    break
                except Exception as e:
                    logger.error("Failed to send event: %s", e, exc_info=True)
                    break
        except Exception as e:
            logger.exception("Downstream error: %s", e)

    # Run upstream + downstream concurrently
    try:
        await asyncio.gather(
            upstream_task(),
            downstream_task(),
            return_exceptions=True,
        )
    finally:
        # --- Phase 4: Graceful Termination ---
        live_request_queue.close()
        logger.info(f"Session ended: uid={uid}, session={session_id}")


# ---------------------------------------------------------------------------
# Phase 4 Power Feature: Caregiver Approval Workflow
# ---------------------------------------------------------------------------

@app.post("/api/family/plans/{plan_id}/approve")
async def approve_dietary_plan(plan_id: str):
    """Webhook for family members to approve a drafted dietary plan.
    
    In a full production environment, this would verify a caregiver JWT
    and update the Firestore document status from 'draft' to 'approved'.
    For the hackathon, we simulate the approval and could theoretically 
    push a WebSocket status update to the active patient session.
    """
    logger.info(f"Caregiver approved dietary plan: {plan_id}")
    
    # Mocking the Firestore update
    # fs = FirestoreService.get_instance()
    # await fs.update_dietary_plan_status(plan_id, "approved")
    
    return {
        "success": True, 
        "plan_id": plan_id, 
        "new_status": "approved",
        "message": "The dietary plan has been successfully approved by the caregiver."
    }



# ---------------------------------------------------------------------------
# React SPA: Serve Vite build output for production deployment
# ---------------------------------------------------------------------------

REACT_DIR = Path(__file__).parent.parent / "dist"
if REACT_DIR.exists():
    # Serve static assets (JS, CSS, images) from Vite build
    _assets_dir = REACT_DIR / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="react-assets")

    @app.get("/{full_path:path}")
    async def serve_react(full_path: str):
        """Catch-all: serve React SPA for all non-API/non-WS routes."""
        file_path = REACT_DIR / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(REACT_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
