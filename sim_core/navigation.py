from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math
from .vec import Vec3
@dataclass
class NavigationSystem:
    max_thrust: float; desired: Vec3 = field(default_factory=Vec3); autopilot: bool = True
    target_name: Optional[str] = None
    yaw: float = 0.0; pitch: float = 0.0; roll: float = 0.0
    yaw_rate: float = 0.0; pitch_rate: float = 0.0; roll_rate: float = 0.0
    max_yaw_accel: float = 0.3; max_pitch_accel: float = 0.3; max_roll_accel: float = 0.4
    max_yaw_rate: float = 1.5; max_pitch_rate: float = 1.5; max_roll_rate: float = 2.0
    pursuit_style: str = 'auto'
    _last_aim: Vec3 = field(default_factory=Vec3)
    aim_smooth: float = 0.4
    def forward(self)->Vec3:
        cy, sy = math.cos(self.yaw), math.sin(self.yaw); cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        return Vec3(cp*cy, cp*sy, sp).normalized()
    def _drive_axis(self, curr, rate, target, max_accel, max_rate, dt):
        err = (target - curr + math.pi)%(2*math.pi) - math.pi
        a = max(-max_accel, min(max_accel, 2.0*err - 0.8*rate))
        rate = max(-max_rate, min(max_rate, rate + a*dt)); curr = curr + rate*dt; return curr, rate
    def steer_to(self, dt:float, desired_forward:Vec3):
        if desired_forward.norm() < 1e-6: return
        df = desired_forward.normalized()
        yaw_d = math.atan2(df.y, df.x); pitch_d = math.atan2(df.z, math.hypot(df.x, df.y))
        self.yaw, self.yaw_rate = self._drive_axis(self.yaw, self.yaw_rate, yaw_d, self.max_yaw_accel, self.max_yaw_rate, dt)
        self.pitch, self.pitch_rate = self._drive_axis(self.pitch, self.pitch_rate, pitch_d, self.max_pitch_accel, self.max_pitch_rate, dt)
        self.roll, self.roll_rate = self._drive_axis(self.roll, self.roll_rate, 0.0, self.max_roll_accel, self.max_roll_rate, dt)
    def compute_autopilot(self, self_ship, target):
        if not self.autopilot: return self.desired.limit(self.max_thrust)
        if target is None: return self.desired.limit(self.max_thrust)
        to_target = (target.position - self_ship.position)
        rel_vel = (target.velocity - self_ship.velocity)
        rel_speed = max(1.0, rel_vel.norm())
        tau_base = to_target.norm()/rel_speed
        tau_purecap = 10.0; tau_leadcap = 30.0; tau_autocap = 15.0
        style = (self.pursuit_style or 'auto')
        if style == 'pure':
            tau = min(tau_purecap, tau_base); aim_point = target.position
        elif style == 'lead':
            tau = min(tau_leadcap, tau_base); aim_point = target.position + rel_vel * tau
        else:
            closing = -to_target.normalized().dot(rel_vel)
            tau = min(tau_autocap, tau_base)
            aim_point = target.position + (rel_vel * tau if closing < 50.0 else Vec3())
        aim_vec = (aim_point - self_ship.position)
        if self._last_aim.norm() > 1e-6:
            alpha = max(0.0, min(1.0, self.aim_smooth))
            aim_vec = (self._last_aim * alpha + aim_vec * (1.0-alpha))
        self._last_aim = aim_vec
        self.steer_to(self_ship.dt, aim_vec)
        thrust_mag = self.max_thrust if style=='lead' else min(self.max_thrust, aim_vec.norm())
        return aim_vec.normalized() * thrust_mag
