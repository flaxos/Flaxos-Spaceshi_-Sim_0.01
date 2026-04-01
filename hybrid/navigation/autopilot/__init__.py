# hybrid/navigation/autopilot/__init__.py
"""Autopilot programs for autonomous ship control."""

from .base import BaseAutopilot
from .match_velocity import MatchVelocityAutopilot
from .intercept import InterceptAutopilot
from .hold import HoldPositionAutopilot
from .formation import FormationAutopilot
from .formation_echelon import EchelonFormationAutopilot
from .goto_position import GoToPositionAutopilot
from .orbit import OrbitAutopilot
from .evasive import EvasiveAutopilot
from .rendezvous import RendezvousAutopilot
from .factory import AutopilotFactory

__all__ = [
    'BaseAutopilot',
    'MatchVelocityAutopilot',
    'InterceptAutopilot',
    'HoldPositionAutopilot',
    'FormationAutopilot',
    'EchelonFormationAutopilot',
    'GoToPositionAutopilot',
    'OrbitAutopilot',
    'EvasiveAutopilot',
    'RendezvousAutopilot',
    'AutopilotFactory'
]
