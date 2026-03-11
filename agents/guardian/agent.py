"""Guardian Agent: medication management, pill verification, vitals, meals, emergency protocol."""

from google.adk.agents import Agent

from agents.shared.constants import LIVE_MODEL
from agents.shared.prompts import GUARDIAN_INSTRUCTION
from agents.guardian.tools import (
    get_medication_schedule,
    log_medication_schedule,
    log_medication_taken,
    verify_pill,
    log_vitals,
    initiate_food_scan,
    confirm_and_save_meal,
    detect_emergency_severity,
    initiate_emergency_protocol,
    initiate_family_call,
)

guardian_agent = Agent(
    name="guardian",
    model=LIVE_MODEL,
    description=(
        "Manages medications, verifies pills via camera, logs vital signs, "
        "tracks meals, handles emergency detection and first-aid protocol, "
        "and places family phone calls. "
        "Use this agent when the user asks about their medication schedule, "
        "wants to verify a pill, report vitals, log food, reports any symptoms, "
        "or wants to call a family member."
    ),
    instruction=GUARDIAN_INSTRUCTION,
    tools=[
        get_medication_schedule,
        log_medication_schedule,
        log_medication_taken,
        verify_pill,
        log_vitals,
        initiate_food_scan,
        confirm_and_save_meal,
        detect_emergency_severity,
        initiate_emergency_protocol,
        initiate_family_call,
    ],
)
