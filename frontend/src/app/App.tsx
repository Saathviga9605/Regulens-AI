import { Route, Routes } from "react-router";

import { AppLayout } from "../layouts/AppLayout";
import { ApplicationCreatePage } from "../pages/applications/ApplicationCreatePage";
import { ApplicationDetailPage } from "../pages/applications/ApplicationDetailPage";
import { ApplicationsListPage } from "../pages/applications/ApplicationsListPage";
import { DashboardPage } from "../pages/DashboardPage";
import { InstitutionCreatePage } from "../pages/institutions/InstitutionCreatePage";
import { InstitutionDetailPage } from "../pages/institutions/InstitutionDetailPage";
import { InstitutionsListPage } from "../pages/institutions/InstitutionsListPage";
import { ModulePlaceholderPage } from "../pages/ModulePlaceholderPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ScrutinyRulesPage } from "../pages/ScrutinyRulesPage";
import { BackendHealthProvider } from "./BackendHealthContext";
import { MODULES } from "./navigation";

/** Routes only; the router itself is supplied by main.tsx (or tests). */
export function App() {
  return (
    <BackendHealthProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="applications" element={<ApplicationsListPage />} />
          <Route path="applications/new" element={<ApplicationCreatePage />} />
          <Route path="applications/:applicationCode" element={<ApplicationDetailPage />} />
          <Route path="institutions" element={<InstitutionsListPage />} />
          <Route path="institutions/new" element={<InstitutionCreatePage />} />
          <Route path="institutions/:institutionCode" element={<InstitutionDetailPage />} />
          <Route path="scrutiny-rules" element={<ScrutinyRulesPage />} />
          {MODULES.filter((m) => !m.available).map((m) => (
            <Route key={m.path} path={m.path} element={<ModulePlaceholderPage module={m} />} />
          ))}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BackendHealthProvider>
  );
}
