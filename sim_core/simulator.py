from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import random, threading, time, math, json
from .event_bus import EventBus
from .ship import Ship, find_by_name
from .vec import Vec3
from .missile import Missile
@dataclass
class Projectile:
    attacker: str; target: str; damage: float; speed: float
    start_pos: Vec3; dir: Vec3; travel_time: float; time_left: float
class Recorder:
    def __init__(self, path:str, interval:float=0.5):
        self.path = path; self.interval = interval; self._acc = 0.0; self._f = open(path, 'w', encoding='utf-8')
    def snapshot(self, sim:'Simulator'):
        rec = {'t': round(sim.t,2),
               'ships':[{'name': s.name, 'pos': s.position.to_dict(), 'vel': s.velocity.to_dict(),
                         'hull': s.hull, 'subsys': s.subsys, 'attitude':{'yaw':s.nav.yaw,'pitch':s.nav.pitch,'roll':s.nav.roll},
                         'weapon': {'heat': getattr(s.weapon,'heat',0.0) if s.weapon else 0.0, 'jammed': getattr(s.weapon,'jammed',False) if s.weapon else False}} for s in sim.ships]}
        self._f.write(json.dumps({'type':'snapshot','data':rec}, separators=(',',':')) + '\n'); self._f.flush()
    def event(self, ev:Dict[str,Any]):
        self._f.write(json.dumps({'type':'event','data':ev}, separators=(',',':')) + '\n'); self._f.flush()
    def close(self): self._f.close()
