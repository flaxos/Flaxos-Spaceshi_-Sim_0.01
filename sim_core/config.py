from __future__ import annotations
import json
from typing import List, Dict, Any
from .vec import Vec3
from .power import PowerBus, Reactor
from .weapons import Weapon
from .sensors import SensorSystem
from .navigation import NavigationSystem
from .ship import Ship
def vec_from(obj:Dict[str,Any], key:str)->Vec3:
    v = obj.get(key, None); return Vec3.from_dict(v) if isinstance(v, dict) else Vec3()
def make_ship_from_dict(e:Dict[str,Any])->Ship:
    reactors = PowerBus([Reactor(name=r['name'], max_output=r['max_output'], warmup_time=r.get('warmup_time', 10.0),
                                 heat_per_output=r.get('heat_per_output', 0.02), cooldown_rate=r.get('cooldown_rate', 1.5),
                                 online=r.get('online', True), health=r.get('health', 100.0))
                         for r in e['reactors']])
    weapon=None
    if e.get('weapon'):
        w=e['weapon']
        weapon=Weapon(
            name=w['name'],
            kind=w.get('kind','railgun'),
            power_per_shot=w.get('power_per_shot',10.0),
            heat_per_shot=w.get('heat_per_shot',20.0),
            cooldown=w.get('cooldown',5.0),
            max_range=w.get('max_range',3000.0),
            damage=w.get('damage',10.0),
            muzzle_velocity=w.get('muzzle_velocity',2000.0),
            fov_deg=w.get('fov_deg',10.0),
            spread_deg=w.get('spread_deg',0.5),
            burst_count=w.get('burst_count',1),
            burst_interval=w.get('burst_interval',0.1),
            falloff_start=w.get('falloff_start',0.6),
            falloff_end=w.get('falloff_end',1.0),
            health=w.get('health', 100.0),
            arc_yaw_deg=w.get('arc_yaw_deg', 120.0),
            arc_pitch_deg=w.get('arc_pitch_deg', 60.0),
            missile_speed=w.get('missile_speed', 900.0),
            max_turn_deg_s=w.get('max_turn_deg_s', 45.0),
            seeker_fov_deg=w.get('seeker_fov_deg', 40.0),
            pn_gain=w.get('pn_gain', 3.0),
            eccm=w.get('eccm', 0.0),
            ecm_susceptibility=w.get('ecm_susceptibility', 0.5),
            warhead=w.get('warhead', 'kinetic'),
            missile_damage=w.get('missile_damage', 150.0),
            prox_radius=w.get('prox_radius', 30.0)
        )
    nav=NavigationSystem(max_thrust=e['nav']['max_thrust'],
                         autopilot=e['nav'].get('autopilot',True),
                         target_name=e['nav'].get('target'),
                         yaw=e['nav'].get('yaw', 0.0),
                         pitch=e['nav'].get('pitch', 0.0),
                         roll=e['nav'].get('roll', 0.0))
    sensors=SensorSystem(range_m=e['sensors']['range_m'],
                         fov_deg=e['sensors'].get('fov_deg',120.0),
                         passive_threshold=e['sensors'].get('passive_threshold',0.005),
                         ping_cooldown=e['sensors'].get('ping_cooldown',10.0),
                         health=e['sensors'].get('health', 100.0))
    s=Ship(name=e['name'], mass=e['mass'], position=vec_from(e,'position'), velocity=vec_from(e,'velocity'),
           nav=nav, sensors=sensors, reactors=reactors, weapon=weapon, ai_mode=e.get('ai_mode','idle'))
    s.subsys['engines']=e.get('subsys',{}).get('engines', 100.0)
    s.crew_repair_rate=e.get('crew_repair_rate', s.crew_repair_rate)
    s.ecm_power=e.get('ecm_power', 0.0)
    return s
def load_ships(path:str)->List[Ship]:
    with open(path, 'r', encoding='utf-8') as f: data = json.load(f)
    return [make_ship_from_dict(e) for e in data]
