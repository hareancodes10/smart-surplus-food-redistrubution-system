import os, sqlite3, threading, time, json, urllib.request, urllib.parse
from datetime import datetime, timedelta
from functools import wraps
from math import radians, sin, cos, asin, sqrt
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__); CORS(app)
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "surplus.db")
ser = URLSafeTimedSerializer(os.environ.get("SECRET_KEY", "change-me-in-production"))
lock = threading.RLock()
PRESETS = {"T. Nagar": (13.0418, 80.2341), "Adyar": (13.0067, 80.2570), "Anna Nagar": (13.0850, 80.2101),
           "Velachery": (12.9815, 80.2180), "Tambaram": (12.9249, 80.1000), "Porur": (13.0382, 80.1565),
           "Ramapuram": (13.0346, 80.1810)}
DEFAULTS = dict(w_prox=0.4, w_need=0.3, w_cap=0.3, speed_vehicle=25, speed_walk=5, handling_min=15,
                auto_interval_s=60, use_road=1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE, pw TEXT, role TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS donations(id INTEGER PRIMARY KEY, user_id INT, donor TEXT, kind TEXT, food TEXT, quantity INT,
  remaining INT, location TEXT, lat REAL, lng REAL, expires_at TEXT, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS recipients(id INTEGER PRIMARY KEY, user_id INT, name TEXT, kind TEXT, location TEXT, lat REAL,
  lng REAL, daily_capacity INT, max_distance_km REAL, priority INT, has_vehicle INT);
CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY, donation_id INT, recipient_id INT, donor TEXT, food TEXT,
  recipient TEXT, quantity INT, distance_km REAL, eta_min INT, score REAL, route_source TEXT, status TEXT DEFAULT 'assigned',
  created_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value REAL);
CREATE TABLE IF NOT EXISTS dist_cache(k TEXT PRIMARY KEY, km REAL);
"""

def rows(sql, a=()):
    with lock:
        c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row
        try: return [dict(r) for r in c.execute(sql, a).fetchall()]
        finally: c.close()

def run(sql, a=()):
    with lock:
        c = sqlite3.connect(DB, timeout=10)
        try:
            cur = c.execute(sql, a); c.commit(); return cur.lastrowid
        finally: c.close()

def settings():
    s = dict(DEFAULTS); s.update({r["key"]: r["value"] for r in rows("SELECT * FROM settings")}); return s

def hav(a, b):
    p = radians(b[0] - a[0]); l = radians(b[1] - a[1])
    return 2 * 6371 * asin(sqrt(sin(p / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(l / 2) ** 2))

def road_km(a, b, use_road):
    """Road distance via the public OSRM server (cached). Falls back to straight line x 1.3 if offline."""
    straight = hav(a, b)
    if not use_road: return straight * 1.3, "estimate"
    k = f"{a[0]:.4f},{a[1]:.4f}|{b[0]:.4f},{b[1]:.4f}"
    hit = rows("SELECT km FROM dist_cache WHERE k=?", (k,))
    if hit: return hit[0]["km"], "road"
    try:
        url = f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?overview=false"
        with urllib.request.urlopen(url, timeout=3) as r:
            km = json.load(r)["routes"][0]["distance"] / 1000
        run("INSERT OR REPLACE INTO dist_cache VALUES(?,?)", (k, km)); return km, "road"
    except Exception:
        return straight * 1.3, "estimate"

def geocode(text):
    t = (text or "").strip()
    for n, c in PRESETS.items():
        if n.lower() == t.lower(): return n, c
    if not t: return None, None
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": t, "format": "json", "limit": 1, "countrycodes": "in"})
        req = urllib.request.Request(url, headers={"User-Agent": "smart-surplus-student-project"})
        with urllib.request.urlopen(req, timeout=4) as r: j = json.load(r)
        if j: return t, (float(j[0]["lat"]), float(j[0]["lon"]))
    except Exception: pass
    return None, None

def recipients_view(where="", a=()):
    today = datetime.now().strftime("%Y-%m-%d")
    used = {r["recipient_id"]: r["u"] for r in rows("SELECT recipient_id,SUM(quantity) u FROM matches WHERE created_at LIKE ? GROUP BY recipient_id", (today + "%",))}
    out = rows("SELECT * FROM recipients " + where, a)
    for r in out:
        r["capacity_left"] = r["daily_capacity"] - used.get(r["id"], 0); r["has_vehicle"] = bool(r["has_vehicle"])
    return out

def allocate():
    """Urgency-first greedy matching. Score = w_prox*proximity + w_need*need + w_cap*capacity fit (weights from settings)."""
    with lock:
        S = settings(); tw = (S["w_prox"] + S["w_need"] + S["w_cap"]) or 1
        recs = recipients_view(); made = 0
        for d in rows("SELECT * FROM donations WHERE remaining>0 AND status!='expired' ORDER BY expires_at"):
            mins = (datetime.fromisoformat(d["expires_at"]) - datetime.now()).total_seconds() / 60
            if mins <= 0: run("UPDATE donations SET status='expired' WHERE id=?", (d["id"],)); continue
            cands = []
            for r in recs:
                if r["capacity_left"] <= 0 or hav((d["lat"], d["lng"]), (r["lat"], r["lng"])) > r["max_distance_km"]: continue
                km, src = road_km((d["lat"], d["lng"]), (r["lat"], r["lng"]), S["use_road"])
                eta = km / (S["speed_vehicle"] if r["has_vehicle"] else S["speed_walk"]) * 60 + S["handling_min"]
                if km > r["max_distance_km"] or eta > mins: continue
                sc = (S["w_prox"] * (1 - km / r["max_distance_km"]) + S["w_need"] * r["priority"] / 5
                      + S["w_cap"] * min(1, r["capacity_left"] / d["remaining"])) / tw
                cands.append((sc, r, km, eta, src))
            rem = d["remaining"]
            for sc, r, km, eta, src in sorted(cands, key=lambda c: -c[0]):
                if rem <= 0: break
                n = min(rem, r["capacity_left"]); rem -= n; r["capacity_left"] -= n; made += 1
                run("INSERT INTO matches(donation_id,recipient_id,donor,food,recipient,quantity,distance_km,eta_min,score,route_source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (d["id"], r["id"], d["donor"], d["food"], r["name"], n, round(km, 1), round(eta), round(sc, 2), src, datetime.now().isoformat()))
            st = "allocated" if rem == 0 else ("partial" if rem < d["quantity"] else "pending")
            run("UPDATE donations SET remaining=?, status=? WHERE id=?", (rem, st, d["id"]))
        return made

def auth(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            try: uid = ser.loads(request.headers.get("Authorization", "")[7:], max_age=7 * 86400)
            except Exception: return jsonify(error="Please log in."), 401
            u = rows("SELECT id,email,name,role FROM users WHERE id=?", (uid,))
            if not u: return jsonify(error="Please log in."), 401
            g.user = u[0]
            if roles and g.user["role"] not in roles: return jsonify(error="Your role cannot do this."), 403
            return f(*a, **k)
        return w
    return deco

def token(u): return jsonify(token=ser.dumps(u["id"]), user=dict(id=u["id"], email=u["email"], name=u["name"], role=u["role"]))

@app.post("/api/register")
def register():
    j = request.json or {}
    email = (j.get("email") or "").strip().lower()
    if "@" not in email or len(j.get("password") or "") < 6 or not (j.get("name") or "").strip() or j.get("role") not in ("donor", "recipient"):
        return jsonify(error="Enter a name, valid email, password (6+ chars) and a role."), 400
    if rows("SELECT 1 FROM users WHERE email=?", (email,)): return jsonify(error="Email already registered."), 400
    uid = run("INSERT INTO users(email,pw,role,name) VALUES(?,?,?,?)", (email, generate_password_hash(j["password"]), j["role"], j["name"].strip()))
    return token(rows("SELECT * FROM users WHERE id=?", (uid,))[0])

@app.post("/api/login")
def login():
    j = request.json or {}
    u = rows("SELECT * FROM users WHERE email=?", ((j.get("email") or "").strip().lower(),))
    if not u or not check_password_hash(u[0]["pw"], j.get("password") or ""): return jsonify(error="Wrong email or password."), 401
    return token(u[0])

@app.get("/api/me")
@auth()
def me(): return jsonify(g.user)

@app.get("/api/locations")
def locations(): return jsonify(list(PRESETS))

@app.get("/api/donations")
@auth("admin", "donor")
def get_donations():
    allocate_expiry()
    if g.user["role"] == "admin": return jsonify(rows("SELECT * FROM donations ORDER BY id DESC"))
    return jsonify(rows("SELECT * FROM donations WHERE user_id=? ORDER BY id DESC", (g.user["id"],)))

def allocate_expiry():
    run("UPDATE donations SET status='expired' WHERE remaining>0 AND expires_at<=?", (datetime.now().isoformat(),))

@app.post("/api/donations")
@auth("admin", "donor")
def post_donation():
    j = request.json or {}
    try:
        qty = int(j["quantity"]); hrs = float(j["hours"]); donor = j["donor"].strip(); food = j["food"].strip()
        assert qty > 0 and hrs > 0 and donor and food
    except Exception: return jsonify(error="Check donor, food, servings and expiry hours."), 400
    loc, c = geocode(j.get("location"))
    if not c: return jsonify(error="Location not found. Pick a listed area or type a fuller address (needs internet)."), 400
    run("INSERT INTO donations(user_id,donor,kind,food,quantity,remaining,location,lat,lng,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (g.user["id"], donor, j.get("kind", "Restaurant"), food, qty, qty, loc, c[0], c[1], (datetime.now() + timedelta(hours=hrs)).isoformat()))
    allocate()  # auto-allocate immediately
    return jsonify(ok=True), 201

@app.get("/api/recipients")
@auth("admin", "recipient")
def get_recipients():
    if g.user["role"] == "admin": return jsonify(recipients_view("ORDER BY id DESC"))
    return jsonify(recipients_view("WHERE user_id=?", (g.user["id"],)))

@app.post("/api/recipients")
@auth("admin", "recipient")
def post_recipient():
    j = request.json or {}
    try:
        cap = int(j["capacity"]); dist = float(j["max_distance_km"]); pr = int(j["priority"]); name = j["name"].strip()
        assert cap > 0 and dist > 0 and 1 <= pr <= 5 and name
    except Exception: return jsonify(error="Check name, capacity, distance and need level (1-5)."), 400
    if g.user["role"] == "recipient" and rows("SELECT 1 FROM recipients WHERE user_id=?", (g.user["id"],)):
        return jsonify(error="You already have a recipient profile."), 400
    loc, c = geocode(j.get("location"))
    if not c: return jsonify(error="Location not found. Pick a listed area or type a fuller address (needs internet)."), 400
    run("INSERT INTO recipients(user_id,name,kind,location,lat,lng,daily_capacity,max_distance_km,priority,has_vehicle) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (g.user["id"], name, j.get("kind", "Shelter"), loc, c[0], c[1], cap, dist, pr, int(bool(j.get("has_vehicle")))))
    allocate()
    return jsonify(ok=True), 201

@app.post("/api/allocate")
@auth("admin")
def allocate_now(): return jsonify(made=allocate())

@app.get("/api/matches")
@auth()
def get_matches():
    u = g.user
    if u["role"] == "admin": return jsonify(rows("SELECT * FROM matches ORDER BY id DESC"))
    if u["role"] == "donor": return jsonify(rows("SELECT * FROM matches WHERE donation_id IN (SELECT id FROM donations WHERE user_id=?) ORDER BY id DESC", (u["id"],)))
    return jsonify(rows("SELECT * FROM matches WHERE recipient_id IN (SELECT id FROM recipients WHERE user_id=?) ORDER BY id DESC", (u["id"],)))

@app.patch("/api/matches/<int:mid>")
@auth("admin", "recipient")
def collect(mid):
    m = rows("SELECT * FROM matches WHERE id=?", (mid,))
    if not m: return jsonify(error="Not found"), 404
    if g.user["role"] == "recipient" and not rows("SELECT 1 FROM recipients WHERE id=? AND user_id=?", (m[0]["recipient_id"], g.user["id"])):
        return jsonify(error="This pickup is not yours."), 403
    run("UPDATE matches SET status='collected' WHERE id=?", (mid,)); return jsonify(ok=True)

@app.get("/api/stats")
@auth()
def stats():
    allocate_expiry()
    t = rows("SELECT COALESCE(SUM(quantity),0) t FROM donations")[0]["t"]
    a = rows("SELECT COALESCE(SUM(quantity),0) t FROM matches")[0]["t"]
    c = rows("SELECT COALESCE(SUM(quantity),0) t FROM matches WHERE status='collected'")[0]["t"]
    w = rows("SELECT COALESCE(SUM(remaining),0) t FROM donations WHERE status='expired'")[0]["t"]
    return jsonify(total=t, allocated=a, collected=c, wasted=w, rate=round(100 * a / t) if t else 0,
                   open_donations=rows("SELECT COUNT(*) n FROM donations WHERE remaining>0 AND status!='expired'")[0]["n"],
                   recipients=rows("SELECT COUNT(*) n FROM recipients")[0]["n"])

@app.get("/api/settings")
@auth("admin")
def get_settings(): return jsonify(settings())

@app.put("/api/settings")
@auth("admin")
def put_settings():
    j = request.json or {}
    for k in DEFAULTS:
        if k in j:
            try: v = float(j[k]); assert v >= 0
            except Exception: return jsonify(error=f"Invalid value for {k}."), 400
            if k == "auto_interval_s": v = max(10, v)
            run("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
    return jsonify(settings())

def seed():
    with lock:
        c = sqlite3.connect(DB); c.executescript(SCHEMA); c.commit(); c.close()
        if rows("SELECT 1 FROM users"): return
        mk = lambda e, n, r: run("INSERT INTO users(email,pw,role,name) VALUES(?,?,?,?)", (e, generate_password_hash("demo123" if r != "admin" else "admin123"), r, n))
        mk("admin@demo.com", "Admin", "admin"); du = mk("donor@demo.com", "Demo Donor", "donor"); ru = mk("recipient@demo.com", "Demo Recipient", "recipient")
        ex = lambda h: (datetime.now() + timedelta(hours=h)).isoformat()
        for donor, kind, food, q, loc, h in [("Saravana Canteen", "Canteen", "Veg meals", 80, "T. Nagar", 3), ("Grand Caterers", "Catering", "Biryani & raita", 150, "Porur", 2), ("Campus Mess", "Canteen", "Rice & sambar", 60, "Ramapuram", 1.5)]:
            run("INSERT INTO donations(user_id,donor,kind,food,quantity,remaining,location,lat,lng,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (du, donor, kind, food, q, q, loc, *PRESETS[loc], ex(h)))
        for uid, n, k, loc, cap, dist, pr, v in [(ru, "Hope Shelter", "Shelter", "T. Nagar", 70, 8, 5, 1), (None, "Anbu Illam", "Orphanage", "Anna Nagar", 90, 12, 4, 1), (None, "Care Kitchen", "Community kitchen", "Ramapuram", 100, 6, 3, 0), (None, "Elder Home", "Old-age home", "Velachery", 50, 10, 5, 0)]:
            run("INSERT INTO recipients(user_id,name,kind,location,lat,lng,daily_capacity,max_distance_km,priority,has_vehicle) VALUES(?,?,?,?,?,?,?,?,?,?)", (uid, n, k, loc, *PRESETS[loc], cap, dist, pr, v))

def auto_loop():
    while True:
        time.sleep(max(10, settings()["auto_interval_s"]))
        try: allocate()
        except Exception as e: print("auto-allocation error:", e)

seed()
if __name__ == "__main__":
    threading.Thread(target=auto_loop, daemon=True).start()
    app.run(port=5000, debug=False)