class Simulator:
    def __init__(self, ships: List[Ship], dt: float, bus: Optional[EventBus]=None, scenario: Optional[object]=None):
        self.ships = ships; self.dt = dt; self.t = 0.0
        self.bus = bus or EventBus(); self._rng = random.Random(0)
        self.projectiles: List[Projectile] = []
        self.missiles: List[Missile] = []
        self.events: List[Dict[str,Any]] = []
        self.scenario = scenario; self.mission_status: Dict[str,Any] = {'status':'running'} if scenario else {'status':'no_scenario'}
        self.recorder: Optional[Recorder] = None; self._rec_acc = 0.0
        self.debrief: Dict[str,Any] = {'started_at': 0.0, 'ended_at': None, 'ships': {}}
        for s in self.ships:
            self.debrief['ships'][s.name] = {'shots_fired':0, 'hits':0, 'damage_dealt':0.0, 'damage_taken':0.0, 'max_weapon_heat':0.0}
        self.bus.subscribe('combat.hit', self._on_event)
        self.bus.subscribe('sensor.passive', self._on_event)
        self.bus.subscribe('scenario.update', self._on_event)
        self.bus.subscribe('scenario.message', self._on_event)
    def _on_event(self, data:Any):
        data = dict(data); data['sim_t']=round(self.t,2); self.events.append(data)
        if self.recorder: self.recorder.event(data)
        if len(self.events)>400: self.events = self.events[-400:]
        if data.get('type')=='hit':
            a=data.get('attacker'); d=float(data.get('damage',0.0)); t=data.get('target')
            if a in self.debrief['ships']: 
                self.debrief['ships'][a]['hits'] += 1; self.debrief['ships'][a]['damage_dealt'] += d
            if t in self.debrief['ships']:
                self.debrief['ships'][t]['damage_taken'] += d
    def _ship_by_name(self, name:str)->Optional[Ship]: return find_by_name(self.ships, name)
    def _angle_deg(self, a:Vec3, b:Vec3)->float:
        na=a.norm(); nb=b.norm()
        if na<1e-6 or nb<1e-6: return 0.0
        c=max(-1.0, min(1.0, a.dot(b)/(na*nb))); return math.degrees(math.acos(c))
    def fire_weapon(self, attacker_name:str, target_name:str)->Dict[str,Any]:
        a = self._ship_by_name(attacker_name); b = self._ship_by_name(target_name)
        if not a or not b: return {'ok': False, 'error':'attacker or target missing'}
        if not a.alive() or not b.alive(): return {'ok': False, 'error':'destroyed'}
        if not a.weapon or a.weapon.health<=0.0: return {'ok': False, 'error':'no weapon'}
        kind = getattr(a.weapon, 'kind', 'railgun')
        r = b.position - a.position; dist = r.norm()
        if dist > a.weapon.max_range: return {'ok': False, 'error':'out of range', 'range': dist}
        fwd = a.forward(); angle = self._angle_deg(fwd, r)
        if angle > (a.weapon.fov_deg/2.0): return {'ok': False, 'error':'outside fov', 'angle': angle}
        half_yaw = a.weapon.arc_yaw_deg * 0.5; half_pitch = a.weapon.arc_pitch_deg * 0.5
        az_world, el_world = a.bearing_elev_to(b.position)
        ship_yaw_deg = math.degrees(a.nav.yaw); ship_pitch_deg = math.degrees(a.nav.pitch)
        rel_yaw = ((az_world - ship_yaw_deg + 180.0) % 360.0) - 180.0
        rel_pitch = ((el_world - ship_pitch_deg + 180.0) % 360.0) - 180.0
        if abs(rel_yaw) > half_yaw or abs(rel_pitch) > half_pitch: return {'ok': False, 'error':'outside_arc'}
        tol = 2.0
        if abs(a.weapon.turret_yaw_deg - rel_yaw) > tol or abs(a.weapon.turret_pitch_deg - rel_pitch) > tol:
            return {'ok': False, 'error':'slewing'}
        if not a.weapon.fire(a.reactors, self._rng): return {'ok': False, 'error':'jammed' if a.weapon.jammed else 'insufficient power'}
        self.debrief['ships'][a.name]['shots_fired'] += max(1, a.weapon.burst_count)
        self.debrief['ships'][a.name]['max_weapon_heat'] = max(self.debrief['ships'][a.name]['max_weapon_heat'], getattr(a.weapon,'heat',0.0))
        if kind == 'launcher':
            name = f"{a.name}-MSL-{int(self.t*1000)}"
            m = Missile(name=name, attacker=a.name, target=b.name, pos=a.position, vel=a.forward()*a.weapon.muzzle_velocity,
                        speed=a.weapon.missile_speed, max_turn_deg_s=a.weapon.max_turn_deg_s, seeker_fov_deg=a.weapon.seeker_fov_deg,
                        pn_gain=a.weapon.pn_gain, eccm=a.weapon.eccm, ecm_susceptibility=a.weapon.ecm_susceptibility,
                        warhead=a.weapon.warhead, damage=a.weapon.missile_damage, prox_radius=a.weapon.prox_radius,
                        max_range=a.weapon.max_range)
            self.missiles.append(m)
            return {'ok': True, 'launched': name}
        eta = dist / max(1.0, a.weapon.muzzle_velocity)
        dir_vec = r.normalized()
        p = Projectile(attacker=a.name, target=b.name, damage=a.weapon.damage, speed=a.weapon.muzzle_velocity,
                       start_pos=a.position, dir=dir_vec, travel_time=eta, time_left=eta)
        self.projectiles.append(p)
        return {'ok': True, 'burst': 1, 'eta': eta}
    def _pd_attempt(self, defender: Ship, missile: Missile):
        r = missile.pos - defender.position; dist = r.norm(); w = defender.weapon
        if not w or w.health<=0.0: return
        if getattr(w,'kind','railgun')!='pdc': return
        if dist > w.max_range: return
        fwd = defender.forward(); na=fwd.norm(); nb=r.norm()
        if na<1e-6 or nb<1e-6: return
        c=max(-1.0, min(1.0, (fwd.dot(r)/(na*nb)))); ang = math.degrees(math.acos(c))
        if ang > (w.fov_deg/2.0): return
        az, el = defender.bearing_elev_to(missile.pos)
        ship_yaw_deg = math.degrees(defender.nav.yaw); ship_pitch_deg = math.degrees(defender.nav.pitch)
        rel_yaw = ((az - ship_yaw_deg + 180.0) % 360.0) - 180.0
        rel_pitch = ((el - ship_pitch_deg + 180.0) % 360.0) - 180.0
        if abs(rel_yaw) > w.arc_yaw_deg*0.5 or abs(rel_pitch) > w.arc_pitch_deg*0.5: return
        kill_factor = max(0.0, 1.0 - dist / max(1.0, w.max_range))
        if w.fire(defender.reactors, self._rng):
            if kill_factor >= 0.35:
                missile.alive=False
                try: self.missiles.remove(missile)
                except ValueError: pass
                self.bus.publish('combat.hit', {'type':'pd_kill','attacker': defender.name, 'target': missile.name, 'damage': 1.0})
    def _update_mission(self):
        if not self.scenario: self.mission_status={'status':'no_scenario'}; return
        self.mission_status = self.scenario.evaluate(self); self.bus.publish('scenario.update', self.mission_status)
        if self.mission_status.get('status') in ('won','lost') and self.debrief.get('ended_at') is None:
            self.debrief['ended_at'] = self.t
    def projectiles_state(self)->List[Dict[str,Any]]:
        return [{'attacker':p.attacker,'target':p.target,'pos':p.start_pos.to_dict(),'dir':p.dir.to_dict(),'eta':p.time_left} for p in self.projectiles]
    def missiles_state(self)->List[Dict[str,Any]]:
        return [m.to_dict() for m in self.missiles]
    def tick(self):
        now = self.t
        for s in self.ships:
            others = [o for o in self.ships if o is not s]
            s.tick(self.dt, others, now, self._rng, self.bus)
        for s in self.ships:
            if s.weapon and getattr(s.weapon,'kind','railgun')=='pdc':
                threats = [m for m in self.missiles if m.target==s.name and m.alive]
                if threats:
                    threats.sort(key=lambda m:(m.pos - s.position).norm())
                    self._pd_attempt(s, threats[0])
        for m in list(self.missiles):
            tgt = self._ship_by_name(m.target)
            if not m.alive or not tgt or not tgt.alive():
                m.alive=False
                try: self.missiles.remove(m)
                except ValueError: pass
                continue
            target_ecm = getattr(tgt, 'ecm_power', 0.0)
            m.tick(self.dt, tgt.position, tgt.velocity, target_ecm)
            if not m.alive:
                if m.warhead == 'nuke':
                    radius = 800.0
                    for s in self.ships:
                        d = (s.position - m.pos).norm()
                        if d <= radius:
                            frac = max(0.0, 1.0 - d/radius)
                            dmg = m.damage * (0.3 + 0.7*frac)
                            s.take_damage(dmg, self._rng)
                            self.bus.publish('combat.hit', {'type':'hit','attacker': m.attacker, 'target': s.name, 'damage': dmg})
                else:
                    if (tgt.position - m.pos).norm() <= m.prox_radius*2.0:
                        tgt.take_damage(m.damage, self._rng)
                        self.bus.publish('combat.hit', {'type':'hit','attacker': m.attacker, 'target': tgt.name, 'damage': m.damage})
                try: self.missiles.remove(m)
                except ValueError: pass
        for p in list(self.projectiles):
            p.time_left -= self.dt
            if p.time_left <= 0.0:
                tgt = self._ship_by_name(p.target)
                if tgt and tgt.alive() and p.damage>0.0:
                    tgt.take_damage(p.damage, self._rng)
                    self.bus.publish('combat.hit', {'type':'hit','attacker': p.attacker, 'target': p.target, 'damage': p.damage})
                self.projectiles.remove(p)
        self.t += self.dt
        if self.scenario:
            self._update_mission()
        if self.recorder:
            self._rec_acc += self.dt
            if self._rec_acc >= self.recorder.interval:
                self.recorder.snapshot(self); self._rec_acc = 0.0
    def start_record(self, path:str, interval:float=0.5)->bool:
        self.recorder = Recorder(path, interval); self._rec_acc = 0.0; return True
    def stop_record(self)->bool:
        if not self.recorder: return False
        self.recorder.close(); self.recorder=None; return True
    def drain_events(self)->List[Dict[str,Any]]:
        ev=self.events; self.events=[]; return ev
    def status(self)->List[Dict[str,Any]]:
        return [{'t': self.t, 'name': s.name, 'pos': s.position.to_dict(), 'vel': s.velocity.to_dict(), 'hull': s.hull,
                 'subsys': s.subsys, 'autopilot': s.nav.autopilot,
                 'attitude':{'yaw':s.nav.yaw,'pitch':s.nav.pitch,'roll':s.nav.roll},
                 'power_avail': s.reactors.total_available(),
                 'reactor_heat': [r.heat for r in s.reactors.reactors],
                 'weapon': {'heat': getattr(s.weapon,'heat',0.0) if s.weapon else 0.0, 'jammed': getattr(s.weapon,'jammed',False) if s.weapon else False,
                            'arc_yaw_deg': getattr(s.weapon,'arc_yaw_deg',0.0) if s.weapon else 0.0,
                            'arc_pitch_deg': getattr(s.weapon,'arc_pitch_deg',0.0) if s.weapon else 0.0,
                            'muzzle_velocity': getattr(s.weapon,'muzzle_velocity',1500.0) if s.weapon else 1500.0,
                            'max_heat': getattr(s.weapon,'max_heat',100.0) if s.weapon else 100.0}} for s in self.ships]
    def reset_mission(self):
        self.t=0.0; self.projectiles=[]; self.missiles=[]; self.events=[]
        for s in self.ships:
            s.hull=100.0; s.velocity=Vec3(); s.position=Vec3()
        self.debrief = {'started_at': 0.0, 'ended_at': None, 'ships': {s.name:{'shots_fired':0,'hits':0,'damage_dealt':0.0,'damage_taken':0.0,'max_weapon_heat':0.0} for s in self.ships}}
        self.mission_status={'status':'running'}
        return True
class SimRunner:
    def __init__(self, sim: Simulator):
        self.sim=sim; self._lock=threading.RLock(); self._running=False; self._th=None; self._paused=False
    def start(self):
        if self._running: return
        self._running=True; self._th=threading.Thread(target=self._loop, daemon=True); self._th.start()
    def _loop(self):
        while self._running:
            time.sleep(self.sim.dt if not self._paused else 0.02)
            if self._paused: continue
            with self._lock: self.sim.tick()
    def pause(self, on:bool):
        self._paused = bool(on)
    def stop(self):
        self._running=False
    def with_lock(self, fn, *a, **kw):
        with self._lock: return fn(*a, **kw)
