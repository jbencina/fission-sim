"""User-facing disclaimer text for simulation entry points."""

from __future__ import annotations

import sys
from typing import TextIO

DISCLAIMER_TEXT = (
    "DISCLAIMER: fission-sim is a personal learning project and is not for "
    "real-world use. The author has no training or experience in nuclear "
    "engineering; model behavior, values, and explanations may be incorrect, "
    "incomplete, and oversimplified."
)


def print_disclaimer(stream: TextIO | None = None) -> None:
    """Print the project disclaimer to a console stream."""
    target = stream if stream is not None else sys.stderr
    print(DISCLAIMER_TEXT, file=target)
