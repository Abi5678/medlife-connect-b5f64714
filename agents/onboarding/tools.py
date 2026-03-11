"""Onboarding Agent tools: restart, voice customization, and real-time UI updates."""

import logging
from agents.shared.firestore_service import FirestoreService

logger = logging.getLogger(__name__)

async def restart_onboarding(tool_context=None) -> dict:
    """Restarts the onboarding session by clearing history.
    
    Must be called if the user says "Let's start over."
    """
    logger.info("Restarting onboarding requested by user.")
    try:
        from app.main import runner  # Delayed import to avoid circular dep
        
        # Use ADK's rewind feature to flush the session
        # Since we're in a tool, we access the runner and clear the current session context
        session_id = tool_context.state.get("session_id")
        if session_id:
            await runner.rewind_async(session_id=session_id)
            
        return {"status": "success", "message": "Session history cleared. Start over."}
    except Exception as e:
        logger.error(f"Failed to restart onboarding: {e}")
        return {"status": "error", "message": str(e)}

async def update_session_voice(voice_name: str, tool_context=None) -> dict:
    """Updates the assigned voice Persona for the conversation.
    
    Valid voice_name options: Fenrir, Aoede, Charon, Kore.
    """
    logger.info(f"Updating session voice to: {voice_name}")
    try:
        # Save to Firestore so it persists across the impending WS reconnect
        uid = "demo_user"
        if tool_context and "user_id" in tool_context.state:
            uid = tool_context.state["user_id"]
            
        fs = FirestoreService.get_instance()
        await fs.save_user_profile(uid, {"voice_name": voice_name})
        
        if tool_context:
            tool_context.state["new_voice_name"] = voice_name
            
        # Emit a UI Event to the frontend
        await emit_ui_update("voice_update", {"voice": voice_name}, tool_context)
            
        return {"status": "success", "message": f"Voice updated to {voice_name}."}
    except Exception as e:
        logger.error(f"Failed to update voice: {e}")
        return {"status": "error", "message": str(e)}

from agents.shared.ui_tools import emit_ui_update


async def complete_onboarding_and_save(name: str, language: str, allergies: list[str], diet: str, emergency_contact_name: str, emergency_contact_phone: str, current_medications: str = "", tool_context=None) -> dict:
    """Saves the user's completed profile and triggers handoff.

    MUST be called only after: (1) you have gathered name, language, allergies, diet,
    medications, emergency contact, and (2) the user has given unambiguous consent.
    Never call with empty or inferred defaults — only after the user has explicitly
    provided or declined each item.
    """
    try:
        uid = tool_context.state.get("user_id", "demo_user")
        fs = FirestoreService.get_instance()
        
        # 1. Save preferences (including persistent onboarding flag)
        # Use display_name and flat emergency fields so Profile UI matches React onboarding
        profile_data = {
            "name": name,
            "display_name": name,
            "language": language,
            "onboarding_complete": True,
            "emergency_contact": [{
                "name": emergency_contact_name,
                "phone": emergency_contact_phone
            }],
            "emergency_contact_name": emergency_contact_name,
            "emergency_contact_phone": emergency_contact_phone,
        }
        await fs.save_user_profile(uid, profile_data)
        
        # 2. Save health restrictions
        await fs.save_health_restrictions(uid, allergies, diet, current_medications)
        
        # 3. Emit Preview UI Event
        await emit_ui_update("profile_preview", {"name": name, "language": language, "diet": diet}, tool_context)
        
        # Set state flag to trigger handoff to Guardian Agent
        if tool_context:
            tool_context.state["onboarding_complete"] = True
            
            # Inject proactive prompt into the new Agent's context so it speaks immediately
            live_queue = tool_context.state.get("live_request_queue")
            if live_queue:
                import logging
                try:
                    from google.genai import types
                    greeting_prompt = (
                        "[SYSTEM: You have just taken over from the Onboarding agent. "
                        f"Greet the patient softly by name ({name}) and ask if they need help "
                        "setting any medication reminders or checking vitals right now.]"
                    )
                    content = types.Content(parts=[types.Part(text=greeting_prompt)])
                    live_queue._queue.put_nowait(content)
                    logging.info("Injected proactive handoff greeting into the live queue.")
                except Exception as e:
                    logging.error(f"Failed to push proactive greeting: {e}")

        return {"status": "success", "message": "Profile saved. Ready to handoff."}
    except Exception as e:
        return {"status": "error", "message": f"Save failed: {e}"}

