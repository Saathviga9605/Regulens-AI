import { Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import { APPLICATION_TYPE_LABELS, INSTITUTION_TYPE_LABELS, RECORD_STATUS_LABELS, formatDateTime } from "../../app/labels";
import { useApiQuery } from "../../app/useApiQuery";
import { InstitutionForm } from "../../components/InstitutionForm";
import {
  Alert,
  Card,
  DefinitionGrid,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  TABLE,
  buttonStyles,
} from "../../components/ui";
import { apiClient } from "../../services/apiClient";

export function InstitutionDetailPage() {
  const { institutionCode = "" } = useParams();
  const location = useLocation();
  const [flash, setFlash] = useState<string | null>((location.state as { flash?: string } | null)?.flash ?? null);
  const [editing, setEditing] = useState(false);
  const inst = useApiQuery(() => apiClient.getInstitution(institutionCode), institutionCode);
  const apps = useApiQuery(
    () => apiClient.listApplications({ institution_code: institutionCode, page_size: 100 }),
    institutionCode,
  );

  if (inst.loading && !inst.data) return <LoadingState label="Loading institution…" />;
  if (inst.error && !inst.data) return <ErrorState message={inst.error} onRetry={inst.reload} />;
  if (!inst.data) return null;
  const i = inst.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Institution record"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Institutions", to: "/institutions" }, { label: i.institution_code }]}
        title={i.name}
        description={`${i.institution_code} · ${RECORD_STATUS_LABELS[i.status]}`}
        actions={
          !editing && (
            <>
              <button type="button" className={buttonStyles.secondary} onClick={() => { setFlash(null); setEditing(true); }}>
                <Pencil aria-hidden="true" className="h-4 w-4" /> Edit
              </button>
              {i.status === "active" && (
                <Link to={`/applications/new?institution=${encodeURIComponent(i.institution_code)}`} className={buttonStyles.primary}>
                  <Plus aria-hidden="true" className="h-4 w-4" /> New application
                </Link>
              )}
            </>
          )
        }
      />
      {flash && <Alert tone="success">{flash}</Alert>}

      {editing ? (
        <Card title="Edit institution">
          <p className="mb-4 text-xs text-ink-subtle">
            Edits apply to this institution record. Applications already marked ready keep the institution details
            captured at that time.
          </p>
          <InstitutionForm
            institution={i}
            submitLabel="Save changes"
            onCancel={() => setEditing(false)}
            onSubmit={async (input) => {
              inst.setData(await apiClient.updateInstitution(i.institution_code, input));
              setEditing(false);
              setFlash("Institution saved.");
            }}
          />
        </Card>
      ) : (
        <Card title="Institution details">
          <DefinitionGrid
            items={[
              ["Institution code", <span className="font-mono">{i.institution_code}</span>],
              ["Type", INSTITUTION_TYPE_LABELS[i.institution_type]],
              ["State", i.state],
              ["District", i.district],
              ["Address", i.address],
              ["Trust or sponsoring body", i.trust_name],
              ["Property / survey identifier", i.property_identifier],
              ["Record status", RECORD_STATUS_LABELS[i.status]],
              ["Created", formatDateTime(i.created_at)],
              ["Last updated", formatDateTime(i.updated_at)],
            ]}
          />
        </Card>
      )}

      <Card title="Applications">
        {apps.loading && !apps.data ? (
          <LoadingState label="Loading applications…" />
        ) : apps.error ? (
          <ErrorState message={apps.error} onRetry={apps.reload} />
        ) : apps.data && apps.data.items.length === 0 ? (
          <EmptyState>No applications for this institution yet.</EmptyState>
        ) : apps.data ? (
          <div className={TABLE.wrap}>
            <table className={`${TABLE.table} min-w-[36rem]`}>
              <caption className="sr-only">Applications for {i.name}</caption>
              <thead>
                <tr>
                  <th scope="col" className={TABLE.th}>Application ID</th>
                  <th scope="col" className={TABLE.th}>Academic year</th>
                  <th scope="col" className={TABLE.th}>Type</th>
                  <th scope="col" className={TABLE.th}>Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {apps.data.items.map((a) => (
                  <tr key={a.application_code}>
                    <td className={TABLE.td}>
                      <Link to={`/applications/${a.application_code}`} className={`${buttonStyles.link} whitespace-nowrap font-mono`}>
                        {a.application_code}
                      </Link>
                    </td>
                    <td className={TABLE.td}>{a.academic_year}</td>
                    <td className={TABLE.td}>{APPLICATION_TYPE_LABELS[a.application_type]}</td>
                    <td className={TABLE.td}>
                      <StatusBadge status={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
