"""Places one outbound call and points Twilio at our server for the conversation."""

import os
import sys

from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

PUBLIC_URL = os.environ["PUBLIC_URL"]
FROM_NUMBER = os.environ["TWILIO_FROM_NUMBER"]
TARGET_NUMBER = os.environ["TARGET_NUMBER"]

client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


def place_call(scenario="reschedule"):
    call = client.calls.create(
        to=TARGET_NUMBER,
        from_=FROM_NUMBER,
        url=f"{PUBLIC_URL}/twiml?scenario={scenario}",
        record=True,  # Twilio keeps the audio; we download it later
    )
    print(f"Dialing {TARGET_NUMBER} as '{scenario}'  (call {call.sid})")
    return call.sid


if __name__ == "__main__":
    place_call(sys.argv[1] if len(sys.argv) > 1 else "reschedule")