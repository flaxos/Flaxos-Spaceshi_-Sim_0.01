from __future__ import annotations
from dataclasses import dataclass
import random
@dataclass
class Weapon:
    name: str
    kind: str = 'railgun'  # 'railgun'|'pdc'|'launcher'
    power_per_shot: float = 10.0
    heat_per_shot: float = 20.0
    cooldown: float = 5.0
    max_range: float = 3000.0
    damage: float = 12.0
    muzzle_velocity: float = 1800.0
    fov_deg: float = 12.0
    spread_deg: float = 0.6
    burst_count: int = 1
    burst_interval: float = 0.1
    falloff_start: float = 0.5
    falloff_end: float = 1.0
    max_heat: float = 100.0
    jam_threshold: float = 90.0
    jam_clear: float = 60.0
    cool_rate: float = 2.0
    jammed: bool = False
    arc_yaw_deg: float = 140.0
    arc_pitch_deg: float = 80.0
    yaw_rate_deg_s: float = 90.0
    pitch_rate_deg_s: float = 90.0
    turret_yaw_deg: float = 0.0
    turret_pitch_deg: float = 0.0
    _cooldown_left: float = 0.0
    heat: float = 0.0
    health: float = 100.0
    # Launcher params
    missile_speed: float = 900.0
    max_turn_deg_s: float = 45.0
    seeker_fov_deg: float = 40.0
    pn_gain: float = 3.0
    eccm: float = 0.0
    ecm_susceptibility: float = 0.5
    warhead: str = 'kinetic'
    missile_damage: float = 150.0
    prox_radius: float = 30.0
    def ready(self)->bool:
        return self._cooldown_left <= 1e-6 and self.health>0.0 and (not self.jammed)
    def tick(self, dt:float):
        self._cooldown_left = max(0.0, self._cooldown_left - dt)
        self.heat = max(0.0, self.heat - self.cool_rate*dt)
        if self.jammed and self.heat <= self.jam_clear:
            self.jammed = False
        if self.health>0.0 and self.health<100.0:
            self.health = min(100.0, self.health + 0.02*dt)
    def try_jam_due_to_heat(self, rng: random.Random)->bool:
        if self.heat < self.jam_threshold: return False
        t = min(1.0, max(0.0, (self.heat - self.jam_threshold) / max(1e-6, self.max_heat - self.jam_threshold)))
        p = 0.10 + 0.80 * t
        if rng.random() < p:
            self.jammed = True
            return True
        return False
    def fire(self, power_bus, rng: random.Random)->bool:
        if not self.ready(): return False
        if self.try_jam_due_to_heat(rng): return False
        got = power_bus.allocate(self.power_per_shot)
        if got + 1e-6 < self.power_per_shot: return False
        self._cooldown_left = self.cooldown
        self.heat = min(self.max_heat, self.heat + self.heat_per_shot)
        return True
