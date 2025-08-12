from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Dict
@dataclass
class Vec3:
    x: float = 0.0; y: float = 0.0; z: float = 0.0
    def __add__(self, o:'Vec3')->'Vec3': return Vec3(self.x+o.x, self.y+o.y, self.z+o.z)
    def __sub__(self, o:'Vec3')->'Vec3': return Vec3(self.x-o.x, self.y-o.y, self.z-o.z)
    def __mul__(self, k:float)->'Vec3': return Vec3(self.x*k, self.y*k, self.z*k)
    __rmul__ = __mul__
    def dot(self, o:'Vec3')->float: return self.x*o.x + self.y*o.y + self.z*o.z
    def norm(self)->float: return math.sqrt(self.x*self.x + self.y*self.y + self.z*self.z)
    def normalized(self)->'Vec3':
        n=self.norm()
        return self if n<=1e-9 else self*(1.0/n)
    def limit(self, max_len:float)->'Vec3':
        n=self.norm()
        if max_len<=0 or n<=max_len: return self
        return self*(max_len/n)
    def to_dict(self)->Dict[str,float]: return {'x':self.x,'y':self.y,'z':self.z}
    @staticmethod
    def from_dict(d:Dict[str,float])->'Vec3': return Vec3(d.get('x',0.0), d.get('y',0.0), d.get('z',0.0))
