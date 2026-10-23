import { useNavigate } from "react-router";

import { InstitutionForm } from "../../components/InstitutionForm";
import { Card, PageHeader } from "../../components/ui";
import { apiClient } from "../../services/apiClient";
import type { InstitutionInput } from "../../types/api";

export function InstitutionCreatePage() {
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader eyebrow="Scrutiny work" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Institutions", to: "/institutions" }, { label: "New" }]} title="New institution" description="The institution code is assigned by the system." />
      <Card>
        <InstitutionForm
          submitLabel="Create institution"
          onCancel={() => navigate("/institutions")}
          onSubmit={async (input) => {
            const created = await apiClient.createInstitution(input as InstitutionInput);
            navigate(`/institutions/${created.institution_code}`, {
              state: { flash: `Institution ${created.institution_code} created.` },
            });
          }}
        />
      </Card>
    </div>
  );
}
