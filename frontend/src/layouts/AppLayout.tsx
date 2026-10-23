import { Menu, ScanSearch, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router";

import { useBackendHealth } from "../app/BackendHealthContext";
import { DASHBOARD_NAV, MODULES } from "../app/navigation";
import { ConnectionIndicator } from "../components/ConnectionIndicator";

const NAV_ITEMS = [DASHBOARD_NAV, ...MODULES];

export function AppLayout() {
  const { state } = useBackendHealth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400 ${
      isActive ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
    }`;

  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to main content
      </a>

      <header className="flex items-center justify-between bg-slate-900 px-4 py-3 md:hidden">
        <span className="flex items-center gap-2 font-semibold text-white">
          <ScanSearch aria-hidden="true" className="h-5 w-5 text-blue-400" /> ReguLens AI
        </span>
        <button
          type="button"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
          aria-controls="primary-nav"
          onClick={() => setMobileOpen((o) => !o)}
          className="rounded p-1 text-slate-200 focus-visible:outline-2 focus-visible:outline-blue-400"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </header>

      <aside
        id="primary-nav"
        className={`${mobileOpen ? "flex" : "hidden"} w-full flex-col bg-slate-900 md:sticky md:top-0 md:flex md:h-screen md:w-64 md:shrink-0`}
      >
        <div className="hidden items-center gap-2 px-5 py-5 md:flex">
          <ScanSearch aria-hidden="true" className="h-6 w-6 text-blue-400" />
          <div>
            <p className="font-semibold leading-tight text-white">ReguLens AI</p>
            <p className="text-xs text-slate-400">Regulatory scrutiny assistant</p>
          </div>
        </div>
        <nav aria-label="Primary" className="flex-1 px-3 py-2">
          <ul className="space-y-1">
            {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
              <li key={path}>
                <NavLink to={path} end={path === "/"} className={linkClass} onClick={() => setMobileOpen(false)}>
                  <Icon aria-hidden="true" className="h-4 w-4" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="border-t border-slate-800 px-5 py-4">
          <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Backend</p>
          <ConnectionIndicator state={state} />
        </div>
      </aside>

      <main id="main-content" className="flex-1 px-4 py-6 md:px-8 md:py-8">
        <Outlet />
      </main>
    </div>
  );
}
