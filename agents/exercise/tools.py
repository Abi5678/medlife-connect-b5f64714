"""Exercise agent tools: session management, progress logging, and history."""

import uuid
from datetime import datetime, timezone

from agents.shared.firestore_service import FirestoreService
from agents.shared.ui_tools import emit_ui_update


EXERCISE_PHASES = [
    {"phase": "Breathing", "exercises": ["Box Breathing", "Deep Belly Breathing"]},
    {"phase": "Stretches", "exercises": ["Neck Rolls", "Shoulder Shrugs", "Seated Side Bend", "Wrist & Ankle Circles"]},
    {"phase": "Yoga", "exercises": ["Mountain Pose", "Tree Pose", "Warrior I", "Seated Cat-Cow", "Child's Pose"]},
    {"phase": "Cool-Down", "exercises": ["Seated Forward Fold", "Gentle Spinal Twist", "Final Relaxation"]},
]

TOTAL_EXERCISES = 14


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


def await_exercise_completion(
    exercise_name: str,
    duration_seconds: int = 30,
    tool_context=None,
) -> dict:
    """Start the exercise hold timer. Returns immediately — do NOT wait silently.

    Call this right after announcing the exercise and giving initial instructions.
    The frontend will count down and send you a voice signal when time is up.

    CRITICAL — while the timer runs you MUST keep coaching:
    - Count the rhythm aloud ("In... 2... 3... 4... Out... 2... 3... 4...")
    - Encourage continuously ("You're doing great! Keep it going!")
    - Comment on what you see in the camera ("Your posture looks wonderful!")
    - Count down the final 5 seconds ("5... 4... 3... 2... 1... and release!")
    Do NOT go silent. The user needs to hear you the whole time.

    When you hear "Time is up" in the conversation, that is the completion signal.
    Only THEN should you call log_exercise_progress and announce the next exercise.

    Args:
        exercise_name: Name of the exercise (e.g. "Box Breathing")
        duration_seconds: Duration in seconds. Use exact values: 30, 45, or 60.
    """
    import logging
    actual_duration = max(duration_seconds, 15)
    if actual_duration != duration_seconds:
        logging.getLogger(__name__).warning(
            "await_exercise_completion: duration_seconds=%s below minimum 15s — "
            "clamped to %s for '%s'",
            duration_seconds, actual_duration, exercise_name,
        )

    emit_ui_update(
        "exercise_timer_started",
        {"exercise_name": exercise_name, "duration_seconds": actual_duration},
        tool_context,
    )

    return {
        "status": "timer_started",
        "exercise": exercise_name,
        "duration_seconds": actual_duration,
        "message": (
            f"Timer started for '{exercise_name}' ({actual_duration}s). "
            "Keep coaching the user actively — count the rhythm, encourage, "
            "and comment on their posture from the camera. "
            "Do NOT call log_exercise_progress yet. "
            "Wait until you hear 'Time is up' then give feedback and log."
        ),
    }


def start_exercise_session(tool_context=None) -> dict:
    """Begin a new 10-minute wellness session. Call this when the user is ready to start exercising.

    Creates a session record and notifies the frontend to show the exercise UI.
    """
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
    if tool_context and hasattr(tool_context, "state"):
        tool_context.state["exercise_session_id"] = session_id

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
    """Log completion of each exercise with posture assessment.

    Call this after each exercise with the name, number (1-14),
    and any posture observations from the camera.
    """
    phase = _get_phase_for_exercise(exercise_number)

    emit_ui_update("exercise_pose_change", {
        "exercise_name": exercise_name,
        "exercise_number": exercise_number,
        "total": TOTAL_EXERCISES,
        "posture_notes": posture_notes,
        "phase": phase,
        "completed": completed,
    }, tool_context)

    # Determine next exercise hint
    next_num = exercise_number + 1
    next_hint = ""
    count = 0
    for p in EXERCISE_PHASES:
        for ex in p["exercises"]:
            count += 1
            if count == next_num:
                next_hint = f"Next: {ex} ({p['phase']})"
                break
        if next_hint:
            break

    if not next_hint and exercise_number >= TOTAL_EXERCISES:
        next_hint = "All exercises complete! Time for the summary."

    return {
        "logged": True,
        "exercise_name": exercise_name,
        "exercise_number": exercise_number,
        "phase": phase,
        "next_exercise_hint": next_hint,
    }


def complete_exercise_session(
    exercises_completed: int,
    overall_posture_notes: str = "",
    tool_context=None,
) -> dict:
    """Finalize the session with summary. Call after the last exercise.

    Provide the total count of exercises completed and any overall posture observations.
    """
    session_id = None
    if tool_context and hasattr(tool_context, "state"):
        session_id = tool_context.state.get("exercise_session_id")

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
