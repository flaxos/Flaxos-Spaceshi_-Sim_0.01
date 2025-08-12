from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
@dataclass
class Reactor:
    name: str; max_output: float; warmup_time: float
    heat: float = 0.0; heat_per_output: float = 0.02; cooldown_rate: float = 1.5
    online: bool = True; _t: float = 0.0; health: float = 100.0
    def available(self)->float:
        if not self.online or self.health<=0.0: return 0.0
        ramp = min(1.0, self._t / max(1e-6, self.warmup_time))
        derate_heat = 1.0 if self.heat < 100.0 else max(0.1, 1.0 - (self.heat-100.0)/200.0)
        derate_health = max(0.1, self.health/100.0)
        return self.max_output * ramp * derate_heat * derate_health
    def tick(self, dt:float, draw:float):
        if self.online: self._t += dt
        self.heat += max(0.0, draw) * self.heat_per_output * dt
        self.heat = max(0.0, self.heat - self.cooldown_rate * dt)
        if self.health>0.0 and self.health<100.0: self.health = min(100.0, self.health + 0.02*dt)
@dataclass
class PowerBus:
    reactors: List[Reactor] = field(default_factory=list)
    def total_available(self)->float: return sum(r.available() for r in self.reactors)
    def allocate(self, requested:float)->float:
        requested=max(0.0, requested)
        av = [r.available() for r in self.reactors]; tot=sum(av)
        if tot<=1e-6 or requested<=1e-6:
            for r in self.reactors: r.tick(0.0, 0.0)
            return 0.0
        frac=[a/tot for a in av]; used=0.0; remaining=requested
        for f,r in zip(frac, self.reactors):
            take = min(r.available(), remaining*f)
            r.tick(0.0, take); used += take; remaining -= take
        return used
    def tick(self, dt:float, draw:float)->float:
        draw=max(0.0, draw)
        av = [r.available() for r in self.reactors]; tot=sum(av)
        if tot<=1e-6:
            for r in self.reactors: r.tick(dt, 0.0); return 0.0
        frac=[a/tot for a in av]; used=0.0
        for f,r in zip(frac, self.reactors):
            take=min(r.available(), draw*f)
            r.tick(dt, take); used += take
        return used
