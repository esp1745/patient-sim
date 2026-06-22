"""Runs scenarios one call at a time against the target number.

  python -m patient_sim.run                  # every scenario
  python -m patient_sim.run weekend refill    # just these
"""

import sys
import time

from .caller import client, place_call
from .scenarios import SCENARIOS

FINISHED = {"completed", "busy", "failed", "no-answer", "canceled"}


def wait_until_done(sid, poll_seconds=5):
    while True:
        status = client.calls(sid).fetch().status
        if status in FINISHED:
            return status
        time.sleep(poll_seconds)


def run(scenario_ids):
    for scenario_id in scenario_ids:
        print(f"\n=== {scenario_id} ===")
        sid = place_call(scenario_id)
        status = wait_until_done(sid)
        print(f"    finished: {status}")
        time.sleep(3)  # short breather before the next call


if __name__ == "__main__":
    run(sys.argv[1:] or list(SCENARIOS))