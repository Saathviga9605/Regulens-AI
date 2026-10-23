import { Route, Routes } from "react-router";

import { AppLayout } from "../layouts/AppLayout";
import { DashboardPage } from "../pages/DashboardPage";
import { ModulePlaceholderPage } from "../pages/ModulePlaceholderPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { BackendHealthProvider } from "./BackendHealthContext";
import { MODULES } from "./navigation";

/** Routes only; the router itself is supplied by main.tsx (or tests). */
export function App() {
  return (
    <BackendHealthProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          {MODULES.map((m) => (
            <Route key={m.path} path={m.path} element={<ModulePlaceholderPage module={m} />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BackendHealthProvider>
  );
}
