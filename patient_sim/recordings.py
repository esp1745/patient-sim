"""Pulls every Twilio call recording down as mp3 into recordings/.

  python -m patient_sim.recordings
"""

import os

import requests
from dotenv import load_dotenv

from .caller import client

load_dotenv()

SID = os.environ["TWILIO_ACCOUNT_SID"]
TOKEN = os.environ["TWILIO_AUTH_TOKEN"]


def download_all():
    os.makedirs("recordings", exist_ok=True)
    for rec in client.recordings.list():
        url = f"https://api.twilio.com/2010-04-01/Accounts/{SID}/Recordings/{rec.sid}.mp3"
        path = f"recordings/{rec.call_sid}.mp3"
        audio = requests.get(url, auth=(SID, TOKEN))
        with open(path, "wb") as f:
            f.write(audio.content)
        print(f"{path}  ({rec.duration}s, {rec.date_created:%Y-%m-%d %H:%M})")


if __name__ == "__main__":
    download_all()