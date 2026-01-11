import { useMemo } from "react";

const NAV_ITEMS = [
  { id: "live", label: "Live Detection" },
  { id: "analysis", label: "Analysis" },
  { id: "anomalies", label: "Anomalies" },
];

function AppShell({ children, activePage, onNavigate }) {
  const navButtons = useMemo(
    () =>
      NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`nav-button ${activePage === item.id ? "active" : ""}`}
          onClick={() => onNavigate(item.id)}
        >
          {item.label}
        </button>
      )),
    [activePage, onNavigate]
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <img
            src="/Deftech_logo.png"
            alt="Deftech logo"
            className="brand-logo"
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
          <div>
            <p className="brand-title">Quantum Threat Detection</p>
            <p className="brand-subtitle">
              DRB Deftech Unmanned System Sdn Bhd
            </p>
          </div>
        </div>
        <div className="header-actions">
          <span className="status-pill">Demo Mode</span>
        </div>
      </header>

      <div className="app-body">
        <aside className="app-sidebar">
          <p className="sidebar-label">Navigation</p>
          <nav className="sidebar-nav">{navButtons}</nav>
          <div className="sidebar-card">
            <p className="sidebar-card-title">Theme Accent</p>
            <p className="sidebar-card-body">
              Update <code>--brand-accent</code> in{" "}
              <code>src/styles/App.css</code> with the official color.
            </p>
          </div>
        </aside>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

export default AppShell;
