import json, socket, threading, time, math, tkinter as tk
from tkinter import ttk, messagebox
class Client:
    def __init__(self, host='127.0.0.1', port=8765):
        self.host=host; self.port=port; self._lock=threading.RLock()
    def request(self, obj):
        line = (json.dumps(obj) + "\n").encode('utf-8')
        with self._lock:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.connect((self.host, self.port)); s.sendall(line)
            data = b''
            while True:
                ch = s.recv(4096)
                if not ch: break
                data += ch
                if b"\n" in data:
                    break
            s.close()
        if not data: return {"ok": False, "error":"no response"}
        return json.loads(data.decode('utf-8').splitlines()[0])
class HUD(tk.Tk):
    def __init__(self, host='127.0.0.1', port=8765):
        super().__init__()
        self.title("Spacesim HUD — Sprint 2")
        self.geometry("980x720")
        self.client = Client(host, port)
        self.ship_focus = None; self.target = None; self.running=True; self.toast_queue=[]
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg="#0b0f13", highlightthickness=0); self.canvas.grid(row=0, column=0, sticky="nsew")
        side = tk.Frame(self, bg="#131a21"); side.grid(row=0, column=1, sticky="ns")
        ttk.Style().configure("TLabel", background="#131a21", foreground="#e3e7ea"); ttk.Style().configure("TButton", padding=6)
        self.lbl_status = ttk.Label(side, text="Status: —", anchor="w"); self.lbl_status.pack(fill="x", pady=(8,4), padx=8)
        self.obj_box = tk.Text(side, width=34, height=18, bg="#0f141a", fg="#e3e7ea"); self.obj_box.pack(padx=8, pady=4)
        self.debrief_btn = ttk.Button(side, text="Get Debrief", command=self.get_debrief); self.debrief_btn.pack(padx=8, pady=(6,2))
        self.record_btn = ttk.Button(side, text="Start Record (R)", command=self.toggle_record); self.record_btn.pack(padx=8, pady=2)
        self.info_lbl = ttk.Label(side, text="Hotkeys: A Autopilot  F Fire  R Record  P Ping", anchor="w"); self.info_lbl.pack(fill="x", padx=8, pady=(8,12))
        self.recording=False; self.last_state=None; self.after(50, self.loop)
        self.bind("<Key-a>", lambda e: self.toggle_autopilot())
        self.bind("<Key-f>", lambda e: self.fire())
        self.bind("<Key-r>", lambda e: self.toggle_record())
        self.bind("<Key-p>", lambda e: self.ping())
        self.after(200, self.draw_toasts)
    def req(self, obj): return self.client.request(obj)
    def get_state(self): return self.req({"cmd":"get_state"})
    def get_mission(self): return self.req({"cmd":"get_mission"})
    def get_debrief(self):
        r = self.req({"cmd":"get_debrief"})
        messagebox.showinfo("Debrief", json.dumps(r.get("debrief"), indent=2) if r.get("ok") else r.get("error"))
    def toggle_autopilot(self):
        s = self.get_state()
        ships = s.get("ships", [])
        if isinstance(ships, dict):
            ships = list(ships.values())
        if not s.get("ok") or not ships:
            return
        if not self.ship_focus:
            self.ship_focus = ships[0]["name"]
        me = next((x for x in ships if x.get("name") == self.ship_focus), None)
        ap = bool(me.get("autopilot", True)) if me else True
        self.req({"cmd": "helm_override", "ship": self.ship_focus, "enabled": ap})
        self.toast(f"Autopilot → {'ON' if not ap else 'OFF'}")
    def set_target(self, name):
        if not self.ship_focus: return
        self.req({"cmd":"set_target", "ship": self.ship_focus, "target": name}); self.target=name; self.toast(f"Target set: {name}")
    def fire(self):
        if not (self.ship_focus and self.target): self.toast("No target selected"); return
        r = self.req({"cmd":"fire_weapon","ship": self.ship_focus, "target": self.target})
        self.toast("Launched missile" if r.get("launched") else ("Firing" if r.get("ok") else f"Cannot fire: {r.get('error','?')}"))
    def ping(self):
        if not self.ship_focus: return
        r = self.req({"cmd":"ping_sensors", "ship": self.ship_focus})
        self.toast(f"Ping: {len(r.get('contacts', []))} contacts" if r.get("ok") else "Ping failed")
    def toggle_record(self):
        if not self.recording:
            r = self.req({"cmd":"start_record","path": "replay.jsonl"}) 
            if r.get("ok"): self.recording=True; self.record_btn.config(text="Stop Record (R)"); self.toast("Recording started")
        else:
            r = self.req({"cmd":"stop_record"}) 
            if r.get("ok"): self.recording=False; self.record_btn.config(text="Start Record (R)"); self.toast("Recording stopped")
    def loop(self):
        try:
            s = self.get_state(); m = self.get_mission()
            if s.get("ok"):
                self.last_state=s
                if not self.ship_focus and s.get("ships"): self.ship_focus = s["ships"][0]["name"]
                self.draw_scene(s)
            if m.get("ok"):
                self.lbl_status.config(text=f"Status: {m['mission'].get('status','?')}   t={s.get('t','?'):.1f}")
                self.obj_box.delete('1.0', 'end')
                for o in m["mission"].get("objectives", []):
                    t = o.get('type'); tgt=o.get('target'); ok='✓' if o.get('satisfied') else '✗' if o.get('failed') else '…'
                    self.obj_box.insert('end', f"{ok} {t} {tgt or ''}\n")
            ev = self.req({"cmd":"get_events"})
            if ev.get("ok"):
                for e in ev.get("events", []):
                    txt = e.get("text") or e.get("type")
                    if txt: self.toast(txt)
        except Exception:
            pass
        if self.running: self.after(200, self.loop)
    def world_to_radar(self, origin, p, scale, center):
        dx = p['x'] - origin['x']; dy = p['y'] - origin['y']; return center[0] + dx*scale, center[1] + dy*scale
    def draw_scene(self, s):
        c = self.canvas; c.delete("all"); w = c.winfo_width() or 960; h = c.winfo_height() or 640
        radar_r = min(w, h) * 0.35; radar_center = (w*0.45, h*0.5); range_m = 20000.0; scale = radar_r / range_m
        for r in (0.25, 0.5, 0.75, 1.0):
            c.create_oval(radar_center[0]-radar_r*r, radar_center[1]-radar_r*r, radar_center[0]+radar_r*r, radar_center[1]+radar_r*r, outline="#22303a")
        me = next((x for x in s.get("ships",[]) if x.get("name")==self.ship_focus), None)
        if not me: return
        yaw = me.get("attitude",{}).get("yaw",0.0); fwd = (math.cos(yaw), math.sin(yaw))
        c.create_line(radar_center[0], radar_center[1], radar_center[0]+fwd[0]*80, radar_center[1]+fwd[1]*80, fill="#3aa3ff")
        wpn = me.get("weapon",{}); half_yaw = (wpn.get("arc_yaw_deg",120.0) / 2.0); start = math.degrees(yaw) - half_yaw; extent = 2*half_yaw
        c.create_arc(radar_center[0]-radar_r*0.95, radar_center[1]-radar_r*0.95, radar_center[0]+radar_r*0.95, radar_center[1]+radar_r*0.95, start=start, extent=extent, outline="#31506b")
        for ship in s.get("ships", []):
            pos = ship.get("pos", {"x":0,"y":0,"z":0}); x,y = self.world_to_radar(me.get("pos"), pos, scale, radar_center)
            r = 5 if ship['name']!=self.ship_focus else 8
            fill = "#8cc8ff" if ship['name']==self.ship_focus else "#ff6666" if ship['name']==self.target else "#d2d8de"
            c.create_oval(x-r, y-r, x+r, y+r, fill=fill, outline="")
            c.create_text(x, y-12, text=ship['name'], fill="#8fa6b8")
            def make_bind(target_name): return lambda e: (self.set_target(target_name), None)
            c.tag_bind(c.create_text(x, y+10, text=f"{int(ship.get('hull',0))}%", fill="#556979"), "<Button-1>", make_bind(ship['name']))
        missiles = s.get("missiles", [])
        for ms in missiles:
            mp = ms.get("pos", {"x":0,"y":0,"z":0}); mx,my = self.world_to_radar(me.get("pos"), mp, scale, radar_center)
            c.create_rectangle(mx-3,my-3,mx+3,my+3, outline="#ffdd66")
    def toast(self, text): self.toast_queue.append((time.time(), text))
    def draw_toasts(self):
        now = time.time(); y = 12
        for ts,t in list(self.toast_queue):
            if now - ts > 3.0: self.toast_queue.remove((ts,t))
            else: self.canvas.create_text(14, y, text=t, anchor="w", fill="#e6f3ff"); y += 16
        if self.running: self.after(200, self.draw_toasts)
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args(); app = HUD(args.host, args.port); app.mainloop()
