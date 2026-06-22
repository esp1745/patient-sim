"""Bridges a Twilio phone call to an OpenAI Realtime session.

Twilio streams the live call audio to us over a websocket; we hand it to OpenAI,
take OpenAI's spoken reply, and stream it back to Twilio. Both sides speak G.711
mu-law, so we forward the audio as-is without transcoding.
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import Connect, VoiceResponse
import websockets

from .scenarios import SCENARIOS

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-realtime"
VOICE = "alloy"

app = FastAPI()


@app.post("/twiml")
async def twiml(request: Request):
    """Twilio fetches this the moment the outbound call connects.

    We answer with instructions to open a media stream back to us, and pass along
    which scenario this call is running so the websocket knows who to be.
    """
    scenario_id = request.query_params.get("scenario", "reschedule")

    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(url=f"wss://{request.url.hostname}/media")
    stream.parameter(name="scenario", value=scenario_id)
    response.append(connect)
    return PlainTextResponse(str(response), media_type="application/xml")


@app.websocket("/media")
async def media(twilio_ws: WebSocket):
    await twilio_ws.accept()
    async with websockets.connect(
        REALTIME_URL,
        additional_headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
    ) as openai_ws:
        await CallBridge(twilio_ws, openai_ws).run()


class CallBridge:
    """Pumps audio both ways between one Twilio call and one OpenAI session."""

    def __init__(self, twilio_ws: WebSocket, openai_ws):
        self.twilio = twilio_ws
        self.openai = openai_ws
        self.stream_sid = None
        self.transcript = []  # (speaker, text), built up as the call unfolds

    async def run(self):
        # Run both directions at once; when either side hangs up, stop the other.
        pumps = [asyncio.create_task(self._from_twilio()),
                 asyncio.create_task(self._from_openai())]
        _, pending = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        self._save_transcript()

    async def _configure_session(self, scenario):
        await self.openai.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": scenario.persona,
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcmu"},  # G.711 mu-law, what Twilio sends
                        "turn_detection": {"type": "semantic_vad", "interrupt_response": True},
                        "transcription": {"model": "gpt-4o-mini-transcribe"},
                    },
                    "output": {
                        "format": {"type": "audio/pcmu"},
                        "voice": VOICE,
                    },
                },
            },
        }))

    async def _from_twilio(self):
        """Caller (clinic agent) audio -> OpenAI."""
        async for raw in self.twilio.iter_text():
            msg = json.loads(raw)
            event = msg["event"]

            if event == "start":
                self.stream_sid = msg["start"]["streamSid"]
                scenario_id = msg["start"]["customParameters"]["scenario"]
                await self._configure_session(SCENARIOS[scenario_id])
                # We don't speak first: the clinic agent greets, then our patient replies.

            elif event == "media":
                await self.openai.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": msg["media"]["payload"],  # already base64 mu-law
                }))

            elif event == "stop":
                break

    async def _from_openai(self):
        """OpenAI patient audio -> Twilio, plus transcript and barge-in handling."""
        async for raw in self.openai:
            event = json.loads(raw)
            kind = event.get("type", "")

            if kind in ("response.output_audio.delta", "response.audio.delta"):
                await self.twilio.send_json({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": event["delta"]},
                })

            elif kind == "input_audio_buffer.speech_started":
                # The clinic agent started talking; drop any patient audio still
                # queued at Twilio so the two voices don't overlap.
                await self.twilio.send_json({"event": "clear", "streamSid": self.stream_sid})

            elif kind == "conversation.item.input_audio_transcription.completed":
                self._record("agent", event.get("transcript", ""))

            elif kind in ("response.output_audio_transcript.done",
                          "response.audio_transcript.done"):
                self._record("patient", event.get("transcript", ""))

            elif kind == "error":
                print("OpenAI error:", event)

    def _record(self, speaker, text):
        text = text.strip()
        if text:
            self.transcript.append((speaker, text))

    def _save_transcript(self):
        if not self.stream_sid:
            return
        os.makedirs("transcripts", exist_ok=True)
        path = f"transcripts/{self.stream_sid}.txt"
        with open(path, "w") as f:
            for speaker, text in self.transcript:
                f.write(f"{speaker}: {text}\n")
        print(f"Saved {path}")