"""Run fictional conversation evaluations. Outputs contain no server addresses.

Usage: python evals/run.py --model gemma2:9b
Move checks are smoke checks; review response meaning manually as well.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent
from models import Profile, TroubleshootingStep


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    failures = 0
    for case in json.loads(Path(__file__).with_name("scenarios.json").read_text()):
        history = []
        if case["previous_step"]:
            previous = TroubleshootingStep(summary="Previous action", step=case["previous_step"],
                why="Earlier diagnostic", difficulty="easy", requires_terminal=False)
            history.append({"id":1,"action_id":1,"step":previous.model_dump(),
                "result":case.get("result", "unclear"), "observation":case["observation"]})
        started = time.monotonic()
        try:
            response = agent.generate_step(Profile(), case["problem"], history, [],
                "next" if case.get("result") == "failed" else "simplify" if history else "initial", model=args.model)
            move = getattr(response, "next_move", "safety")
            fallback_used = getattr(response, "situation", "") == "The model could not produce a valid contextual response."
            passed = move in case["expected_moves"] and not fallback_used
            failures += not passed
            print(json.dumps({"scenario":case["name"], "model":args.model,
                "move_check_passed":passed, "fallback_used":fallback_used, "seconds":round(time.monotonic()-started, 1),
                "decision":response.model_dump()}, ensure_ascii=False), flush=True)
        except agent.AgentError as exc:
            failures += 1
            print(json.dumps({"scenario":case["name"], "error":str(exc)}), flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
