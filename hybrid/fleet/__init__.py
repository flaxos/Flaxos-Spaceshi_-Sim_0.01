"""
Fleet Management System
Provides multi-ship coordination, formations, and fleet-level combat capabilities.
"""

from .formation import FleetFormation, FormationType, FormationPosition, FormationConfig
from .fleet_manager import FleetManager, FleetGroup, FleetStatus, FleetMessage, SharedContact, ThreatLevel
from .ai_controller import AIController, AIBehavior
from .threat_assessment import AIThreatAssessment
from .npc_behavior import BehaviorProfile, get_profile, infer_role

__all__ = [
    'FleetFormation',
    'FormationType',
    'FormationPosition',
    'FormationConfig',
    'FleetManager',
    'FleetGroup',
    'FleetStatus',
    'FleetMessage',
    'SharedContact',
    'ThreatLevel',
    'AIController',
    'AIBehavior',
    'AIThreatAssessment',
    'BehaviorProfile',
    'get_profile',
    'infer_role',
]
