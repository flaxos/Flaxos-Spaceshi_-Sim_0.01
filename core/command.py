# core/command.py
from dataclasses import dataclass
from typing import Dict

@dataclass
class Command:
    command_type: str
    payload: Dict
    source: str = "unknown"
    timestamp: str = ""
