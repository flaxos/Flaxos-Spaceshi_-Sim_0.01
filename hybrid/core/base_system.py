# hybrid/core/base_system.py

class BaseSystem:
    def __init__(self, config):
        self.config = config

    def tick(self, dt):
        raise NotImplementedError("tick must be implemented by subclasses")
