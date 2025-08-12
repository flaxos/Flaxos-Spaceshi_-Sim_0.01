from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import math
from .vec import Vec3
@dataclass
class Missile:
    name: str; attacker: str; target: str
    pos: Vec3; vel: Vec3
    speed: float; max_turn_deg_s: float; seeker_fov_deg: float; pn_gain: float
    eccm: float = 0.0; ecm_susceptibility: float = 0.5
    warhead: str = "kinetic"; damage: float = 150.0; prox_radius: float = 30.0; max_range: float = 100000.0
    alive: bool = True; time: float = 0.0
    def to_dict(self)->Dict[str,Any]:
        return {"name": self.name, "pos": self.pos.to_dict(), "vel": self.vel.to_dict(), "target": self.target,
                "speed": self.speed, "alive": self.alive, "warhead": self.warhead}
    def _unit(self, v: Vec3)->Vec3:
        n = v.norm(); return v if n<1e-9 else v*(1.0/n)
    def _angle_deg(self, a:Vec3, b:Vec3)->float:
        na=a.norm(); nb=b.norm()
        if na<1e-6 or nb<1e-6: return 0.0
        c=max(-1.0, min(1.0, a.dot(b)/(na*nb))); return math.degrees(math.acos(c))
    def tick(self, dt: float, target_pos: Vec3, target_vel: Vec3, target_ecm: float) -> None:
        if not self.alive: return
        self.time += dt
        r = target_pos - self.pos
        los = self._unit(r)
        heading = self._unit(self.vel) if self.vel.norm()>=1e-6 else los
        off_deg = self._angle_deg(heading, los)
        effective_fov = self.seeker_fov_deg * (1.0 + 0.5*self.eccm)
        has_fov = off_deg <= effective_fov * 0.5
        lock_factor = (1.0 - target_ecm * self.ecm_susceptibility) * (1.0 + 0.5 * self.eccm)
        lock_factor = max(0.0, min(1.2, lock_factor))
        has_lock = has_fov and lock_factor >= 0.25
        if has_lock:
            rel_speed = max(1.0, (target_vel - self.vel).norm())
            tau = min(20.0, r.norm() / rel_speed)
            aim = (target_pos + target_vel * tau) - self.pos
            desired_dir = self._unit(aim)
        else:
            desired_dir = heading
        max_turn_rad = math.radians(self.max_turn_deg_s) * dt * max(0.2, lock_factor)
        ang = self._angle_deg(heading, desired_dir)
        if ang > 1e-6:
            k = min(1.0, max_turn_rad / math.radians(ang))
            new_dir = self._unit(heading*(1.0 - k) + desired_dir*k)
        else:
            new_dir = desired_dir
        self.vel = new_dir * self.speed
        self.pos = self.pos + self.vel * dt
        dist = (target_pos - self.pos).norm()
        if dist <= self.prox_radius or self.time*self.speed >= self.max_range:
            self.alive = False
