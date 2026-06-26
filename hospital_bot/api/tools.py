# hospital_bot/api/tools.py
import os
import httpx
from pydantic import BaseModel, Field
from duckduckgo_search import DDGS

# --- CONFIGURATION ---
DJANGO_PORT = os.environ.get("DJANGO_PORT", "8000")
# Falls back to localhost if the .env variable is missing
DJANGO_BASE_URL = os.environ.get("DJANGO_API_URL", f"http://localhost:{DJANGO_PORT}/api/bot")


# --- 1. SCHEMAS ---
class CheckAvailabilitySchema(BaseModel):
    doctor_name: str = Field(default="", description="The last name or username of the doctor.")
    day_of_week: str = Field(default="", description="The day of the week in lowercase.")

class GetLabResultsSchema(BaseModel):
    patient_id: int = Field(..., description="The unique numerical ID of the patient.")

class CheckInventorySchema(BaseModel):
    item_name: str = Field(..., description="The name of the medical supply.")

class DispatchEmergencySchema(BaseModel):
    patient_id: int = Field(..., description="The unique ID of the patient.")
    location: str = Field(..., description="The physical address of the emergency.")
    emergency_type: str = Field(..., description="A brief description of the medical emergency.")

class SendNotificationSchema(BaseModel):
    recipient_username: str = Field(..., description="The username of the recipient.")
    message: str = Field(..., description="The content of the notification.")
    notification_type: str = Field(..., description="'appointment', 'bill_payment', or 'emergency'.")
    is_urgent: bool = Field(..., description="True ONLY if it is a medical emergency.")

class ExpiringCertsSchema(BaseModel):
    days: int = Field(default=30, description="Number of days to look ahead for expiring certifications.")


