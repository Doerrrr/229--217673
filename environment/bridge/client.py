"""Public raw-DDI stream adapter. The agent repairs only the native graph engine."""

from __future__ import annotations

import subprocess
import sys
import os

from panel_to_graph import translate


def main() -> None:
    graph_stream = translate(sys.stdin.read())
    completed = subprocess.run(
        [os.environ.get("DDI_BRIDGE_ENGINE", "/opt/ddi-bridge/bridge-index")],
        input=graph_stream,
        text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    sys.stdout.write(completed.stdout)


if __name__ == "__main__":
    main()
