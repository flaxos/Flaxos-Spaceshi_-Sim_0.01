import unittest
import random
from hybrid.simulator import Simulator

class TestPassiveSensorDetection(unittest.TestCase):
    def test_contact_generated_within_range(self):
        observer_config = {
            "id": "observer",
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "mass": 1000.0,
            "systems": {
                "sensors": {
                    "passive": {"range": 1000.0}
                }
            }
        }

        target_config = {
            "id": "target",
            "position": {"x": 500.0, "y": 0.0, "z": 0.0},
            "mass": 1000.0,
            "systems": {
                "sensors": {
                    "passive": {"range": 1000.0}
                }
            }
        }

        sim = Simulator(dt=0.1)
        sim.add_ship("observer", observer_config)
        sim.add_ship("target", target_config)

        random.seed(0)
        sim.start()
        sim.tick()

        observer = sim.get_ship("observer")
        sensor = observer.systems["sensors"]
        contacts = sensor.passive.get("contacts", [])

        self.assertTrue(any(c.get("id") == "target" for c in contacts))

if __name__ == "__main__":
    unittest.main()
