import { Route, Routes } from "react-router";

import { ToastProvider } from "../components/Toast";
import { AppLayout } from "../layouts/AppLayout";
import { AlertsPage } from "../pages/AlertsPage";
import { ApplicationCreatePage } from "../pages/applications/ApplicationCreatePage";
import { ApplicationDetailPage } from "../pages/applications/ApplicationDetailPage";
import { ApplicationsListPage } from "../pages/applications/ApplicationsListPage";
import { AuditTrailPage } from "../pages/AuditTrailPage";
import { DashboardPage } from "../pages/DashboardPage";
import { CasePairPage } from "../pages/CasePairPage";
import { CrossCasePage } from "../pages/CrossCasePage";
import { HelpPage } from "../pages/HelpPage";
import { InstitutionCreatePage } from "../pages/institutions/InstitutionCreatePage";
import { InstitutionDetailPage } from "../pages/institutions/InstitutionDetailPage";
import { InstitutionsListPage } from "../pages/institutions/InstitutionsListPage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ReviewQueuePage } from "../pages/ReviewQueuePage";
import { ScrutinyRulesPage } from "../pages/ScrutinyRulesPage";
import { UsersPage } from "../pages/UsersPage";
import { AuthProvider } from "./AuthContext";
import { BackendHealthProvider } from "./BackendHealthContext";
import { RequireAdmin, RequireAuth } from "./guards";

/** Routes only; the router itself is supplied by main.tsx (or tests). Route list: docs/design-system.md. */
export function App() {
  return (
    <BackendHealthProvider>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="login" element={<LoginPage />} />
            <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
              <Route index element={<DashboardPage />} />
              <Route path="review-queue" element={<ReviewQueuePage />} />
              <Route path="applications" element={<ApplicationsListPage />} />
              <Route path="applications/new" element={<ApplicationCreatePage />} />
              <Route path="applications/:applicationCode" element={<ApplicationDetailPage />} />
              <Route path="institutions" element={<InstitutionsListPage />} />
              <Route path="institutions/new" element={<InstitutionCreatePage />} />
              <Route path="institutions/:institutionCode" element={<InstitutionDetailPage />} />
              <Route path="alerts" element={<AlertsPage />} />
              <Route path="cross-case" element={<CrossCasePage />} />
              <Route path="case-pairs/:pairId" element={<CasePairPage />} />
              <Route path="scrutiny-rules" element={<ScrutinyRulesPage />} />
              <Route path="audit-trail" element={<RequireAdmin><AuditTrailPage /></RequireAdmin>} />
              <Route path="users" element={<RequireAdmin><UsersPage /></RequireAdmin>} />
              <Route path="help" element={<HelpPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BackendHealthProvider>
  );
}
