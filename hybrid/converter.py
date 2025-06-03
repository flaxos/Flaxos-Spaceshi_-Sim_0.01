# hybrid/converter.py
"""
Utility for converting old-style ship configurations to the hybrid format.
"""
# hybrid/converter.py
"""
Converter module for the hybrid architecture.
This module converts ship definitions from JSON to the hybrid format.
"""
import os
import json
import sys
import shutil

def convert_ships(input_dir, output_dir):
    """
    Convert ship JSON files to the hybrid format
    
    Args:
        input_dir (str): Directory containing input JSON files
        output_dir (str): Directory to write output files to
        
    Returns:
        int: Number of ships converted
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    count = 0
    for filename in os.listdir(input_dir):
        if filename.endswith('.json'):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, filename)
            
            print(f"Converting {input_path} to {output_path}")
            
            try:
                # Load JSON
                with open(input_path, 'r') as f:
                    ship_data = json.load(f)
                
                # Convert to hybrid format
                hybrid_data = convert_ship_to_hybrid(ship_data)
                
                # Write output
                with open(output_path, 'w') as f:
                    json.dump(hybrid_data, f, indent=2)
                    
                count += 1
            except Exception as e:
                print(f"Error converting {input_path}: {e}")
    
    return count

def convert_ship_to_hybrid(ship_data):
    """
    Convert a ship definition to the hybrid format
    
    Args:
        ship_data (dict): Ship definition in JSON format
        
    Returns:
        dict: Ship definition in hybrid format
    """
    # Create a copy of the data to avoid modifying the original
    hybrid_data = ship_data.copy()
    
    # Make sure we have a valid systems section
    if "systems" not in hybrid_data or not isinstance(hybrid_data["systems"], dict):
        hybrid_data["systems"] = {}
    
    # Make sure we have a valid position section
    if "position" not in hybrid_data or not isinstance(hybrid_data["position"], dict):
        hybrid_data["position"] = {"x": 0.0, "y": 0.0, "z": 0.0}
    
    # Make sure we have a valid orientation section
    if "orientation" not in hybrid_data or not isinstance(hybrid_data["orientation"], dict):
        hybrid_data["orientation"] = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
    
    # Convert or initialize each system
    for system_type in ["power", "propulsion", "sensors", "navigation", "helm", "bio"]:
        # Skip if system already exists in valid format
        if system_type in hybrid_data["systems"] and isinstance(hybrid_data["systems"][system_type], dict):
            continue
            
        # Create default system configuration
        if system_type == "power":
            hybrid_data["systems"][system_type] = {
                "enabled": True,
                "generation": 100.0,
                "capacity": 1000.0,
                "efficiency": 0.95
            }
        elif system_type == "propulsion":
            hybrid_data["systems"][system_type] = {
                "enabled": True,
                "main_drive": {
                    "max_thrust": 100.0,
                    "efficiency": 0.9
                },
                "maneuvering_thrusters": {
                    "power": 20.0,
                    "efficiency": 0.7
                },
                "max_fuel": 1000.0,
                "fuel_level": 1000.0
            }
        elif system_type == "sensors":
            hybrid_data["systems"][system_type] = {
                "enabled": True,
                "passive_range": 1000.0,
                "active_range": 5000.0,
                "ping_cooldown": 10.0
            }
        elif system_type == "navigation":
            hybrid_data["systems"][system_type] = {
                "enabled": True,
                "autopilot_enabled": False,
                "approach_distance": 10.0,
                "max_speed": 100.0
            }
        elif system_type == "helm":
            hybrid_data["systems"][system_type] = {
                "enabled": True,
                "manual_override": False,
                "control_mode": "standard",
                "dampening": 0.8
            }
        elif system_type == "bio":
            hybrid_data["systems"][system_type] = {
                "enabled": True,
                "crew_count": 1,
                "health_status": "nominal",
                "max_sustained_g": 3.0,
                "max_peak_g": 8.0,
                "safety_override": False
            }
    
    return hybrid_data

def create_test_scenario(output_dir):
    """
    Create a test scenario with multiple ships
    
    Args:
        output_dir (str): Directory to write scenario file to
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Create scenarios directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create test scenario with multiple ships
    scenario = {
        "name": "Test Scenario",
        "description": "A simple test scenario with multiple ships",
        "ships": [
            {
                "id": "player_ship",
                "name": "Valiant",
                "class": "corvette",
                "faction": "alliance",
                "mass": 5000.0,
                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
                "orientation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
                "systems": {
                    "power": {
                        "enabled": True,
                        "generation": 200.0,
                        "capacity": 2000.0,
                        "efficiency": 0.95
                    },
                    "propulsion": {
                        "enabled": True,
                        "main_drive": {
                            "max_thrust": 150.0,
                            "efficiency": 0.9
                        },
                        "max_fuel": 2000.0,
                        "fuel_level": 2000.0
                    },
                    "sensors": {
                        "enabled": True,
                        "passive_range": 2000.0,
                        "active_range": 8000.0,
                        "ping_cooldown": 5.0
                    }
                }
            },
            {
                "id": "enemy_ship",
                "name": "Marauder",
                "class": "frigate",
                "faction": "pirates",
                "mass": 8000.0,
                "position": {"x": 500.0, "y": 500.0, "z": 0.0},
                "velocity": {"x": -5.0, "y": 0.0, "z": 0.0},
                "orientation": {"pitch": 0.0, "yaw": 180.0, "roll": 0.0},
                "systems": {
                    "power": {
                        "enabled": True,
                        "generation": 180.0,
                        "capacity": 1800.0,
                        "efficiency": 0.9
                    },
                    "propulsion": {
                        "enabled": True,
                        "main_drive": {
                            "max_thrust": 130.0,
                            "efficiency": 0.85
                        },
                        "max_fuel": 1800.0,
                        "fuel_level": 1500.0
                    }
                }
            },
            {
                "id": "neutral_ship",
                "name": "Trader",
                "class": "shuttle",
                "faction": "civilian",
                "mass": 2000.0,
                "position": {"x": -800.0, "y": 200.0, "z": 100.0},
                "velocity": {"x": 2.0, "y": 1.0, "z": 0.0},
                "orientation": {"pitch": 0.0, "yaw": 45.0, "roll": 0.0}
            }
        ]
    }
    
    # Write scenario to file
    scenario_path = os.path.join(output_dir, "test_scenario.json")
    try:
        with open(scenario_path, 'w') as f:
            json.dump(scenario, f, indent=2)
        print(f"Created test scenario: {scenario_path}")
        return True
    except Exception as e:
        print(f"Error creating test scenario: {e}")
        return False

