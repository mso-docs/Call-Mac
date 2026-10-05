"""Export only public prompt/schema data for the static demo; never load .env."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models import TroubleshootingDecision
from prompts import SYSTEM


def contract_text():
    return json.dumps({"system": SYSTEM, "schema": TroubleshootingDecision.model_json_schema()},
                      ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "demo" / "contract.json"
    content = contract_text()
    if args.check:
        if not destination.exists() or destination.read_text() != content:
            raise SystemExit("Demo contract is stale. Run: python tools/export_demo_contract.py")
        print("Demo prompt and schema match the Python app.")
    else:
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(content)
        print("Exported demo/contract.json (public prompt and schema only).")
