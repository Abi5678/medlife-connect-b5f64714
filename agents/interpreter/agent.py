"""Interpreter Agent: translation, prescription/label reading, drug interaction checks."""

from google.adk.agents import Agent

from agents.shared.constants import LIVE_MODEL
from agents.shared.prompts import INTERPRETER_INSTRUCTION
from agents.interpreter.tools import (
    check_drug_interactions,
    read_prescription,
    read_report,
    translate_text,
)

interpreter_agent = Agent(
    name="interpreter",
    model=LIVE_MODEL,
    description=(
        "Handles language translation between Hindi, Spanish, English, and "
        "Kannada, reads prescriptions or medication labels shown via camera, "
        "reads lab reports, and checks for drug interactions. "
        "Use this agent when the user asks to translate something, read a "
        "prescription, understand a medication label, read a lab report, or "
        "check if their medications interact with each other."
    ),
    instruction=INTERPRETER_INSTRUCTION,
    tools=[read_prescription, read_report, translate_text, check_drug_interactions],
)
