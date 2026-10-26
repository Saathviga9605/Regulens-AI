import { Bell, ChevronDown, LogOut, Menu, UserCircle2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { useAuth } from "../app/AuthContext";
import { useBackendHealth } from "../app/BackendHealthContext";
import { IDENTITY_STATEMENT, NAV_GROUPS } from "../app/navigation";
import { useApiQuery } from "../app/useApiQuery";
import { Wordmark } from "../components/BrandMark";
import { ConnectionIndicator } from "../components/ConnectionIndicator";
import { apiClient } from "../services/apiClient";

function AccountMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  if (!user) return null;
  async function signOut() {
    setOpen(false);
    await logout();
    navigate("/login");
  }
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-control px-2 py-1.5 text-left text-sm text-white hover:bg-brand-800">
        <UserCircle2 aria-hidden="true" className="h-5 w-5 text-brand-100" />
        <span className="hidden leading-tight sm:block">
          <span className="block font-medium">{user.display_name}</span>
          <span className="block text-xs text-brand-100">{user.username} · {user.role === "admin" ? "Administrator" : "Reviewer"}</span>
        </span>
        <span className="sr-only">Account menu for {user.username}</span>
        <ChevronDown aria-hidden="true" className="h-4 w-4 text-brand-100" />
      </button>
      {open && (
        <div role="menu" aria-label="Account" className="absolute right-0 z-[var(--z-drawer)] mt-1 w-56 rounded-panel border border-line bg-surface py-1 text-sm shadow-overlay">
          <p className="border-b border-line px-3 py-2 text-xs text-ink-subtle sm:hidden">
            {user.username} · {user.role === "admin" ? "Administrator" : "Reviewer"}
          </p>
          <Link role="menuitem" to="/help" onClick={() => setOpen(false)} className="block px-3 py-2 text-ink hover:bg-surface-muted">
            Help &amp; About
          </Link>
          <button role="menuitem" type="button" onClick={signOut} className="flex w-full items-center gap-2 px-3 py-2 text-left text-ink hover:bg-surface-muted">
            <LogOut aria-hidden="true" className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Sidebar({ onNavigate, unread }: { onNavigate: () => void; unread: number | null }) {
  const { user } = useAuth();
  const { state } = useBackendHealth();
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-control border-l-4 px-3 py-2 text-sm font-medium ${
      isActive ? "border-saffron-500 bg-brand-800 text-white" : "border-transparent text-brand-100 hover:bg-brand-800/60 hover:text-white"
    }`;
  return (
    <div className="flex h-full flex-col">
      <nav aria-label="Primary" className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => {
          const items = group.items.filter((i) => !i.adminOnly || user?.role === "admin");
          if (items.length === 0) return null;
          return (
            <div key={group.label}>
              <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-brand-100/70">{group.label}</p>
              <ul className="space-y-0.5">
                {items.map(({ path, label, icon: Icon }) => (
                  <li key={path}>
                    <NavLink to={path} end={path === "/"} className={linkClass} onClick={onNavigate}>
                      <Icon aria-hidden="true" className="h-4 w-4" />
                      <span className="flex-1">{label}</span>
                      {path === "/alerts" && unread !== null && unread > 0 && (
                        <span data-testid="unread-alerts" className="rounded-full bg-saffron-500 px-2 text-xs font-semibold text-brand-950">
                          <span className="sr-only">Unread alerts: </span>{unread}
                        </span>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>
      {/* shown only when something is wrong; a healthy connection needs no permanent label */}
      {state.kind !== "connected" && (
        <div className="border-t border-brand-800 px-5 py-3">
          <p className="mb-1 text-[11px] uppercase tracking-wider text-brand-100/70">Backend</p>
          <ConnectionIndicator state={state} />
        </div>
      )}
    </div>
  );
}

export function AppLayout() {
  const location = useLocation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Unread count refreshes on navigation (no background polling).
  const alerts = useApiQuery(() => apiClient.listAlerts({ page_size: 1 }), location.pathname);
  const unread = alerts.error ? null : alerts.data?.unread_count ?? null;
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => setDrawerOpen(false), [location.pathname]);
  useEffect(() => {
    if (!drawerOpen) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    drawerRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDrawerOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", onKey); };
  }, [drawerOpen]);

  return (
    <div className="min-h-screen bg-canvas">
      <a href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[var(--z-toast)] focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to main content
      </a>

      <header className="sticky top-0 z-[var(--z-sticky)] flex h-[var(--layout-header)] items-center gap-3 border-b-4 border-saffron-500 bg-brand-900 px-3 sm:px-4">
        <button type="button" className="rounded-control p-1.5 text-white hover:bg-brand-800 lg:hidden"
          aria-label={drawerOpen ? "Close navigation" : "Open navigation"} aria-expanded={drawerOpen} aria-controls="mobile-nav"
          onClick={() => setDrawerOpen((o) => !o)}>
          {drawerOpen ? <X aria-hidden="true" className="h-5 w-5" /> : <Menu aria-hidden="true" className="h-5 w-5" />}
        </button>
        <Link to="/" className="min-w-0 rounded-control" aria-label="ReguLens AI — overview"><Wordmark inverse /></Link>
        <div className="ml-auto flex items-center gap-1">
          <Link to="/alerts" className="relative rounded-control p-2 text-white hover:bg-brand-800"
            aria-label={unread ? `Alerts, ${unread} unread` : "Alerts"}>
            <Bell aria-hidden="true" className="h-5 w-5" />
            {unread !== null && unread > 0 && (
              <span aria-hidden="true" className="absolute right-0.5 top-0.5 min-w-4 rounded-full bg-saffron-500 px-1 text-center text-[10px] font-bold leading-4 text-brand-950">
                {unread > 99 ? "99+" : unread}
              </span>
            )}
          </Link>
          <AccountMenu />
        </div>
      </header>

      <div className="lg:flex">
        <aside aria-label="Sidebar" className="hidden bg-brand-900 lg:sticky lg:top-[var(--layout-header)] lg:block lg:h-[calc(100vh-var(--layout-header))] lg:w-[var(--layout-sidebar)] lg:shrink-0">
          <Sidebar onNavigate={() => {}} unread={unread} />
        </aside>

        {drawerOpen && (
          <div className="fixed inset-0 z-[var(--z-drawer)] lg:hidden" onMouseDown={(e) => { if (e.target === e.currentTarget) setDrawerOpen(false); }}
            style={{ backgroundColor: "rgb(11 21 51 / 0.5)" }}>
            <div id="mobile-nav" ref={drawerRef} role="dialog" aria-modal="true" aria-label="Navigation"
              className="h-full w-72 max-w-[85vw] bg-brand-900 shadow-overlay">
              <div className="flex items-center justify-between border-b border-brand-800 px-4 py-3">
                <Wordmark inverse />
                <button type="button" aria-label="Close navigation" onClick={() => setDrawerOpen(false)} className="rounded-control p-1 text-white hover:bg-brand-800">
                  <X aria-hidden="true" className="h-5 w-5" />
                </button>
              </div>
              <Sidebar onNavigate={() => setDrawerOpen(false)} unread={unread} />
            </div>
          </div>
        )}

        <main id="main-content" className="min-w-0 flex-1 px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          <div className="mx-auto max-w-[var(--layout-content-max)]">
            <Outlet />
          </div>
          <footer className="mx-auto mt-10 max-w-[var(--layout-content-max)] border-t border-line pt-3 text-xs text-ink-subtle">
            {IDENTITY_STATEMENT}
          </footer>
        </main>
      </div>
    </div>
  );
}
