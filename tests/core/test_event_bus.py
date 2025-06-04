import unittest
from hybrid.core.event_bus import EventBus

class TestEventBus(unittest.TestCase):
    def test_publish_subscribe(self):
        bus = EventBus.get_instance()
        results = []
        def callback(payload):
            results.append(payload)
        bus.subscribe('test', callback)
        bus.publish('test', {'data': 1})
        self.assertEqual(results[0]['data'], 1)

if __name__ == '__main__':
    unittest.main()
