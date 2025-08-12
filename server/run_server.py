import json, socket, threading, argparse
from sim_core.simulator import Simulator, SimRunner
from sim_core.config import load_ships
from sim_core.event_bus import EventBus
def serve(host, port, dt, fleet_path):
    ships = load_ships(fleet_path)
    sim = Simulator(ships, dt=dt, bus=EventBus())
    runner = SimRunner(sim); runner.start()
    print(f"Server on {host}:{port} dt={dt}")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port)); srv.listen(8)
    def handle(conn):
        buf = b''
        try:
            while True:
                data = conn.recv(4096)
                if not data: break
                buf += data
                if b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        req = json.loads(line.decode('utf-8'))
                    except Exception:
                        conn.sendall((json.dumps({"ok":False,"error":"bad json"})+"\n").encode('utf-8')); break
                    resp = dispatch(sim, runner, req)
                    conn.sendall((json.dumps(resp)+"\n").encode('utf-8'))
                    break
        finally:
            conn.close()
    while True:
        c,_ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()
def dispatch(sim, runner, req):
    cmd = req.get("cmd")
    if cmd=="get_state":
        return {"ok":True, "t": sim.t, "ships": sim.status(), "projectiles": sim.projectiles_state() if hasattr(sim,'projectiles_state') else [], "missiles": sim.missiles_state() if hasattr(sim,'missiles_state') else []}
    if cmd=="get_events": return {"ok": True, "events": sim.drain_events()}
    if cmd=="get_mission": return {"ok": True, "mission": sim.mission_status}
    if cmd=="get_debrief": return {"ok": True, "debrief": sim.debrief}
    if cmd=="helm_override":
        ship=req.get("ship"); en=bool(req.get("enabled", True))
        for s in sim.ships:
            if s.name==ship: s.nav.autopilot = not bool(en); return {"ok": True, "autopilot": s.nav.autopilot}
        return {"ok": False, "error":"ship not found"}
    if cmd=="set_target":
        ship=req.get("ship"); tgt=req.get("target")
        for s in sim.ships:
            if s.name==ship: s.nav.target_name=tgt; s.nav.autopilot=True; return {"ok": True}
        return {"ok": False, "error":"ship not found"}
    if cmd=="set_ai":
        ship=req.get("ship"); mode=req.get("mode")
        for s in sim.ships:
            if s.name==ship: s.ai_mode=mode; return {"ok": True, "mode": mode}
        return {"ok": False, "error":"ship not found"}
    if cmd=="fire_weapon":
        sh=req.get("ship"); tgt=req.get("target"); return sim.fire_weapon(sh, tgt)
    if cmd=="ping_sensors":
        sh=req.get("ship")
        for s in sim.ships:
            if s.name==sh:
                ok,contacts = s.sensors.active_ping(s, [o for o in sim.ships if o is not s], sim.t)
                return {"ok":ok, "contacts": contacts}
        return {"ok": False, "error":"ship not found"}
    if cmd=="start_record":
        p=req.get("path","replay.jsonl"); sim.start_record(p, req.get("interval",0.5)); return {"ok": True, "path": p}
    if cmd=="stop_record": return {"ok": sim.stop_record()}
    if cmd=="pause":
        on=bool(req.get("on", True)); runner.pause(on); return {"ok": True, "paused": on}
    if cmd=="reset_mission": return {"ok": sim.reset_mission()}
    return {"ok": False, "error":"unknown cmd"}
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--dt", type=float, default=0.1)
    ap.add_argument("--config", default="fleet/demo_ships.json")
    args = ap.parse_args()
    serve(args.host, args.port, args.dt, args.config)
