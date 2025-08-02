"""Record GitHub Actions run parameters to a JSON file."""

import json
import os
import datetime
from pathlib import Path
import logging

class RunParametersRecorder:
    """Save workflow inputs and results for later inspection."""

    def __init__(self, inputs_env: str, result_env: str) -> None:
        self.inputs_env = inputs_env
        self.result_env = result_env
        self.logger = logging.getLogger(self.__class__.__name__)

    def record(self) -> None:
        """Write the run parameters to ``.github/workflow-data/last-run.json``."""
        data = {
            "inputs": json.loads(self.inputs_env or "{}"),
            "outcome": self.result_env or "unknown",
            "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        path = Path(".github/workflow-data/last-run.json")
        path.write_text(json.dumps(data, indent=2))
        self.logger.debug("Saved run data to %s", path)


def main() -> None:
    """CLI entrypoint for saving run parameters."""
    logging.basicConfig(level=logging.DEBUG)
    recorder = RunParametersRecorder(
        os.environ.get("INPUTS_JSON", "{}"), os.environ.get("RESULT", "unknown")
    )
    recorder.record()


if __name__ == "__main__":
    main()
