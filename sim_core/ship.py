from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
import math, random
from .vec import Vec3
from .navigation import NavigationSystem
from .sensors import SensorSystem
from .power import PowerBus
from .weapons import Weapon
@dataclass
class Ship:
    name: str
    mass: float
    position: Vec3
    velocity: Vec3
    nav: NavigationSystem
    sensors: SensorSystem
    reactors: PowerBus
    weapon: Optional[Weapon] = None
    hull: float = 100.0
    thrust_out: Vec3 = field(default_factory=Vec3)
    dt: float = 0.1
    subsys: Dict[str, float] = field(default_factory=lambda: {"engines":100.0})
    crew_repair_rate: float = 0.3
    ai_mode: str = "idle"
    ecm_power: float = 0.0
    def passive_signature(self)->float:
        return 5.0 + 0.02 * self.thrust_out.norm()
    def alive(self)->bool:
        return self.hull > 0.0
    def apply_subsystem_damage(self, dmg: float, rng: random.Random):
        to_sub = dmg * 0.3; to_hull = dmg - to_sub
        self.hull = max(0.0, self.hull - to_hull)
        targets = []
        if self.sensors: targets.append(("sensors",None))
        if self.weapon: targets.append(("weapon",None))
        targets.append(("engines",None))
        if self.reactors.reactors: targets.append(("reactor",rng.choice(self.reactors.reactors)))
        if targets:
            which, ref = rng.choice(targets)
            if which=="sensors": self.sensors.health = max(0.0, self.sensors.health - to_sub)
            elif which=="weapon": self.weapon.health = max(0.0, self.weapon.health - to_sub)
            elif which=="engines": self.subsys["engines"] = max(0.0, self.subsys.get("engines",100.0) - to_sub)
            elif which=="reactor": ref.health = max(0.0, ref.health - to_sub)
    def take_damage(self, dmg: float, rng: Optional[random.Random]=None):
        rng = rng or random.Random(); self.apply_subsystem_damage(dmg, rng)
        for r in self.reactors.reactors: r.heat += dmg * 0.5
    def forward(self)->Vec3: return self.nav.forward()
    def bearing_elev_to(self, other_pos:Vec3)->Tuple[float,float]:
        r = other_pos - self.position
        az = math.degrees(math.atan2(r.y, r.x)) % 360.0
        dist_xy = math.hypot(r.x, r.y)
        el = math.degrees(math.atan2(r.z, dist_xy))
        return az, el
    def _crew_repair_tick(self, dt:float):
        cands = []
        if self.sensors: cands.append(("sensors","sensors", self.sensors.health, 100.0))
        if self.weapon: cands.append(("weapon","weapon", self.weapon.health, 100.0))
        cands.append(("engines","engines", self.subsys.get("engines",100.0), 100.0))
        if self.reactors.reactors:
            worst = min(self.reactors.reactors, key=lambda r: r.health)
            cands.append(("reactor", worst, worst.health, 100.0))
        damaged = [(k,obj,h,maxh) for (k,obj,h,maxh) in cands if h<maxh-1e-6]
        if not damaged: return
        k, obj, h, maxh = min(damaged, key=lambda x: x[2])
        delta = self.crew_repair_rate * dt; newh = min(maxh, h + delta)
        if k=="sensors": self.sensors.health = newh
        elif k=="weapon": self.weapon.health = newh
        elif k=="engines": self.subsys["engines"] = newh
        elif k=="reactor": obj.health = newh
    def _slew_turret_towards_target(self, dt:float, target: 'Ship'):
        if not self.weapon or self.weapon.health<=0.0: return
        az_world, el_world = self.bearing_elev_to(target.position)
        ship_yaw_deg = math.degrees(self.nav.yaw); ship_pitch_deg = math.degrees(self.nav.pitch)
        rel_yaw = ((az_world - ship_yaw_deg + 180.0) % 360.0) - 180.0
        rel_pitch = ((el_world - ship_pitch_deg + 180.0) % 360.0) - 180.0
        half_yaw = self.weapon.arc_yaw_deg * 0.5; half_pitch = self.weapon.arc_pitch_deg * 0.5
        rel_yaw = max(-half_yaw, min(half_yaw, rel_yaw))
        rel_pitch = max(-half_pitch, min(half_pitch, rel_pitch))
        def approach(curr, desired, rate):
            delta = desired - curr; step = max(-rate*dt, min(rate*dt, delta)); return curr + step
        self.weapon.turret_yaw_deg = approach(self.weapon.turret_yaw_deg, rel_yaw, self.weapon.yaw_rate_deg_s)
        self.weapon.turret_pitch_deg = approach(self.weapon.turret_pitch_deg, rel_pitch, self.weapon.pitch_rate_deg_s)
    def tick(self, dt:float, others:List['Ship'], now:float, rng, bus):
        if not self.alive(): return
        self.dt = dt
        target = find_by_name(others + [self], self.nav.target_name) if self.nav.target_name else None
        if self.ai_mode == 'pursue':
            desired = self.nav.compute_autopilot(self, target); self.nav.desired = desired
        elif self.ai_mode == 'evade':
            base = (self.position - (target.position if target else self.position)).normalized()
            self.nav.autopilot = False; self.nav.desired = base * self.nav.max_thrust
        else:
            desired = self.nav.compute_autopilot(self, target); self.nav.desired = desired
        avail = self.reactors.total_available()
        requested_power = self.nav.desired.norm() * 0.1
        if avail < 0.5 * max(1.0, requested_power):
            self.nav.desired = self.nav.desired * 0.8
        desired = self.nav.desired
        requested_power = desired.norm() * 0.1
        used_power = self.reactors.tick(dt, requested_power)
        power_ratio = (used_power / max(1e-6, requested_power)) if requested_power > 1e-6 else 1.0
        self.thrust_out = desired * max(0.0, min(1.0, power_ratio))
        a = self.thrust_out * (1.0 / max(1e-6, self.mass))
        self.velocity = self.velocity + a * dt
        self.position = self.position + self.velocity * dt
        passive = self.sensors.passive_detect(self, [s for s in others if s is not self and s.alive()], now, rng)
        if passive: bus.publish("sensor.passive", {"type":"sensor.passive","ship": self.name, "contacts": passive})
        if self.weapon:
            self.weapon.tick(dt)
            if target is not None: self._slew_turret_towards_target(dt, target)
        self._crew_repair_tick(dt)
def find_by_name(ships:List['Ship'], name:str|None):
    if not name: return None
    for s in ships:
        if s.name == name: return s
    return None
