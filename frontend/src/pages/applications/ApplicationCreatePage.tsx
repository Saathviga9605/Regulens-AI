import { Link, useNavigate, useSearchParams } from "react-router";

import { useApiQuery } from "../../app/useApiQuery";
import { ApplicationForm, toFormValues } from "../../components/ApplicationForm";
import { Alert, Card, ErrorState, LoadingState, PageHeader, buttonStyles } from "../../components/ui";
import { apiClient } from "../../services/apiClient";

export function ApplicationCreatePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const institutions = useApiQuery(() => apiClient.listInstitutions({ status: "active", page_size: 100 }), "active");

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scrutiny work"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Applications", to: "/applications" }, { label: "New" }]}
        title="New EoA application"
        description="Creates a draft in ReguLens. The application ID is assigned by the system. Nothing is sent to AICTE."
      />
      <Card>
        {institutions.loading ? (
          <LoadingState label="Loading institutions…" />
        ) : institutions.error ? (
          <ErrorState message={institutions.error} onRetry={institutions.reload} />
        ) : institutions.data && institutions.data.items.length === 0 ? (
          <Alert tone="info">
            No active institutions exist yet.{" "}
            <Link to="/institutions/new" className={buttonStyles.link}>
              Create an institution
            </Link>{" "}
            first.
          </Alert>
        ) : (
          <ApplicationForm
            institutions={institutions.data?.items ?? []}
            initial={toFormValues({ institution_code: params.get("institution") ?? "" })}
            submitLabel="Create draft application"
            onCancel={() => navigate("/applications")}
            onSubmit={async (input) => {
              const created = await apiClient.createApplication(input);
              navigate(`/applications/${created.application_code}`, {
                state: { flash: `Draft application ${created.application_code} created.` },
              });
            }}
          />
        )}
        {institutions.data && institutions.data.total > institutions.data.items.length && (
          <p className="mt-3 text-xs text-ink-subtle">
            Showing the first {institutions.data.items.length} active institutions alphabetically.
          </p>
        )}
      </Card>
    </div>
  );
}
