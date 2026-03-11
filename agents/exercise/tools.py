"""Exercise agent tools: session management, progress logging, and history."""

import json
import uuid
from datetime import datetime, timezone

from agents.shared.firestore_service import FirestoreService
from agents.shared.ui_tools import emit_ui_update

# #region debug instrumentation
import os as _os
import logging as _logging
_debug_logger = _logging.getLogger("exercise_tools_debug")

def _dbg(tool: str, message: str, data: dict, hypothesis_id: str = ""):
    import time
    payload = {"sessionId": "5959a7", "location": f"tools.py:{tool}", "message": message, "data": data, "timestamp": int(time.time() * 1000), "hypothesisId": hypothesis_id}
    _debug_logger.info("[DEBUG-5959a7] %s", json.dumps(payload))
    try:
        base = _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__)))
        path = _os.path.join(base, ".cursor", "debug-5959a7.log")
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion


EXERCISE_PHASES = [
    {"phase": "Breathing", "exercises": ["Box Breathing", "Deep Belly Breathing"]},
    {"phase": "Stretches", "exercises": ["Neck Rolls", "Shoulder Shrugs", "Seated Side Bend", "Wrist & Ankle Circles"]},
    {"phase": "Yoga", "exercises": ["Mountain Pose", "Tree Pose", "Warrior I", "Seated Cat-Cow", "Child's Pose"]},
    {"phase": "Cool-Down", "exercises": ["Seated Forward Fold", "Gentle Spinal Twist", "Final Relaxation"]},
]

TOTAL_EXERCISES = 14

# Global progress store — run_live mode may not propagate session state reliably.
# Key: user_id, Value: last logged exercise_number (1-14)
EXERCISE_PROGRESS: dict[str, int] = {}

# Ordered list for get_next_exercise
EXERCISE_LIST = [
    ("Box Breathing", 35),
    ("Deep Belly Breathing", 60),
    ("Neck Rolls", 30),
    ("Shoulder Shrugs", 30),
    ("Seated Side Bend", 60),
    ("Wrist & Ankle Circles", 60),
    ("Mountain Pose", 30),
    ("Tree Pose", 45),
    ("Warrior I", 45),
    ("Seated Cat-Cow", 30),
    ("Child's Pose", 30),
    ("Seated Forward Fold", 30),
    ("Gentle Spinal Twist", 30),
    ("Final Relaxation", 60),
]


def get_next_exercise(last_completed_number: int, tool_context=None) -> dict:
    """Returns the next exercise to do. Call this after log_exercise_progress to know what comes next.

    Args:
        last_completed_number: The exercise number you just logged (1-14). Use 0 for the first exercise.
    """
    _dbg("get_next_exercise", "entry", {"last_completed_number": last_completed_number}, "H1")
    uid = _get_user_id(tool_context)
    highest_logged = EXERCISE_PROGRESS.get(uid, 0)
    # Guardrail: never go backwards. If agent passes a smaller number than already logged,
    # use the highest so we always advance through the list (avoids Box Breathing loop).
    effective_last = max(last_completed_number, highest_logged)
    if effective_last >= TOTAL_EXERCISES:
        return {"next": None, "message": "Session complete. Call complete_exercise_session."}
    idx = effective_last  # 0-based index into EXERCISE_LIST
    name, duration = EXERCISE_LIST[idx]
    out = {"exercise_name": name, "exercise_number": idx + 1, "duration_seconds": duration, "message": f"Next: {name} ({duration}s). Introduce this one — do not skip."}
    _dbg("get_next_exercise", "exit", {"effective_last": effective_last, "highest_logged": highest_logged, **out}, "H1")
    return out


def _get_user_id(tool_context) -> str:
    if tool_context and hasattr(tool_context, "state"):
        return tool_context.state.get("user_id", "demo_user")
    return "demo_user"


def _use_firestore(tool_context) -> bool:
    fs = FirestoreService.get_instance()
    return fs.is_available and tool_context is not None


def _get_phase_for_exercise(exercise_number: int) -> str:
    count = 0
    for phase in EXERCISE_PHASES:
        count += len(phase["exercises"])
        if exercise_number <= count:
            return phase["phase"]
    return "Cool-Down"


def _exercise_name_to_number(name: str) -> int:
    """Return 1-based exercise number for name, or 0 if unknown."""
    for i, (n, _) in enumerate(EXERCISE_LIST):
        if n == name:
            return i + 1
    return 0


def await_exercise_completion(
    exercise_name: str,
    duration_seconds: int = 30,
    tool_context=None,
) -> dict:
    """Updates the frontend UI to start the purely-visual timer for the user.

    The duration is only for the on-screen countdown; the agent decides when
    the exercise is done by watching the camera feed.
    """
    _dbg("await_exercise_completion", "entry", {"exercise_name": exercise_name, "duration_seconds": duration_seconds}, "H1")
    actual_duration = max(duration_seconds, 15)

    emit_ui_update(
        "exercise_timer_started",
        {"exercise_name": exercise_name, "duration_seconds": actual_duration},
        tool_context,
    )

    return {
        "status": "timer_started",
        "message": "UI updated. Guide the user, watch them via camera, and wrap up when they finish.",
    }


def notify_timer_complete(exercise_name: str, tool_context=None) -> dict:
    """Stub — kept for imports. Agent uses camera to detect completion."""
    return {"status": "ok", "message": "Acknowledged."}


