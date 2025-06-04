# hybrid/systems/power/reactor.py
from hybrid.core.constants import DEFAULT_REACTOR_OUTPUT, DEFAULT_OUTPUT_RATE, DEFAULT_THERMAL_LIMIT

class Reactor:
    def __init__(self, name, capacity=DEFAULT_REACTOR_OUTPUT, output_rate=DEFAULT_OUTPUT_RATE, thermal_limit=DEFAULT_THERMAL_LIMIT):
        self.name = name
        self.capacity = capacity
        self.available = 0.0
        self.output_rate = output_rate
        self.thermal_limit = thermal_limit
        self.temperature = 25.0  # starting ambient temperature
        self.status = "nominal"

    def tick(self, dt):
        if self.available < self.capacity:
            self.available = min(self.capacity, self.available + self.output_rate * dt)
        if self.temperature > self.thermal_limit:
            self.status = "overheated"
            self.available *= 0.5

    def draw_power(self, amount):
        if self.available >= amount:
            self.available -= amount
            self.temperature += amount * 0.1
            return True
        return False
