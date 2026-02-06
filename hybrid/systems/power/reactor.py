# hybrid/systems/power/reactor.py

from hybrid.core.constants import DEFAULT_REACTOR_OUTPUT, DEFAULT_OUTPUT_RATE, DEFAULT_THERMAL_LIMIT

class Reactor:
    def __init__(self, name, capacity=DEFAULT_REACTOR_OUTPUT,
                 output_rate=DEFAULT_OUTPUT_RATE, thermal_limit=DEFAULT_THERMAL_LIMIT,
                 fuel_capacity=None, fuel_level=None, fuel_consumption_rate=0.0,
                 cooling_rate=1.5, heat_rate=0.05, heat_per_kw=0.1,
                 overheat_output_factor=0.5):
        self.name = name
        self.capacity = capacity
        self.available = 0.0
        self.output_rate = output_rate
        self.thermal_limit = thermal_limit
        self.temperature = 25.0  # ambient start
        self.status = "nominal"
        self.fuel_capacity = self._normalize_fuel(fuel_capacity)
        self.fuel_level = self._normalize_fuel(fuel_level)
        if self.fuel_capacity is not None and self.fuel_level is None:
            self.fuel_level = self.fuel_capacity
        self.fuel_consumption_rate = float(fuel_consumption_rate or 0.0)
        self.cooling_rate = float(cooling_rate or 0.0)
        self.heat_rate = float(heat_rate or 0.0)
        self.heat_per_kw = float(heat_per_kw or 0.0)
        self.overheat_output_factor = float(overheat_output_factor or 0.5)
        self.last_generated = 0.0
        self.last_drawn = 0.0

    def _normalize_fuel(self, value):
        if value is None:
            return None
        value = float(value)
        return value if value > 0 else None

    def tick(self, dt):
        self.last_generated = 0.0
        self._cool(dt)

        if self._is_depleted():
            self.available = 0.0
            self.status = "depleted"
            return

        # Ramp available power toward capacity
        if self.available < self.capacity:
            generated = min(self.capacity - self.available, self.output_rate * dt)
            generated = self._consume_fuel_for_output(generated)
            if generated > 0:
                self.available = min(self.capacity, self.available + generated)
                self.last_generated = generated

        self._apply_heat_from_output(dt)

        # If overheated, mark status and throttle output
        if self.temperature > self.thermal_limit:
            self.status = "overheated"
            self.available *= self.overheat_output_factor
        elif self.status == "overheated" and self.temperature <= self.thermal_limit * 0.9:
            self.status = "nominal"
        elif self.status == "nominal":
            self.status = "nominal"

    def draw_power(self, amount):
        if self.available >= amount:
            self.available -= amount
            self.temperature += amount * self.heat_per_kw
            self.last_drawn += amount
            return True
        return False

    def _consume_fuel_for_output(self, generated):
        if generated <= 0:
            return 0.0
        if self.fuel_capacity is None:
            return generated
        if self.fuel_consumption_rate <= 0:
            return generated
        if self.fuel_level is None:
            return generated
        fuel_needed = generated * self.fuel_consumption_rate
        if fuel_needed <= self.fuel_level:
            self.fuel_level -= fuel_needed
            return generated
        if self.fuel_level <= 0:
            self.fuel_level = 0.0
            return 0.0
        output_limited = self.fuel_level / self.fuel_consumption_rate
        self.fuel_level = 0.0
        return output_limited

    def _apply_heat_from_output(self, dt):
        if self.capacity <= 0:
            return
        output_ratio = max(0.0, min(1.0, self.available / self.capacity))
        if output_ratio <= 0:
            return
        self.temperature += (self.heat_rate * output_ratio) * dt

    def _cool(self, dt):
        if self.cooling_rate <= 0:
            return
        self.temperature = max(0.0, self.temperature - self.cooling_rate * dt)

    def _is_depleted(self):
        if self.fuel_capacity is None:
            return False
        if self.fuel_level is None:
            return False
        return self.fuel_level <= 0.0
