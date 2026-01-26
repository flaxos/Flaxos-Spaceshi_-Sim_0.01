"""
Canonical configuration for Flaxos Spaceship Sim server.

This module defines all default ports, hosts, and configuration values
used across the server stack. Import from here to ensure consistency.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import os


class ServerMode(Enum):
    """Server operation mode."""
    MINIMAL = "minimal"   # Basic server, no station management
    STATION = "station"   # Full multi-crew station-based control


# Default port assignments
DEFAULT_TCP_PORT = 8765      # Main simulation server
DEFAULT_WS_PORT = 8080       # WebSocket bridge
DEFAULT_HTTP_PORT = 3000     # GUI static file server
DEFAULT_MOBILE_PORT = 5000   # Mobile UI (Flask)

# Default host bindings
DEFAULT_HOST = "127.0.0.1"           # Localhost only (secure default)
DEFAULT_LAN_HOST = "0.0.0.0"         # All interfaces (for LAN play)

# Simulation defaults
DEFAULT_DT = 0.1                     # 100ms simulation timestep
DEFAULT_FLEET_DIR = "hybrid_fleet"   # Ship definitions directory

# Protocol version
PROTOCOL_VERSION = "1.0"


@dataclass
class ServerConfig:
    """
    Server configuration container.

    Provides a single source of truth for all server settings.
    Can be constructed from CLI args, environment, or config file.
    """

    # Server mode
    mode: ServerMode = ServerMode.STATION

    # Network settings
    host: str = DEFAULT_HOST
    tcp_port: int = DEFAULT_TCP_PORT
    ws_port: int = DEFAULT_WS_PORT
    http_port: int = DEFAULT_HTTP_PORT

    # Simulation settings
    dt: float = DEFAULT_DT
    fleet_dir: str = DEFAULT_FLEET_DIR

    # Optional overrides
    log_file: Optional[str] = None
    lan_mode: bool = False

    def __post_init__(self):
        """Apply LAN mode settings if enabled."""
        if self.lan_mode and self.host == DEFAULT_HOST:
            self.host = DEFAULT_LAN_HOST

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create config from environment variables."""
        return cls(
            mode=ServerMode(os.environ.get("FLAXOS_MODE", "station")),
            host=os.environ.get("FLAXOS_HOST", DEFAULT_HOST),
            tcp_port=int(os.environ.get("FLAXOS_TCP_PORT", DEFAULT_TCP_PORT)),
            ws_port=int(os.environ.get("FLAXOS_WS_PORT", DEFAULT_WS_PORT)),
            http_port=int(os.environ.get("FLAXOS_HTTP_PORT", DEFAULT_HTTP_PORT)),
            dt=float(os.environ.get("FLAXOS_DT", DEFAULT_DT)),
            fleet_dir=os.environ.get("FLAXOS_FLEET_DIR", DEFAULT_FLEET_DIR),
            log_file=os.environ.get("FLAXOS_LOG_FILE"),
            lan_mode=os.environ.get("FLAXOS_LAN", "").lower() in ("1", "true", "yes"),
        )

    def to_discovery_info(self) -> dict:
        """
        Generate discovery information for GUI autodiscovery.

        Returns:
            Dictionary with connection info for clients
        """
        return {
            "version": PROTOCOL_VERSION,
            "mode": self.mode.value,
            "endpoints": {
                "tcp": {"host": self.host, "port": self.tcp_port},
                "ws": {"host": self.host, "port": self.ws_port},
                "http": {"host": self.host, "port": self.http_port},
            },
            "features": {
                "stations": self.mode == ServerMode.STATION,
                "multi_crew": self.mode == ServerMode.STATION,
                "fleet_commands": True,
            },
        }


def get_default_config() -> ServerConfig:
    """Get the default server configuration."""
    return ServerConfig()
