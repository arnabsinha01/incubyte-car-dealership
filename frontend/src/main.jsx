import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CarFront, ArrowUpRight, Search, Plus, LogOut,
  Pencil, Trash2, PackagePlus, X, CheckCircle2
} from "lucide-react";
import "./styles.css";

const emptyVehicle = {
  make: "", model: "", category: "Sedan", price: "", quantity: ""
};
const emptyFilters = {
  make: "", model: "", category: "", min_price: "", max_price: ""
};
const money = value => new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 2
}).format(value);

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("token") || "");
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [credentials, setCredentials] = useState({ email: "", password: "" });
  const [vehicles, setVehicles] = useState([]);
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editor, setEditor] = useState(null);
  const [draft, setDraft] = useState(emptyVehicle);
  const [restock, setRestock] = useState(null);
  const [amount, setAmount] = useState("1");
  const [deleting, setDeleting] = useState(null);
  const admin = user?.role === "admin";

  function logout() {
    sessionStorage.removeItem("token");
    setToken("");
    setUser(null);
    setVehicles([]);
    setEditor(null);
    setRestock(null);
    setDeleting(null);
    setNotice("");
  }

  async function api(path, options = {}, authToken = token) {
    const response = await fetch(path, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        ...options.headers
      }
    });
    const data = response.status === 204
      ? null : await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && authToken) logout();
      const detail = data?.detail;
      throw new Error(Array.isArray(detail)
        ? detail.map(item => `${item.loc.at(-1)}: ${item.msg}`).join("; ")
        : detail || `Request failed (${response.status})`);
    }
    return data;
  }

  async function loadVehicles(selected = appliedFilters) {
    setLoading(true);
    try {
      const query = new URLSearchParams(
        Object.entries(selected).filter(([, value]) => value !== "")
      );
      const path = query.size ? `/api/vehicles/search?${query}` : "/api/vehicles";
      setVehicles(await api(path));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!token) {
      setChecking(false);
      return;
    }
    let active = true;
    api("/api/auth/me")
      .then(data => { if (active) setUser(data); })
      .catch(err => { if (active) setError(err.message); })
      .finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    if (user) loadVehicles().catch(err => setError(err.message));
  }, [user]);

  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timeout);
  }, [notice]);

  async function authenticate(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (registering) {
        await api("/api/auth/register", {
          method: "POST", body: JSON.stringify(credentials)
        }, "");
      }
      const result = await api("/api/auth/login", {
        method: "POST", body: JSON.stringify(credentials)
      }, "");
      sessionStorage.setItem("token", result.access_token);
      setToken(result.access_token);
      setCredentials({ email: "", password: "" });
      setNotice(registering ? "Account created. Welcome to Motorhouse." : "Welcome back.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function mutate(path, method, body, message) {
    setBusy(true);
    setError("");
    try {
      await api(path, {
        method,
        ...(body === undefined ? {} : { body: JSON.stringify(body) })
      });
      setEditor(null);
      setRestock(null);
      setDeleting(null);
      setNotice(message);
      await loadVehicles();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function search(event) {
    event.preventDefault();
    setError("");
    setAppliedFilters({ ...filters });
    try { await loadVehicles(filters); }
    catch (err) { setError(err.message); }
  }

  function openEditor(vehicle = null) {
    setError("");
    setEditor(vehicle ? { id: vehicle.id } : {});
    setDraft(vehicle ? {
      make: vehicle.make, model: vehicle.model, category: vehicle.category,
      price: String(vehicle.price), quantity: String(vehicle.quantity)
    } : { ...emptyVehicle });
  }

  function saveVehicle(event) {
    event.preventDefault();
    const editing = editor.id !== undefined;
    mutate(
      editing ? `/api/vehicles/${editor.id}` : "/api/vehicles",
      editing ? "PUT" : "POST",
      { ...draft, price: Number(draft.price), quantity: Number(draft.quantity) },
      editing ? "Vehicle updated." : "Vehicle added to inventory."
    );
  }

  const feedback = <>
    {error && <div className="alert error" role="alert">{error}</div>}
    {notice && <div className="alert success" role="status">
      <CheckCircle2 size={18} />{notice}
    </div>}
  </>;

  if (checking) return <main className="loading-screen">Opening Motorhouse...</main>;

  if (!user) return <main className="auth-layout">
    <section className="auth-story">
      <a className="brand" href="/"><CarFront /> MOTORHOUSE<span /></a>
      <div>
        <span className="eyebrow">A BETTER WAY TO FIND YOUR NEXT DRIVE</span>
        <h1>Great cars.<br />Clear choices.</h1>
        <p>Explore the collection, find your fit, and make your next move.</p>
        <div className="auth-car"><CarFront strokeWidth={0.8} /></div>
      </div>
      <small>CURATED INVENTORY / LIVE AVAILABILITY</small>
    </section>
    <section className="auth-form">
      <div className="auth-inner">
        <span className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</span>
        <h2>{registering ? "Join Motorhouse." : "Welcome back."}</h2>
        <p className="muted">{registering
          ? "Create an account to explore and purchase vehicles."
          : "Sign in to explore the collection or manage inventory."}</p>
        {feedback}
        <form onSubmit={authenticate}>
          <label>Email address<input type="email" required maxLength={254}
            autoComplete="username" value={credentials.email}
            onChange={e => setCredentials({ ...credentials, email: e.target.value })}
            placeholder="you@example.com" /></label>
          <label>Password<input type="password" required minLength={8} maxLength={128}
            autoComplete={registering ? "new-password" : "current-password"}
            value={credentials.password}
            onChange={e => setCredentials({ ...credentials, password: e.target.value })}
            placeholder="At least 8 characters" /></label>
          <button className="primary wide" disabled={busy}>
            {busy ? "Please wait..." : registering ? "Create account" : "Sign in"}
            <ArrowUpRight size={18} />
          </button>
        </form>
        <button className="text-button" disabled={busy} onClick={() => {
          setRegistering(!registering); setError("");
        }}>{registering ? "Already have an account? Sign in" : "New here? Create an account"}</button>
        <p className="fine-print">Assessment demo. Purchases adjust inventory; no payment is collected.</p>
      </div>
    </section>
  </main>;

  return <div className="app">
    <header className="topbar">
      <a className="brand" href="/"><CarFront /> MOTORHOUSE<span /></a>
      <div className="account"><span className="role">{admin ? "ADMIN" : "MEMBER"}</span>
        <span className="email">{user.email}</span>
        <button className="icon-button" onClick={logout} aria-label="Sign out"><LogOut size={19} /></button>
      </div>
    </header>
    <main className="container">
      <section className="hero">
        <div><span className="eyebrow">THE MOTORHOUSE COLLECTION</span>
          <h1>Find your next<br /><em>great drive.</em></h1>
          <p>Thoughtfully selected. Ready for the road.</p>
        </div>
        <div className="hero-side">
          <CarFront size={100} strokeWidth={1} />
          <span>EXCEPTIONAL CARS.<br />EVERYDAY POSSIBILITIES.</span>
        </div>
      </section>
      <section className="stats" aria-label="Inventory summary">
        <div><strong>{vehicles.length}</strong><span>Vehicles in view</span></div>
        <div><strong>{vehicles.reduce((sum, v) => sum + v.quantity, 0)}</strong><span>Units in view</span></div>
        <div><strong>{new Set(vehicles.map(v => v.make)).size}</strong><span>Brands in view</span></div>
        <div><strong>{admin ? "Admin" : "Member"}</strong><span>Your workspace</span></div>
      </section>
      <div className="section-heading">
        <div><span className="eyebrow">BROWSE & DISCOVER</span><h2>Our inventory</h2></div>
        {admin && <button className="primary" disabled={busy} onClick={() => openEditor()}>
          <Plus size={18} /> Add vehicle</button>}
      </div>
      <form className="filters" onSubmit={search}>
        <label>Make<input placeholder="Any make" value={filters.make}
          onChange={e => setFilters({ ...filters, make: e.target.value })} /></label>
        <label>Model<input placeholder="Any model" value={filters.model}
          onChange={e => setFilters({ ...filters, model: e.target.value })} /></label>
        <label>Category<input placeholder="Any category" value={filters.category}
          onChange={e => setFilters({ ...filters, category: e.target.value })} /></label>
        <label>Min price ($)<input type="number" min="0" step="0.01" placeholder="0"
          value={filters.min_price} onChange={e => setFilters({ ...filters, min_price: e.target.value })} /></label>
        <label>Max price ($)<input type="number" min="0" step="0.01" placeholder="Any"
          value={filters.max_price} onChange={e => setFilters({ ...filters, max_price: e.target.value })} /></label>
        <button className="primary" disabled={loading || busy}><Search size={18} /> Search</button>
        <button type="button" className="text-button" disabled={loading || busy} onClick={() => {
          setFilters({ ...emptyFilters }); setAppliedFilters({ ...emptyFilters });
          setError(""); loadVehicles(emptyFilters).catch(err => setError(err.message));
        }}>Reset</button>
      </form>
      {feedback}
      {loading ? <div className="empty">Loading inventory...</div> :
        vehicles.length === 0 ? <div className="empty"><CarFront size={40} />
          <h3>No vehicles found</h3><p>Try different filters{admin ? " or add your first vehicle." : "."}</p>
        </div> :
        <section className="vehicle-grid" aria-label="Vehicles">
          {vehicles.map(vehicle => <article className="vehicle-card" key={vehicle.id}>
            <div className={`vehicle-art art-${vehicle.id % 4}`}>
              <span className="category">{vehicle.category}</span>
              <span className={`stock ${vehicle.quantity === 0 ? "sold" : ""}`}>
                {vehicle.quantity > 0 ? `${vehicle.quantity} in stock` : "Out of stock"}
              </span>
              <CarFront size={115} strokeWidth={1} aria-hidden="true" />
              <span className="art-label">{vehicle.make}</span>
            </div>
            <div className="vehicle-body">
              <span className="eyebrow">{vehicle.make}</span>
              <h3>{vehicle.model}</h3>
              <div className="price-row"><strong>{money(vehicle.price)}</strong><span>USD / vehicle</span></div>
              <button className="purchase wide" disabled={busy || vehicle.quantity === 0}
                onClick={() => mutate(`/api/vehicles/${vehicle.id}/purchase`, "POST", undefined,
                  `${vehicle.make} ${vehicle.model} purchased. Stock updated.`)}>
                {vehicle.quantity === 0 ? "Currently unavailable" : "Purchase vehicle"}
                <ArrowUpRight size={18} />
              </button>
              {admin && <div className="admin-actions">
                <button disabled={busy} onClick={() => openEditor(vehicle)}><Pencil size={15} /> Edit</button>
                <button disabled={busy} onClick={() => { setRestock(vehicle); setAmount("1"); setError(""); }}>
                  <PackagePlus size={15} /> Restock</button>
                <button className="danger" disabled={busy} onClick={() => { setDeleting(vehicle); setError(""); }}>
                  <Trash2 size={15} /> Delete</button>
              </div>}
            </div>
          </article>)}
        </section>}
      <footer><span>MOTORHOUSE / INVENTORY SYSTEM</span><span>Demo purchases. No payment processing.</span></footer>
    </main>

    {(editor !== null || restock || deleting) && <div className="modal-backdrop">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <div className="modal-heading">
          <h2 id="dialog-title">{editor !== null ? editor.id ? "Edit vehicle" : "Add vehicle"
            : restock ? "Restock vehicle" : "Delete vehicle?"}</h2>
          <button className="icon-button" aria-label="Close dialog" disabled={busy} onClick={() => {
            setEditor(null); setRestock(null); setDeleting(null); setError("");
          }}><X /></button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        {editor !== null ? <form onSubmit={saveVehicle}>
          <div className="form-grid">
            {["make", "model", "category", "price", "quantity"].map(field =>
              <label key={field}>{field === "price" ? "Price (USD)" : field}
                <input required autoFocus={field === "make"}
                  type={["price", "quantity"].includes(field) ? "number" : "text"}
                  min={["price", "quantity"].includes(field) ? "0" : undefined}
                  step={field === "price" ? "0.01" : field === "quantity" ? "1" : undefined}
                  maxLength={100} value={draft[field]}
                  onChange={e => setDraft({ ...draft, [field]: e.target.value })} />
              </label>)}
          </div>
          <button className="primary wide" disabled={busy}>{busy ? "Saving..." : "Save vehicle"}</button>
        </form> : restock ? <form onSubmit={e => {
          e.preventDefault();
          mutate(`/api/vehicles/${restock.id}/restock`, "POST",
            { quantity: Number(amount) }, "Inventory restocked.");
        }}>
          <p>{restock.make} {restock.model} currently has {restock.quantity} units.</p>
          <label>Units to add<input autoFocus required type="number" min="1" step="1"
            value={amount} onChange={e => setAmount(e.target.value)} /></label>
          <button className="primary wide" disabled={busy}>{busy ? "Updating..." : "Add stock"}</button>
        </form> : <>
          <p>Remove {deleting.make} {deleting.model} from inventory? This cannot be undone.</p>
          <button className="delete-button wide" disabled={busy} onClick={() =>
            mutate(`/api/vehicles/${deleting.id}`, "DELETE", undefined, "Vehicle deleted.")
          }>{busy ? "Deleting..." : "Delete vehicle"}</button>
        </>}
      </section>
    </div>}
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
