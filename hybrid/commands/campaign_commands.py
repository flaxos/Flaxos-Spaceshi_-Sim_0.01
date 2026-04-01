# hybrid/commands/campaign_commands.py
"""Campaign management commands.

These are meta-level commands (not ship-scoped) that manage the persistent
campaign state between missions.  They are routed through the server's
meta-command dispatch, not through the hybrid command handler, because
campaign state lives on the runner -- not on any individual ship.

Commands:
    campaign_new:    Create a fresh campaign with a starter ship and crew.
    campaign_save:   Persist current campaign state to a JSON file.
    campaign_load:   Load campaign state from a previously saved JSON file.
    campaign_status: Return current campaign summary (credits, rep, chapter).
"""

import logging
import os
from typing import Optional

from hybrid.campaign.campaign_state import CampaignState

logger = logging.getLogger(__name__)

# Default save directory relative to project root
_DEFAULT_SAVE_DIR = "campaign_saves"


def cmd_campaign_new(runner, params: dict) -> dict:
    """Create a fresh campaign and attach it to the runner.

    Args:
        runner: HybridRunner instance.
        params: Optional keys:
            - ship_class (str): Starting ship class (default "corvette").

    Returns:
        dict: ok + campaign summary.
    """
    ship_class = params.get("ship_class", "corvette")
    state = CampaignState.new_campaign(ship_class=ship_class)
    runner._campaign_state = state
    logger.info("New campaign created (ship_class=%s)", ship_class)
    return {"ok": True, "status": "Campaign created", "campaign": state.get_summary()}


def cmd_campaign_save(runner, params: dict) -> dict:
    """Save the active campaign to disk.

    Args:
        runner: HybridRunner instance.
        params: Optional keys:
            - filepath (str): Custom save path. Defaults to campaign_saves/campaign.json.

    Returns:
        dict: ok + filepath saved to.
    """
    state = getattr(runner, "_campaign_state", None)
    if state is None:
        return {"ok": False, "error": "NO_CAMPAIGN", "message": "No active campaign to save"}

    save_dir = os.path.join(runner.root_dir, _DEFAULT_SAVE_DIR)
    filepath = params.get("filepath") or os.path.join(save_dir, "campaign.json")

    try:
        state.save(filepath)
        return {"ok": True, "status": "Campaign saved", "filepath": filepath}
    except Exception as exc:
        logger.error("Failed to save campaign: %s", exc, exc_info=True)
        return {"ok": False, "error": "SAVE_FAILED", "message": str(exc)}


def cmd_campaign_load(runner, params: dict) -> dict:
    """Load a campaign from a JSON file.

    Args:
        runner: HybridRunner instance.
        params: Required keys:
            - filepath (str): Path to the campaign save file.

    Returns:
        dict: ok + campaign summary.
    """
    filepath = params.get("filepath")
    if not filepath:
        # Try default location
        filepath = os.path.join(runner.root_dir, _DEFAULT_SAVE_DIR, "campaign.json")

    if not os.path.exists(filepath):
        return {
            "ok": False,
            "error": "FILE_NOT_FOUND",
            "message": f"Campaign file not found: {filepath}",
        }

    try:
        state = CampaignState.load(filepath)
        runner._campaign_state = state
        logger.info("Campaign loaded from %s", filepath)
        return {"ok": True, "status": "Campaign loaded", "campaign": state.get_summary()}
    except Exception as exc:
        logger.error("Failed to load campaign: %s", exc, exc_info=True)
        return {"ok": False, "error": "LOAD_FAILED", "message": str(exc)}


def cmd_campaign_status(runner, params: dict) -> dict:
    """Return the current campaign summary.

    Args:
        runner: HybridRunner instance.
        params: Ignored.

    Returns:
        dict: ok + campaign summary, or error if no campaign is active.
    """
    state: Optional[CampaignState] = getattr(runner, "_campaign_state", None)
    if state is None:
        return {"ok": False, "error": "NO_CAMPAIGN", "message": "No active campaign"}

    return {"ok": True, "campaign": state.get_summary()}