def main():
    """Main function"""
    # Check command line arguments
    if len(sys.argv) < 3:
        print("Usage: python -m hybrid.converter <input_dir> <output_dir>")
        return 1
    
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    
    # Check if input directory exists
    if not os.path.exists(input_dir):
        print(f"Input directory not found: {input_dir}")
        return 1
    
    # Convert ships
    count = convert_ships(input_dir, output_dir)
    print(f"Converted {count} ships to {output_dir}")
    
    # Create test scenario
    create_test_scenario("scenarios")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
import json
import os
import logging

logger = logging.getLogger(__name__)

def convert_system_config(system_name, config):
    """
    Convert a system configuration to the hybrid format
    
    Args:
        system_name (str): Name of the system
        config (dict): Old system configuration
        
    Returns:
        dict: Converted system configuration
    """
    # Start with the original config
    new_config = dict(config)
    
    # Ensure required fields
    if "enabled" not in new_config:
        new_config["enabled"] = True
        
    # Set default values based on system type
    if system_name == "power":
        new_config["power_draw"] = 0  # Power system doesn't draw power
        new_config["mass"] = new_config.get("mass", 50)
        new_config["slot_type"] = "core"
        new_config["tech_level"] = new_config.get("tech_level", 1)
    elif system_name == "propulsion":
        new_config["power_draw"] = new_config.get("power_draw", 10)
        new_config["mass"] = new_config.get("mass", 100)
        new_config["slot_type"] = "propulsion"
        new_config["tech_level"] = new_config.get("tech_level", 1)
    elif system_name == "sensors":
        new_config["power_draw"] = new_config.get("power_draw", 5)
        new_config["mass"] = new_config.get("mass", 30)
        new_config["slot_type"] = "sensor"
        new_config["tech_level"] = new_config.get("tech_level", 1)
    elif system_name == "helm":
        new_config["power_draw"] = new_config.get("power_draw", 2)
        new_config["mass"] = new_config.get("mass", 20)
        new_config["slot_type"] = "control"
        new_config["tech_level"] = new_config.get("tech_level", 1)
    elif system_name == "bio_monitor":
        new_config["power_draw"] = new_config.get("power_draw", 1)
        new_config["mass"] = new_config.get("mass", 10)
        new_config["slot_type"] = "utility"
        new_config["tech_level"] = new_config.get("tech_level", 1)
    elif system_name == "navigation":
        new_config["power_draw"] = new_config.get("power_draw", 3)
        new_config["mass"] = new_config.get("mass", 25)
        new_config["slot_type"] = "control"
        new_config["tech_level"] = new_config.get("tech_level", 1)
    else:
        # Generic defaults
        new_config["power_draw"] = new_config.get("power_draw", 5)
        new_config["mass"] = new_config.get("mass", 20)
        new_config["slot_type"] = "utility"
        new_config["tech_level"] = new_config.get("tech_level", 1)
        
    return new_config

def convert_ship_config(config):
    """
    Convert a ship configuration to the hybrid format
    
    Args:
        config (dict): Old ship configuration
        
    Returns:
        dict: Converted ship configuration
    """
    # Start with the original config
    new_config = dict(config)
    
    # Convert systems
    if "systems" in new_config:
        systems = new_config["systems"]
        new_systems = {}
        
        for system_name, system_config in systems.items():
            new_systems[system_name] = convert_system_config(system_name, system_config)
            
        new_config["systems"] = new_systems
        
    # Ensure launch bay if not present
    if "launch_bay" not in new_config:
        new_config["launch_bay"] = {
            "capacity": 0,
            "types_allowed": [],
            "active": []
        }
        
    return new_config

def convert_ships_in_directory(input_dir, output_dir):
    """
    Convert all ship configurations in a directory
    
    Args:
        input_dir (str): Input directory containing old ship configurations
        output_dir (str): Output directory for new ship configurations
        
    Returns:
        int: Number of ships converted
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    count = 0
    try:
        for filename in os.listdir(input_dir):
            if filename.endswith(".json"):
                input_path = os.path.join(input_dir, filename)
                output_path = os.path.join(output_dir, filename)
                
                try:
                    # Load old config
                    with open(input_path, 'r') as f:
                        config = json.load(f)
                        
                    # Convert config
                    new_config = convert_ship_config(config)
                    
                    # Save new config
                    with open(output_path, 'w') as f:
                        json.dump(new_config, f, indent=2)
                        
                    count += 1
                    logger.info(f"Converted {input_path} -> {output_path}")
                except Exception as e:
                    logger.error(f"Failed to convert {input_path}: {e}")
    except Exception as e:
        logger.error(f"Failed to process directory {input_dir}: {e}")
        
    return count

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) != 3:
        print("Usage: python converter.py <input_dir> <output_dir>")
        sys.exit(1)
        
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    
    count = convert_ships_in_directory(input_dir, output_dir)
    print(f"Converted {count} ships")
