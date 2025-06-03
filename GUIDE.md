# Hybrid Ship Simulator - User Guide

This guide will help you start the simulator, launch the GUI, and test both navigation and sensor gameplay elements.

## Starting the Simulator

To launch the GUI and start the simulation:

1. Open a terminal/command prompt
2. Navigate to the project directory
3. Run the following command:
   ```
   python run_hybrid_sim.py
   ```
   
   This will start the GUI with the default test scenario.

4. If you want to use a specific scenario, you can specify it with:
   ```
   python run_hybrid_sim.py --scenario sensor_test_scenario
   ```

## Using the GUI

Once the GUI launches, you'll see a ship control interface with several panels:

### Loading and Starting the Simulation

1. **Load Ships**: Click the "Load Ships" button to load available ships from the hybrid_fleet directory
2. **Load Scenario**: Click the "Load Scenario" button to load a predefined scenario
3. **Start Simulation**: Click the "Start Simulation" button to begin the simulation
   - The button will change to "Stop Simulation" when running
   - You'll see the telemetry updating in real-time

### Ship Selection

- Use the ship dropdown to select different ships in the simulation
- The active ship's state information will be displayed in the telemetry panels

### Testing Navigation

1. **Setting a Course**:
   - Enter X, Y, Z coordinates in the Navigation panel
   - Click "Set Course" to establish the destination
   - Click "Enable Autopilot" to have the ship navigate automatically

2. **Manual Thrust Control**:
   - Enter X, Y, Z thrust values in the Thrust Control panel
   - Click "Set Thrust" to apply the thrust
   - Click "Manual Helm On" to take direct control
   - The ship will respond according to the physical model

3. **Verifying Navigation**:
   - Watch the ship's position, velocity, and orientation change in the telemetry panels
   - The autopilot should adjust thrust to reach the target coordinates
   - Manual thrust allows direct control of the ship's movement

### Testing Sensor Gameplay

1. **Active Sensor Ping**:
   - Click "Ping Sensors" to perform an active sensor scan
   - This will detect ships at a longer range but will make your ship detectable
   - The cooldown indicator will show when you can ping again

2. **Viewing Contacts**:
   - Detected ships will appear in the Sensor Contacts panel
   - The display shows ship ID, distance, and detection method
   - Use the "Show" dropdown to filter contacts (all, active, passive, recent)
   - Use "Sort by" to organize contacts by distance, name, timestamp, or signature

3. **Passive Sensors**:
   - Passive sensors work automatically without interaction
   - They have shorter range but don't reveal your position
   - You'll see passively detected ships in the contacts panel

## Advanced Testing

For more comprehensive testing:

1. **Custom Commands**:
   - Use the Custom Command panel to send specific commands
   - Example: `get_state`, `set_thrust`, `rotate`, etc.

2. **Multi-Ship Testing**:
   - Load a scenario with multiple ships
   - Switch between ships to test interactions
   - Try to detect other ships using sensors

3. **Bio Override**:
   - Click "Override Bio Monitor" to bypass safety limits
   - This allows more aggressive maneuvers but increases risk

## Troubleshooting

If you encounter issues:

- Check the console output for error messages
- Ensure all ships are loaded properly
- Try restarting the simulation
- Verify that the hybrid_fleet directory contains ship files

## Command Reference

### Navigation Commands:
- `set_course`: Set destination coordinates
- `autopilot`: Enable/disable autopilot
- `set_thrust`: Apply specific thrust values
- `helm_override`: Enable/disable manual helm control

### Sensor Commands:
- `ping_sensors`: Perform active sensor scan
- `get_contacts`: Retrieve all sensor contacts

Remember that some commands have cooldown periods, especially sensor pings!
