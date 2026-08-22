"""A logger that behaves whether or not the host configures logging.

The library must not decide how an application logs, and must not go silent
when it has not been told anything. A NullHandler covers the second: warnings
still reach a caller who configures logging, and nothing is printed to a caller
who does not.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("carryover")
logger.addHandler(logging.NullHandler())
