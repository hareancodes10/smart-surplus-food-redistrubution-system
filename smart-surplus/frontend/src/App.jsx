import { useEffect, useState, useCallback } from "react";

const api = async (p, o = {}) => {
  const t = localStorage.getItem("t");
  const r = await fetch("/api" + p, { headers: { "Content-Type": "application/json", ...(t ? { Authorization: "Bearer " + t } : {}) }, ...o, body: o.body && JSON.stringify(o.body) });
  const j = await r.json();
  if (r.status === 401 && t) { localStorage.removeItem("t"); location.reload(); }
  if (!r.ok) throw new Error(j.error || "Request failed");
  return j;
};
const left = (iso) => { const m = Math.round((new Date(iso) - Date.now()) / 60000); return m <= 0 ? "expired" : m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m left` : `${m}m left`; };
const Field = ({ label, children }) => <label className="field"><span>{label}</span>{children}</label>;
const LocInput = ({ value, onChange, locs }) => (<>
  <input list="locs" value={value} onChange={onChange} placeholder="Pick an area or type an address" required /><datalist id="locs">{locs.map(l => <option key={l} value={l} />)}</datalist></>);

function Auth({ onLogin }) {
  const [reg, setReg] = useState(false), [f, setF] = useState({ email: "", password: "", name: "", role: "donor" }), [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const go = async (e) => { e.preventDefault(); try { const r = await api(reg ? "/register" : "/login", { method: "POST", body: f }); localStorage.setItem("t", r.token); onLogin(r.user); } catch (x) { setErr(x.message); } };
  return (<div className="authwrap"><form className="panel auth" onSubmit={go}>
    <div className="brand dark"><span className="leaf" />Smart Surplus</div><h2>{reg ? "Create your account" : "Log in"}</h2>
    {reg && <Field label="Name or organisation"><input value={f.name} onChange={set("name")} required /></Field>}
    <Field label="Email"><input type="email" value={f.email} onChange={set("email")} required /></Field>
    <Field label="Password"><input type="password" value={f.password} onChange={set("password")} required /></Field>
    {reg && <Field label="I am a"><select value={f.role} onChange={set("role")}><option value="donor">Food donor</option><option value="recipient">Recipient organisation</option></select></Field>}
    {err && <p className="err">{err}</p>}<button className="btn">{reg ? "Create account" : "Log in"}</button>
    <p className="muted"><button type="button" className="link" onClick={() => { setReg(!reg); setErr(""); }}>{reg ? "I already have an account" : "Create an account"}</button></p>
    {!reg && <p className="muted small">Demo: admin@demo.com / admin123 · donor@demo.com / demo123 · recipient@demo.com / demo123</p>}</form></div>);
}

function Dashboard({ s }) {
  const cards = [["Servings listed", s.total], ["Allocated", s.allocated], ["Collected", s.collected], ["Lost to expiry", s.wasted]];
  return (<>
    <section className="hero"><div><h1>Good food should reach a plate, not a bin.</h1>
      <p>Surplus is matched automatically by urgency, road distance, need and collection capacity, before it spoils.</p></div>
      <div className="ring" style={{ "--p": s.rate || 0 }}><b>{s.rate || 0}%</b><small>of surplus allocated</small></div></section>
    <div className="stats">{cards.map(([k, v]) => <div className="stat" key={k}><b>{v ?? 0}</b><span>{k}</span></div>)}</div>
    <p className="muted">{s.open_donations ?? 0} open donations waiting · {s.recipients ?? 0} registered recipients</p></>);
}

function Donations({ list, locs, reload, user }) {
  const [f, setF] = useState({ donor: user.name, kind: "Restaurant", food: "", quantity: 20, location: "", hours: 2 }), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => { e.preventDefault(); setBusy(true); try { await api("/donations", { method: "POST", body: f }); setErr(""); setF({ ...f, food: "" }); reload(); } catch (x) { setErr(x.message); } setBusy(false); };
  return (<div className="split">
    <form className="panel" onSubmit={submit}><h2>List surplus food</h2>
      <Field label="Donor name"><input value={f.donor} onChange={set("donor")} required /></Field>
      <Field label="Donor type"><select value={f.kind} onChange={set("kind")}>{["Restaurant", "Canteen", "Catering"].map(x => <option key={x}>{x}</option>)}</select></Field>
      <Field label="Food description"><input value={f.food} onChange={set("food")} required /></Field>
      <div className="row"><Field label="Servings"><input type="number" min="1" value={f.quantity} onChange={set("quantity")} /></Field>
        <Field label="Safe for (hours)"><input type="number" step="0.5" min="0.5" value={f.hours} onChange={set("hours")} /></Field></div>
      <Field label="Pickup location"><LocInput value={f.location} onChange={set("location")} locs={locs} /></Field>
      {err && <p className="err">{err}</p>}<button className="btn" disabled={busy}>{busy ? "Locating…" : "Add donation"}</button></form>
    <div className="panel"><h2>Donations</h2>{!list.length ? <p className="muted">No donations yet. Add your first surplus listing.</p> :
      <table><thead><tr><th>Donor</th><th>Food</th><th>Left</th><th>Location</th><th>Time</th><th>Status</th></tr></thead>
        <tbody>{list.map(d => <tr key={d.id}><td>{d.donor}</td><td>{d.food}</td><td>{d.remaining}/{d.quantity}</td><td>{d.location}</td><td>{left(d.expires_at)}</td><td><span className={"tag " + d.status}>{d.status}</span></td></tr>)}</tbody></table>}</div></div>);
}

function Recipients({ list, locs, reload, user }) {
  const [f, setF] = useState({ name: user.name, kind: "Shelter", location: "", capacity: 50, max_distance_km: 8, priority: 3, has_vehicle: false }), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const submit = async (e) => { e.preventDefault(); setBusy(true); try { await api("/recipients", { method: "POST", body: f }); setErr(""); reload(); } catch (x) { setErr(x.message); } setBusy(false); };
  const hasForm = user.role === "admin" || !list.length;
  return (<div className={hasForm ? "split" : ""}>
    {hasForm && <form className="panel" onSubmit={submit}><h2>Register a recipient</h2>
      <Field label="Organisation name"><input value={f.name} onChange={set("name")} required /></Field>
      <Field label="Type"><select value={f.kind} onChange={set("kind")}>{["Shelter", "Orphanage", "Old-age home", "Community kitchen", "NGO"].map(x => <option key={x}>{x}</option>)}</select></Field>
      <Field label="Location"><LocInput value={f.location} onChange={set("location")} locs={locs} /></Field>
      <div className="row"><Field label="Daily capacity (servings)"><input type="number" min="1" value={f.capacity} onChange={set("capacity")} /></Field>
        <Field label="Max pickup distance (km)"><input type="number" min="1" value={f.max_distance_km} onChange={set("max_distance_km")} /></Field></div>
      <Field label={`Need level: ${f.priority} (1 low – 5 critical)`}><input type="range" min="1" max="5" value={f.priority} onChange={set("priority")} /></Field>
      <label className="check"><input type="checkbox" checked={f.has_vehicle} onChange={set("has_vehicle")} /> Has a vehicle for pickup</label>
      {err && <p className="err">{err}</p>}<button className="btn" disabled={busy}>{busy ? "Locating…" : "Add recipient"}</button></form>}
    <div className="panel"><h2>{user.role === "admin" ? "Recipients" : "Your profile"}</h2>
      <table><thead><tr><th>Name</th><th>Location</th><th>Capacity left today</th><th>Radius</th><th>Need</th><th>Vehicle</th></tr></thead>
        <tbody>{list.map(r => <tr key={r.id}><td>{r.name}<br /><small>{r.kind}</small></td><td>{r.location}</td><td>{r.capacity_left}/{r.daily_capacity}</td><td>{r.max_distance_km} km</td><td>{r.priority}/5</td><td>{r.has_vehicle ? "Yes" : "No"}</td></tr>)}</tbody></table></div></div>);
}

function Matches({ matches, reload, user }) {
  const [busy, setBusy] = useState(false), [note, setNote] = useState("");
  const run = async () => { setBusy(true); const r = await api("/allocate", { method: "POST" }); setNote(r.made ? `${r.made} new match(es) created.` : "No new matches: nothing eligible within time, distance and capacity limits."); setBusy(false); reload(); };
  const collect = async (id) => { await api("/matches/" + id, { method: "PATCH" }); reload(); };
  const canCollect = user.role !== "donor";
  return (<div className="panel"><div className="bar"><h2>{user.role === "recipient" ? "Your pickups" : "Allocation"}</h2>
    {user.role === "admin" && <button className="btn" onClick={run} disabled={busy}>{busy ? "Matching…" : "Run allocation now"}</button>}</div>
    <p className="muted small">Allocation also runs automatically when a donation or recipient is added, and on a timer.</p>{note && <p className="muted">{note}</p>}
    {!matches.length ? <p className="muted">No matches yet.</p> :
      <table><thead><tr><th>Food</th><th>From</th><th>To</th><th>Servings</th><th>Distance</th><th>ETA</th><th>Score</th><th></th></tr></thead>
        <tbody>{matches.map(m => <tr key={m.id}><td>{m.food}</td><td>{m.donor}</td><td>{m.recipient}</td><td>{m.quantity}</td>
          <td>{m.distance_km} km{m.route_source === "estimate" ? " (est.)" : ""}</td><td>{m.eta_min} min</td><td>{m.score}</td>
          <td>{m.status === "collected" ? <span className="tag allocated">collected</span> : canCollect ? <button className="btn small" onClick={() => collect(m.id)}>Mark collected</button> : <span className="tag pending">assigned</span>}</td></tr>)}</tbody></table>}</div>);
}

const FIELDS = [["w_prox", "Weight: proximity", 0.1], ["w_need", "Weight: need level", 0.1], ["w_cap", "Weight: capacity fit", 0.1], ["speed_vehicle", "Speed with vehicle (km/h)", 1], ["speed_walk", "Speed on foot (km/h)", 1], ["handling_min", "Handling time (min)", 1], ["auto_interval_s", "Auto-allocation interval (sec, min 10)", 10]];
function Settings() {
  const [s, setS] = useState(null), [msg, setMsg] = useState("");
  useEffect(() => { api("/settings").then(setS); }, []);
  const save = async (e) => { e.preventDefault(); try { setS(await api("/settings", { method: "PUT", body: s })); setMsg("Saved. New values apply to the next allocation run."); } catch (x) { setMsg(x.message); } };
  if (!s) return null;
  return (<form className="panel narrow" onSubmit={save}><h2>Allocation settings</h2>
    {FIELDS.map(([k, l, st]) => <Field key={k} label={l}><input type="number" step={st} min="0" value={s[k]} onChange={e => setS({ ...s, [k]: e.target.value })} /></Field>)}
    <label className="check"><input type="checkbox" checked={!!Number(s.use_road)} onChange={e => setS({ ...s, use_road: e.target.checked ? 1 : 0 })} /> Use road distance (OSRM); otherwise straight-line × 1.3</label>
    <p className="muted small">Weights are normalised, so only their ratio matters.</p>{msg && <p className="muted">{msg}</p>}<button className="btn">Save settings</button></form>);
}

export default function App() {
  const [user, setUser] = useState(null), [ready, setReady] = useState(false), [tab, setTab] = useState("Dashboard");
  const [d, setD] = useState({ stats: {}, donations: [], recipients: [], matches: [], locs: [] });
  useEffect(() => { if (localStorage.getItem("t")) api("/me").then(setUser).catch(() => {}).finally(() => setReady(true)); else setReady(true); }, []);
  const reload = useCallback(async () => {
    if (!user) return; const r = user.role, none = Promise.resolve([]);
    const [stats, donations, recipients, matches, locs] = await Promise.all([api("/stats"), r !== "recipient" ? api("/donations") : none, r !== "donor" ? api("/recipients") : none, api("/matches"), api("/locations")]);
    setD({ stats, donations, recipients, matches, locs });
  }, [user]);
  useEffect(() => { reload(); const t = setInterval(reload, 20000); return () => clearInterval(t); }, [reload]);
  if (!ready) return <p className="muted pad">Loading…</p>;
  if (!user) return <Auth onLogin={setUser} />;
  const tabs = { admin: ["Dashboard", "Donations", "Recipients", "Allocation", "Settings"], donor: ["Dashboard", "Donations", "Allocation"], recipient: ["Dashboard", "Recipients", "Allocation"] }[user.role];
  const label = (t) => user.role === "recipient" ? ({ Recipients: "My profile", Allocation: "My pickups" }[t] || t) : user.role === "donor" ? ({ Donations: "My donations", Allocation: "My matches" }[t] || t) : t;
  return (<>
    <header><div className="brand"><span className="leaf" />Smart Surplus</div>
      <nav>{tabs.map(t => <button key={t} className={t === tab ? "on" : ""} onClick={() => setTab(t)}>{label(t)}</button>)}
        <button onClick={() => { localStorage.removeItem("t"); setUser(null); }}>Log out ({user.role})</button></nav></header>
    <main>
      {tab === "Dashboard" && <Dashboard s={d.stats} />}
      {tab === "Donations" && <Donations list={d.donations} locs={d.locs} reload={reload} user={user} />}
      {tab === "Recipients" && <Recipients list={d.recipients} locs={d.locs} reload={reload} user={user} />}
      {tab === "Allocation" && <Matches matches={d.matches} reload={reload} user={user} />}
      {tab === "Settings" && <Settings />}
    </main></>);
}
