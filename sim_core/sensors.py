from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any
@dataclass
class SensorSystem:
    range_m: float; fov_deg: float; passive_threshold: float; ping_cooldown: float
    last_ping: float = -1e9
    last_passive: List[Dict[str,Any]] = field(default_factory=list)
    last_active: List[Dict[str,Any]] = field(default_factory=list)
    health: float = 100.0
    _next_passive_update: float = 0.0
    def passive_detect(self, self_ship, others, now, rng):
        if self.health<=0.0: self.last_passive=[]; return []
        if now < self._next_passive_update and self.last_passive: return self.last_passive
        self._next_passive_update = now + 0.3
        contacts = []
        for o in others:
            rvec = o.position - self_ship.position
            dist = rvec.norm()
            if dist > self.range_m * max(0.2, self.health/100.0): continue
            signature = o.passive_signature() if hasattr(o, 'passive_signature') else 5.0
            if signature / max(1.0, dist) >= self.passive_threshold:
                contacts.append({"type":"passive","name":getattr(o,'name','?'),"range":dist})
        self.last_passive = contacts
        return contacts
    def active_ping(self, self_ship, others, now):
        if self.health<=0.0: self.last_active=[]; return False, []
        if now - self.last_ping < self.ping_cooldown: return False, []
        self.last_ping = now; contacts=[]
        for o in others:
            rvec = o.position - self_ship.position; dist = rvec.norm()
            if dist <= self.range_m * max(0.2, self.health/100.0):
                contacts.append({"type":"active","name":getattr(o,'name','?'),"range":dist})
        self.last_active = contacts; return True, contacts
