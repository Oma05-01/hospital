import os
import json
import logging
from datetime import datetime
from groq import Groq, AsyncGroq
from typing import List, Generator
from dotenv import load_dotenv
from capabilities import scope_rule

# --- 1. IMPORT OUR DYNAMIC TOOLS ---
from tools import ALL_TOOLS, TOOL_ROUTER
# Load the .env file so we can see the GROQ_API_KEY
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GenerationConfig:
    """Helper class to hold settings like temperature and max tokens."""
    def __init__(self, temperature: float = 0.1, max_tokens: int = 1024):
        self.temperature = temperature
        self.max_tokens = max_tokens


class InferenceEngine:
    def __init__(self):
        self.ready = False
        self.client = None
        # The 70B model is the "Specialist" brain
        self.model_id = "llama-3.3-70b-versatile"

    def load(self) -> None:
        logger.info("Connecting to Groq API...")

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY environment variable is missing in .env!")
            return

        self.client = Groq(api_key=api_key)
        self.ready = True
        logger.info(f"Connected to Groq. Model set to {self.model_id}")

    def generate_stream(self, prompt: str, patient_name: str, history: List, context: str, domain: str, cfg: GenerationConfig,
                        patient_username: str = "", auth_token: str = None ) -> Generator[str, None, None]:

        from datetime import datetime
        current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

        if not self.ready:
            yield json.dumps({"summary": "Error: Engine not loaded.", "items": []})
            return

        # Build the System Message with our relaxed RAG context
        system_msg = (
            "You are a highly professional, warm, and human-like medical desk assistant.\n"
            f"The current date and time is {current_time}.You MUST use this to determine if an event is in the past or future\n"
            f"IMPORTANT CONTEXT: You are speaking with {patient_name} (username: {patient_username}). If their name is literally 'Patient', just call them by their username. Do NOT tell them their name is 'Patient'.\n"
            "When referring to doctors, ALWAYS capitalize their names and add 'Dr.' (e.g., Dr. Henru).\n\n"

            f"{scope_rule()}\n\n"

            "First, read the provided context. If the context contains the answer, use it. "
            "If the context does NOT contain the answer, answer naturally using your general knowledge "
            "(you ARE allowed to tell the user the current time, day, or date if they ask).\n\n"

            "CRITICAL PERSONA RULE: You MUST NEVER mention 'the context', 'my database', 'tools', "
            "'functions', or your AI nature to the user. Speak naturally like a real human receptionist.\n\n"

            "CRITICAL CONVERSATION RULE: If the user says 'thank you', 'okay', 'wait', or expresses frustration, you MUST respond with a short, warm acknowledgment and STOP. Do not ask any questions at all.\n"
            "Example for 'thank you': 'You are very welcome! Have a great day.'\n"
            "Example for 'hold on': 'Of course, take your time. I will be right here.'\n"
            "Example for frustration: 'I apologize for the confusion. Let me know how I can better assist you.'\n\n"

            "CRITICAL APPOINTMENT LOGIC:\n"
            "1. When looking at database results, ALWAYS compare the appointment date to the current date.\n"
            "2. If an appointment is in the PAST and its status is 'Pending' (or is_confirmed is false), DO NOT call it 'upcoming'. Inform the user: 'You had an appointment requested for [Date] but it was never approved by your doctor.' Then, ask if they would like to book a new appointment.\n"
            "3. Only use the word 'upcoming' for dates in the FUTURE.\n\n"
            
            "--- APPOINTMENT REQUEST PROTOCOL (STRICT ORDER OF OPERATIONS) ---\n"
            "CRITICAL TRIGGER RULE: ONLY execute this protocol if the user EXPLICITLY asks to book, "
            "schedule, or create a new appointment. If they ask 'who is my doctor?' or 'do I have "
            "appointments?', use your tools to answer — do NOT execute this protocol.\n"
            "STEP 1: Gather Doctor, Day, and Time. Ask if any are missing.\n"
            "STEP 2: Verify the doctor is available at that exact time using your tools.\n"
            "STEP 3: ONLY AFTER you have confirmed availability, you may trigger the secure UI authentication modal using the JSON 'action' block.\n\n"
            "CRITICAL WHEN TRIGGERING AUTH: When you output the 'REQUIRE_AUTH' action block, your 'summary' message MUST direct the user to the screen. Tell them: 'That time is available! Please complete the secure authorization prompt on your screen to submit your request for review.'\n"
            "DO NOT say the request 'has been submitted' yet, because they still need to enter their code.\n"
            "Format scheduled_time strictly as YYYY-MM-DDTHH:MM.\n\n"

            "CRITICAL RULE: Respond ONLY in this exact JSON schema:\n"
            '{"summary": "Your main response.", "items": [], '
            '"action": {"type": "REQUIRE_AUTH", "target": "Doctor Name", "scheduled_time": "YYYY-MM-DDTHH:MM"}}\n'
            "Omit the 'action' key entirely unless you are confirming a new appointment booking.\n\n"

            "STRICT SCHEMA RULES:\n"
            "- 'items' array: ONLY use this array if you need to present a list of MULTIPLE distinct items (like multiple appointments, clinic capabilities, or lab results). DO NOT use this array for a single piece of information (like one doctor's name) that is already stated in the 'summary'. Leave it empty [] if a list is unnecessary.\n"
            "- 'action' block: For 'target', you MUST use the EXACT name retrieved from the database. NEVER invent last names and NEVER add the words 'human', 'Dr.', or 'Doctor'.\n\n"

            f"--- CONTEXT ---\n{context}"
        )

        messages = [{"role": "system", "content": system_msg}]

        # Add conversation history
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add the current user question
        messages.append({"role": "user", "content": prompt})

        try:
            # HOP 1: Ask Llama-3 if it needs a tool (stream=False to allow JSON/Tool parsing)
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                tools=ALL_TOOLS,  # <-- Passes all 7 tools dynamically
                tool_choice="auto",
                stream=False
            )

            response_message = response.choices[0].message

            # Did the AI decide to use a tool?
            if response_message.tool_calls:
                tool_call = response_message.tool_calls[0]
                tool_name = tool_call.function.name

                # --- THE DYNAMIC ROUTER ---
                tool_func = TOOL_ROUTER.get(tool_name)

                if tool_func:
                    # 1. Parse the JSON arguments Llama-3 generated (WITH THE SAFETY NET)
                    raw_args = tool_call.function.arguments
                    args = json.loads(raw_args) if raw_args else {}
                    if args is None:
                        args = {}

                    # 2. Execute the function dynamically using kwargs (**args)
                    if "patient_username" in tool_func.__code__.co_varnames:
                        args["patient_username"] = patient_username

                    if "auth_token" in tool_func.__code__.co_varnames:
                        args["auth_token"] = auth_token

                    tool_result = tool_func(**args)

                    if hasattr(response_message, "model_dump"):
                        messages.append(response_message.model_dump(exclude_none=True))
                    else:
                        messages.append(dict(response_message))

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(tool_result)  # Ensure the result is a clean string
                    })

                    # 4. FIX: Dynamic System Note (Forces the 70B model to read Bing Search results)
                    note_content = (
                        "System Note: Based on the live web search results provided above, extract the facts to answer the user's query accurately. "
                        "Do not state that you lack information if the data is present in the search results. Respond ONLY with a JSON object matching the schema."
                    ) if tool_name == "execute_web_search" else (
                        "System Note: Based on the database results above, answer my query. "
                        "Respond ONLY with a JSON object matching the schema."
                    )

                    messages.append({
                        "role": "user",
                        "content": (
                            f"{note_content}\n\n"
                            "CRITICAL SCHEMA RULE:\n"
                            "- Respond ONLY with a JSON object.\n"
                            "- Format: {\"summary\": \"...\", \"items\": [], \"action\": null}\n"
                            "- ONLY populate the 'action' block as {\"type\": \"REQUIRE_AUTH\", \"target\": \"Name\", \"scheduled_time\": \"YYYY-MM-DDTHH:MM\"} IF AND ONLY IF the user explicitly asked to book an appointment AND you have confirmed a specific date and time. Otherwise, 'action' MUST be null."
                        )
                    })

                    # HOP 2: Now that it has the DB data, stream the final JSON response
                    final_response = self.client.chat.completions.create(
                        model=self.model_id,
                        messages=messages,
                        temperature=cfg.temperature,
                        max_tokens=cfg.max_tokens,
                        stream=False,
                        response_format={"type": "json_object"}
                    )

                    # THE FIX: Stop replacing '\n'! Let json.dumps safely escape the markdown formatting.
                    raw_content = final_response.choices[0].message.content
                    try:
                        safe_json = json.dumps(json.loads(raw_content))
                        yield safe_json
                    except json.JSONDecodeError:
                        yield json.dumps({"summary": raw_content, "items": []})
                    return
                else:
                    yield json.dumps({"summary": f"Error: Tool {tool_name} not found in router.", "items": []})
                    return

            # If no tools were called, yield the Hop 1 response normally
            raw_content = response_message.content
            try:
                # Squash the multi-line JSON into a single line safely
                safe_json = json.dumps(json.loads(raw_content))
                yield safe_json
            except json.JSONDecodeError:
                # FIX: Preserve the markdown newlines here as well!
                yield json.dumps({"summary": raw_content, "items": []})

        except Exception as e:
            logger.error(f"Groq API Error: {e}")
            yield json.dumps({"summary": f"System Error: {str(e)}", "items": []})


# Global instance
engine = InferenceEngine()