# --- 2. TOOL DEFINITIONS (For Groq) ---
ALL_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_doctor_availability",
            "description": "Fetch the patient's assigned doctors, their names, OR check a specific doctor's shift times.",
            "parameters": CheckAvailabilitySchema.model_json_schema()
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_patient_appointments",
            "description": "Use this tool whenever a user asks about their existing, pending, or scheduled appointments.",
            "parameters": {
                "type": "object",
                "properties": {} # No parameters needed from the AI, the backend injects the username automatically!
            }
        }
    },
    {
        "type": "function",
        "function": {"name": "get_patient_lab_results", "description": "Fetch recent lab results.", "parameters": GetLabResultsSchema.model_json_schema()}
    },
    {
        "type": "function",
        "function": {"name": "check_medical_inventory", "description": "Check supply stock levels.", "parameters": CheckInventorySchema.model_json_schema()}
    },
    {
        "type": "function",
        "function": {"name": "dispatch_emergency_service", "description": "Dispatch an ambulance.", "parameters": DispatchEmergencySchema.model_json_schema()}
    },
    {
        "type": "function",
        "function": {"name": "send_system_notification", "description": "Push a notification to a user.", "parameters": SendNotificationSchema.model_json_schema()}
    },
    {
        "type": "function",
        "function": {"name": "get_hospital_metrics", "description": "Fetch live hospital performance metrics.", "parameters": {"type": "object", "properties": {}}}
    },
    {
        "type": "function",
        "function": {"name": "check_expiring_certifications", "description": "Check for staff certifications expiring soon.", "parameters": ExpiringCertsSchema.model_json_schema()}
    },
    {
        "type": "function",
        "function": {
            "name": "execute_web_search",
            "description": "Searches highly verified medical authorities (WHO, CDC, NIH, NCDC) for up-to-date health information and news.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The precise search query to look up on the internet."
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# --- 3. EXECUTION FUNCTIONS ---
def execute_check_availability(doctor_name: str = "", day_of_week: str = "", patient_username: str = "", auth_token: str = None):
    if not patient_username:
        return "SYSTEM ERROR: Patient identity is unknown. Cannot fetch assigned records."

    try:

        headers = {}
        if auth_token:
            # Clean up the token string if it already contains 'Bearer' to prevent duplication
            clean_token = auth_token.replace("Bearer ", "").strip()
            headers["Authorization"] = f"Bearer {clean_token}"

        with httpx.Client() as client:
            # Hit our new patient-filtered endpoint!
            url = f"{DJANGO_BASE_URL}/my-doctors/?username={patient_username}&day={day_of_week}"
            res = client.get(url, headers=headers, timeout=5.0)

            if res.status_code == 401:
                return "SYSTEM ERROR: Authentication failed or token expired."
            elif res.status_code != 200:
                # Truncate the response text to 200 characters maximum!
                # This drops massive HTML walls while preserving short, useful error snippets.
                clean_error = res.text[:200] if res.text else "No error details provided."
                return f"ERROR: Backend returned status code {res.status_code}. Details: {clean_error}"
            return str(res.json())
    except Exception as e:
        return f"CONNECTION ERROR: {str(e)}"

def execute_get_lab_results(patient_id: int):
    try:
        with httpx.Client() as client:
            res = client.get(f"{DJANGO_BASE_URL}/lab-results/?patient_id={patient_id}", timeout=5.0)
            return str(res.json()) if res.status_code == 200 else f"ERROR: {res.text}"
    except Exception as e: return f"CONNECTION ERROR: {str(e)}"

def execute_check_inventory(item_name: str):
    try:
        with httpx.Client() as client:
            res = client.get(f"{DJANGO_BASE_URL}/inventory/?item={item_name}", timeout=5.0)
            return str(res.json()) if res.status_code == 200 else f"ERROR: {res.text}"
    except Exception as e: return f"CONNECTION ERROR: {str(e)}"

def execute_dispatch_emergency(patient_id: int, location: str, emergency_type: str):
    try:
        with httpx.Client() as client:
            res = client.post(f"{DJANGO_BASE_URL}/emergency/", json={"patient_id": patient_id, "location": location, "emergency_type": emergency_type}, timeout=5.0)
            return str(res.json()) if res.status_code == 201 else f"ERROR: {res.text}"
    except Exception as e: return f"CONNECTION ERROR: {str(e)}"

def execute_send_notification(recipient_username: str, message: str, notification_type: str, is_urgent: bool):
    try:
        with httpx.Client() as client:
            res = client.post(f"{DJANGO_BASE_URL}/notification/", json={"recipient_username": recipient_username, "message": message, "notification_type": notification_type, "is_urgent": is_urgent}, timeout=5.0)
            return str(res.json()) if res.status_code == 201 else f"ERROR: {res.text}"
    except Exception as e: return f"CONNECTION ERROR: {str(e)}"

def execute_get_metrics():
    try:
        with httpx.Client() as client:
            res = client.get(f"{DJANGO_BASE_URL}/metrics/", timeout=5.0)
            return str(res.json()) if res.status_code == 200 else f"ERROR: {res.text}"
    except Exception as e: return f"CONNECTION ERROR: {str(e)}"

def execute_check_certs(days: int = 30):
    try:
        with httpx.Client() as client:
            res = client.get(f"{DJANGO_BASE_URL}/expiring-certs/?days={days}", timeout=5.0)
            return str(res.json()) if res.status_code == 200 else f"ERROR: {res.text}"
    except Exception as e: return f"CONNECTION ERROR: {str(e)}"


def execute_web_search(query: str, patient_username: str = "", auth_token: str = None):
    """
    Queries the live internet (restricted to trusted medical sites) and returns the top 3 results.
    """
    # 1. Define your whitelist of highly verified medical domains
    # (Added NCDC since you are building for the Nigerian market, alongside WHO and CDC)
    trusted_domains = [
        "who.int",
        "cdc.gov",
        "nih.gov",
        "ncdc.gov.ng",
        "mayoclinic.org"
    ]

    # 2. Format the domains into a DuckDuckGo search operator string
    # Result: "(site:who.int OR site:cdc.gov OR site:nih.gov OR site:ncdc.gov.ng OR site:mayoclinic.org)"
    site_restrictions = " OR ".join([f"site:{domain}" for domain in trusted_domains])

    # 3. Force the restriction onto the AI's query
    secure_query = f"{query} ({site_restrictions})"

    try:
        with DDGS() as ddgs:
            # Pass the secure_query instead of the raw query
            results = [r for r in ddgs.text(secure_query, max_results=3)]

            if not results:
                return f"No verified medical results found on trusted sites (WHO, CDC, NIH, etc.) for '{query}'."

            formatted_results = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            return f"Verified Web Search Results for '{query}':\n{formatted_results}"

    except Exception as e:
        return f"WEB SEARCH ERROR: {str(e)}"

def execute_check_appointments(patient_username: str = "", auth_token: str = None):
    if not patient_username:
        return "SYSTEM ERROR: Patient identity unknown."

    try:
        headers = {}
        if auth_token:
            clean_token = auth_token.replace("Bearer ", "").strip()
            headers["Authorization"] = f"Bearer {clean_token}"

        with httpx.Client() as client:
            # Hit our new endpoint
            url = f"{DJANGO_BASE_URL}/my-appointments/?username={patient_username}"
            res = client.get(url, headers=headers, timeout=5.0)

            if res.status_code == 200:
                return str(res.json())
            else:
                return f"ERROR: Could not fetch appointments. Status {res.status_code}."
    except Exception as e:
        print("comign from here", flush=True)
        return f"CONNECTION ERROR: {str(e)}"


# --- 4. TOOL ROUTER ---
# This dictionary makes executing tools dynamic in inference.py
TOOL_ROUTER = {
    "check_doctor_availability": execute_check_availability,
    "execute_web_search": execute_web_search,
    "get_patient_lab_results": execute_get_lab_results,
    "check_medical_inventory": execute_check_inventory,
    "dispatch_emergency_service": execute_dispatch_emergency,
    "send_system_notification": execute_send_notification,
    "get_hospital_metrics": execute_get_metrics,
    "check_expiring_certifications": execute_check_certs,
"check_patient_appointments": execute_check_appointments,
}