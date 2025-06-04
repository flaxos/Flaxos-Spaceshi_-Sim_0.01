# Hybrid Ship Simulator

This project provides a simulation environment for spacecraft with a hybrid object-oriented and event-driven architecture.

## Quick Start

1. Convert YAML ship definitions to JSON:
   ```
   python convert_yaml_to_json.py
   ```

2. Convert JSON to hybrid format:
   ```
   python -m hybrid.converter fleet_json hybrid_fleet
   ```

3. Start the command server (required for GUI commands):
   ```
   python main.py
   ```

4. In a separate terminal, launch the GUI:
   ```
   python run_hybrid_sim.py
   ```

## Running without GUI
