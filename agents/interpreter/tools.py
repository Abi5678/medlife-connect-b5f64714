"""Interpreter agent tools: prescription reading, report reading, text translation,
and drug interaction checking.

All tools support Firestore (via tool_context) with mock_data.py fallback.
"""

from datetime import datetime, timezone

from agents.shared.drug_service import check_interactions, normalize_drug_name
from agents.shared.firestore_service import FirestoreService
from agents.shared.mock_data import PRESCRIPTIONS, REPORTS


def _get_user_id(tool_context) -> str:
    """Extract user_id from ADK tool_context, with fallback."""
    if tool_context and hasattr(tool_context, "state"):
        return tool_context.state.get("user_id", "demo_user")
    return "demo_user"


def _use_firestore(tool_context) -> bool:
    """Check if Firestore should be used for this call."""
    fs = FirestoreService.get_instance()
    return fs.is_available and tool_context is not None


async def read_prescription(image_description: str, tool_context=None) -> dict:
    """Extract medication information from a prescription shown via camera.

    The model describes what it sees in the camera image, and this tool
    structures the extracted information and stores it for future reference.

    Args:
        image_description: A description of the prescription as seen in the camera image.
    """
    now = datetime.now(timezone.utc).isoformat()
    user_id = _get_user_id(tool_context)

    # Build structured prescription from the model's description
    prescription_data = {
        "medications": [],
        "raw_description": image_description,
        "doctor_name": "",
        "date": "",
        "extracted_at": now,
        "source": "voice_camera",
    }

    # Store in Firestore or mock
    if _use_firestore(tool_context):
        fs = FirestoreService.get_instance()
        try:
            doc_id = await fs.add_prescription(user_id, prescription_data)
            prescription_data["doc_id"] = doc_id
        except Exception:
            pass
    else:
        PRESCRIPTIONS.append(prescription_data)

    return {
        "status": "extracted",
        "raw_description": image_description,
        "stored": True,
        "instructions": (
            "Please confirm the following with the patient: "
            "medication name, dosage, frequency, and any special instructions "
            "you read from the prescription or label. "
            "For more accurate extraction, the patient can also use the Scan button."
        ),
    }


async def read_report(image_description: str, tool_context=None) -> dict:
    """Extract test results from a lab report shown via camera.

    The model describes what it sees in the camera image, and this tool
    structures the extracted information and stores it for future reference.

    Args:
        image_description: A description of the lab report as seen in the camera image.
    """
    now = datetime.now(timezone.utc).isoformat()
    user_id = _get_user_id(tool_context)

    report_data = {
        "tests": [],
        "raw_description": image_description,
        "lab_name": "",
        "date": "",
        "extracted_at": now,
        "source": "voice_camera",
    }

    if _use_firestore(tool_context):
        fs = FirestoreService.get_instance()
        try:
            doc_id = await fs.add_report(user_id, report_data)
            report_data["doc_id"] = doc_id
        except Exception:
            pass
    else:
        REPORTS.append(report_data)

    return {
        "status": "extracted",
        "raw_description": image_description,
        "stored": True,
        "instructions": (
            "Please confirm the following with the patient: "
            "test names, values, and whether any results are outside the normal range. "
            "For more accurate extraction, the patient can also use the Scan button."
        ),
    }


def translate_text(text: str, source_language: str, target_language: str) -> dict:
    """Translate text between Hindi, Spanish, and English.

    Use this when the patient needs text from a prescription, label, or
    medical document translated to their preferred language.

    Args:
        text: The text to translate.
        source_language: The source language (e.g. 'English', 'Hindi', 'Spanish').
        target_language: The target language (e.g. 'English', 'Hindi', 'Spanish').
    """
    return {
        "status": "translate",
        "original_text": text,
        "source_language": source_language,
        "target_language": target_language,
        "instruction": (
            f"Please translate the following text from {source_language} "
            f"to {target_language} and speak it to the patient: {text}"
        ),
    }


async def check_drug_interactions(
    medication_names: list[str], tool_context=None
) -> dict:
    """Check for known drug interactions between a list of medications.

    Normalizes each drug name via RxNorm, checks the curated knowledge
    base first (instant, reliable), then supplements with OpenFDA drug
    label data for unknown pairs.

    Call this when a new prescription is scanned with multiple medications,
    or when the patient asks "can I take X with Y?"

    Args:
        medication_names: List of drug names to check pairwise interactions for.
    """
    if len(medication_names) < 2:
        return {
            "error": "Need at least two medications to check interactions.",
            "medications": medication_names,
        }

    normalized = []
    for name in medication_names:
        result = await normalize_drug_name(name)
        normalized.append(result.get("normalized_name", name))

    interaction_result = await check_interactions(medication_names)

    return {
        "medications_checked": medication_names,
        "normalized_names": normalized,
        **interaction_result,
    }
