from __future__ import annotations
from typing import Tuple, Optional
import math
from .vec import Vec3
def intercept_direction(shooter_pos:Vec3, target_pos:Vec3, target_vel:Vec3, projectile_speed:float) -> Tuple[Vec3, Optional[float]]:
    r = target_pos - shooter_pos; v = target_vel; s = max(1e-6, projectile_speed)
    a = v.dot(v) - s*s; b = 2.0 * r.dot(v); c = r.dot(r)
    if abs(a) < 1e-12:
        if abs(b) < 1e-12: return r.normalized(), None
        t = -c / b
        if t <= 0: return r.normalized(), None
        aim = r + v * t; return aim.normalized(), t
    disc = b*b - 4*a*c
    if disc < 0: return r.normalized(), None
    sd = math.sqrt(disc); t1 = (-b - sd)/(2*a); t2 = (-b + sd)/(2*a)
    poss = [t for t in (t1,t2) if t>0]
    if not poss: return r.normalized(), None
    t = min(poss); aim = r + v*t; return aim.normalized(), t
