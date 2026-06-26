import os
from google.oauth2 import service_account
from googleapiclient.discovery import build


class GoogleCalendarEngine:
    # The scope tells Google we want full read/write access to calendars
    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self):
        """Initialize the engine using the downloaded JSON key."""
        # Assuming gcp_credentials.json is in your Django base directory
        self.creds_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gcp_credentials.json')

        if not os.path.exists(self.creds_path):
            raise FileNotFoundError("Google Credentials JSON not found. Please add gcp_credentials.json")

        self.credentials = service_account.Credentials.from_service_account_file(
            self.creds_path, scopes=self.SCOPES
        )

        # Build the actual API service
        self.service = build('calendar', 'v3', credentials=self.credentials)

    def provision_doctor_calendar(self, doctor_name, doctor_email):
        """
        Creates a new clinic calendar for the doctor and shares it with their email.
        Returns the new Calendar ID.
        """
        # 1. Create the Calendar
        calendar_meta = {
            'summary': f'Lagos Horizon - Dr. {doctor_name}',
            'timeZone': 'Africa/Lagos'
        }
        created_calendar = self.service.calendars().insert(body=calendar_meta).execute()
        calendar_id = created_calendar['id']

        # 2. Share the Calendar with the doctor's personal/work email
        # 'writer' role allows them to see details and manually cancel events if needed
        rule = {
            'scope': {
                'type': 'user',
                'value': doctor_email,
            },
            'role': 'writer'
        }
        self.service.acl().insert(calendarId=calendar_id, body=rule).execute()

        return calendar_id