def wait_for_user_confirmation(tool_context=None) -> dict:
    """Call after asking "Are you ready for the next one?" — signals you must end your turn and wait for the user."""
    _dbg("wait_for_user_confirmation", "called", {}, "H2")
    return {
        "status": "waiting",
        "message": "STOP SPEAKING NOW. End your turn. Do not say another word. Wait for the user to say yes, ready, or let's go. When they do, call log_exercise_progress(exercise_name, exercise_number, notes) for the exercise you just completed, then get_next_exercise(last_completed) to get the NEXT exercise, and introduce that new exercise once.",
    }


def start_exercise_session(tool_context=None) -> dict:
    """Begin a new 10-minute wellness session. Call this when the user is ready to start exercising.

    Creates a session record and notifies the frontend to show the exercise UI.
    """
    _dbg("start_exercise_session", "entry", {}, "H1")
    session_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)

    session_data = {
        "session_id": session_id,
        "started_at": now.isoformat(),
        "completed_at": None,
        "duration_minutes": 0,
        "exercises": [],
        "posture_score": 0,
    }

    # Store session_id in state for subsequent tool calls
    uid = _get_user_id(tool_context)
    if tool_context and hasattr(tool_context, "state"):
        tool_context.state["exercise_session_id"] = session_id
        tool_context.state["exercises_completed"] = 0  # no exercises logged yet
    EXERCISE_PROGRESS[uid] = 0  # run_live: session state may not propagate

    emit_ui_update("exercise_session_started", {
        "session_id": session_id,
        "total_exercises": TOTAL_EXERCISES,
        "phases": [p["phase"] for p in EXERCISE_PHASES],
    }, tool_context)

    return {
        "session_id": session_id,
        "total_exercises": TOTAL_EXERCISES,
        "message": "Session started! Let's begin with Phase 1: Breathing.",
    }


def log_exercise_progress(
    exercise_name: str,
    exercise_number: int,
    posture_notes: str = "",
    completed: bool = True,
    tool_context=None,
) -> dict:
    """Log completion of the exercise. Call after the user confirms they are ready to move on."""
    _dbg("log_exercise_progress", "entry", {"exercise_name": exercise_name, "exercise_number": exercise_number}, "H3")
    uid = _get_user_id(tool_context)
    if tool_context and hasattr(tool_context, "state"):
        tool_context.state["exercises_completed"] = exercise_number
    EXERCISE_PROGRESS[uid] = exercise_number
    phase = _get_phase_for_exercise(exercise_number)

    emit_ui_update("exercise_pose_change", {
        "exercise_name": exercise_name,
        "exercise_number": exercise_number,
        "total": TOTAL_EXERCISES,
        "posture_notes": posture_notes,
        "phase": phase,
        "completed": completed,
    }, tool_context)

    return {
        "logged": True,
        "message": "Progress logged. You may now introduce the next exercise.",
    }


def complete_exercise_session(
    exercises_completed: int,
    overall_posture_notes: str = "",
    tool_context=None,
) -> dict:
    """Finalize the session with summary. Call after the last exercise OR when the user interrupts to stop.

    Use when: (a) user completes exercise 14 (Final Relaxation), or (b) user says "stop", "end session",
    "that's enough", etc. mid-session. Provide the ACTUAL count of exercises completed — never use 14
    unless you actually coached all 14. If you only did Box Breathing, use 1.
    """
    _dbg("complete_exercise_session", "entry", {"exercises_completed": exercises_completed}, "H4")
    session_id = None
    uid = _get_user_id(tool_context)
    last_logged = EXERCISE_PROGRESS.get(uid, 0)  # run_live: use global store
    if tool_context and hasattr(tool_context, "state"):
        last_logged = max(last_logged, tool_context.state.get("exercises_completed", 0))
        session_id = tool_context.state.get("exercise_session_id")
    # Reject wrong counts: exercises_completed can be at most last_logged + 1 (current exercise just finished)
    if exercises_completed > last_logged + 1:
        return {
            "blocked": True,
            "error": (
                f"BLOCKED: You claimed {exercises_completed} exercises completed, but you've only logged {last_logged}. "
                f"Use the ACTUAL count. If you only did Box Breathing, use 1. Never use 14 unless you completed all 14."
            ),
        }

    # Compute a simple posture score based on notes
    posture_score = min(100, 60 + exercises_completed * 3)
    if overall_posture_notes and "great" in overall_posture_notes.lower():
        posture_score = min(100, posture_score + 10)

    encouragement = "Wonderful session! You're doing great things for your health."
    if exercises_completed >= 12:
        encouragement = "Outstanding! You completed almost the entire routine. Your body thanks you!"
    elif exercises_completed >= 8:
        encouragement = "Great effort! You did more than half the routine. Every bit counts!"

    emit_ui_update("exercise_session_completed", {
        "session_id": session_id,
        "exercises_completed": exercises_completed,
        "total_exercises": TOTAL_EXERCISES,
        "duration_minutes": 10,
        "posture_score": posture_score,
        "posture_summary": overall_posture_notes,
        "encouragement": encouragement,
    }, tool_context)

    return {
        "session_id": session_id,
        "exercises_completed": exercises_completed,
        "duration_minutes": 10,
        "posture_score": posture_score,
        "encouragement": encouragement,
        "summary": f"Completed {exercises_completed}/{TOTAL_EXERCISES} exercises. Posture score: {posture_score}/100.",
    }


def get_exercise_history(tool_context=None) -> dict:
    """Get the user's past exercise sessions for motivation and tracking.

    Returns the last 10 sessions with date, duration, exercises completed, and posture scores.
    """
    # Mock data fallback for demo
    return {
        "sessions": [
            {"date": "2026-03-07", "duration_minutes": 10, "exercises_completed": 14, "posture_score": 85},
            {"date": "2026-03-05", "duration_minutes": 10, "exercises_completed": 12, "posture_score": 78},
        ],
        "total_sessions": 2,
    }
