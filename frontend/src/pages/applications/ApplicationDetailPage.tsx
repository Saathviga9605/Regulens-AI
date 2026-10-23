import { Pencil } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";

import {
  APPLICATION_TYPE_LABELS,
  INSTITUTION_TYPE_LABELS,
  PROGRAMME_LEVEL_LABELS,
  SHIFT_LABELS,
  STATUS_DESCRIPTIONS,
  STATUS_LABELS,
  TRANSITION_ACTIONS,
  formatDateTime,
} from "../../app/labels";
import { useApiQuery } from "../../app/useApiQuery";
import { ApplicationForm, toFormValues } from "../../components/ApplicationForm";
import { DocumentsPanel } from "../../components/DocumentsPanel";
import { ScrutinyPanel } from "../../components/ScrutinyPanel";
import { ActivityLog } from "../../components/ActivityLog";
import { CopilotPanel } from "../../components/CopilotPanel";
import { EvidenceRequestsPanel } from "../../components/EvidenceRequestsPanel";
import { AlertList } from "../AlertsPage";
import {
  Alert,
  Card,
  DefinitionGrid,
  ErrorState,
  LoadingState,
  PageHeader,
  SectionNav,
  StatusBadge,
  TABLE,
  buttonStyles,
} from "../../components/ui";
import { ApiError, apiClient } from "../../services/apiClient";
import type { Application, ApplicationStatus, Institution } from "../../types/api";

export function ApplicationDetailPage() {
  const { applicationCode = "" } = useParams();
  const location = useLocation();
  const initialFlash = (location.state as { flash?: string } | null)?.flash ?? null;
  const app = useApiQuery(() => apiClient.getApplication(applicationCode), applicationCode);
  const [editing, setEditing] = useState(false);
  const [flash, setFlash] = useState<string | null>(initialFlash);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [institutions, setInstitutions] = useState<Institution[] | null>(null);
  const [documentsVersion, setDocumentsVersion] = useState(0);
  const [focus, setFocus] = useState<{ findingId: string; nonce: number } | null>(null);
  const bump = () => setDocumentsVersion((v) => v + 1);

  if (app.loading && !app.data) return <LoadingState label="Loading application…" />;
  if (app.error && !app.data) return <ErrorState message={app.error} onRetry={app.reload} />;
  if (!app.data) return null;
  const a: Application = app.data;

  async function startEditing() {
    setActionError(null);
    setFlash(null);
    try {
      const page = await apiClient.listInstitutions({ status: "active", page_size: 100 });
      const items = page.items.some((i) => i.institution_code === a.institution.institution_code)
        ? page.items
        : [...page.items, { ...a.institution, address: "", trust_name: "", property_identifier: "", created_at: "", updated_at: "" }];
      setInstitutions(items);
      setEditing(true);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not load institutions.");
    }
  }

  async function transition(target: ApplicationStatus) {
    setBusy(true);
    setActionError(null);
    setFlash(null);
    try {
      const updated = await apiClient.changeApplicationStatus(a.application_code, target);
      app.setData(updated);
      setFlash(`Status changed to “${STATUS_LABELS[updated.status]}”.`);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Status change failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Application workspace"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Applications", to: "/applications" }, { label: a.application_code }]}
        title={a.application_code}
        description={<>
          <span className="font-medium text-ink">{a.institution.name}</span> · {APPLICATION_TYPE_LABELS[a.application_type]} ·
          Academic year {a.academic_year} · <StatusBadge status={a.status} />
        </>}
        actions={
          a.is_editable && !editing ? (
            <button type="button" className={buttonStyles.secondary} onClick={startEditing}>
              <Pencil aria-hidden="true" className="h-4 w-4" /> Edit draft
            </button>
          ) : undefined
        }
      />

      {flash && <Alert tone="success">{flash}</Alert>}
      {actionError && <Alert tone="error">{actionError}</Alert>}

      <SectionNav label="Workspace sections" sections={[
        { id: "overview", label: "Overview" }, { id: "documents", label: "Documents" },
        { id: "scrutiny", label: "Scrutiny & findings" }, { id: "evidence", label: "Evidence requests" },
        { id: "copilot", label: "Copilot" }, { id: "alerts", label: "Alerts" }, { id: "activity", label: "Activity" },
        { id: "institution", label: "Institution" },
      ]} />

      <div id="overview" className="grid scroll-mt-28 gap-5 lg:grid-cols-2">
      <Card title="Internal workflow status">
        <div className="space-y-3">
          <StatusBadge status={a.status} />
          <p className="text-sm text-ink">{STATUS_DESCRIPTIONS[a.status]}</p>
          <p className="text-xs text-ink-subtle">Status last changed {formatDateTime(a.status_changed_at)}.</p>
          {a.allowed_transitions.length > 0 ? (
            <div className="flex flex-wrap gap-2 pt-1">
              {a.allowed_transitions.map((t) => (
                <button
                  key={t}
                  type="button"
                  disabled={busy || editing}
                  onClick={() => transition(t)}
                  className={t === "draft" ? buttonStyles.secondary : buttonStyles.primary}
                >
                  {TRANSITION_ACTIONS[t]}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No further workflow steps are available.</p>
          )}
          {a.status === "draft" && (
            <p className="text-xs text-ink-subtle">
              Marking ready freezes the application details. It does not confirm that required documents are present
              or valid — use preliminary scrutiny below and review its findings.
            </p>
          )}
        </div>
      </Card>

      {editing && institutions ? (
        <div className="lg:col-span-2">
        <Card title="Edit draft">
          <ApplicationForm
            institutions={institutions}
            initial={toFormValues({ ...a, institution_code: a.institution.institution_code })}
            submitLabel="Save changes"
            onCancel={() => setEditing(false)}
            onSubmit={async (input) => {
              const updated = await apiClient.updateApplication(a.application_code, input);
              app.setData(updated);
              setEditing(false);
              setFlash("Draft saved.");
            }}
          />
        </Card>
        </div>
      ) : (
        <>
          <div className="space-y-5">
          <Card title="Application details">
            <DefinitionGrid
              items={[
                ["Application ID", <span className="font-mono">{a.application_code}</span>],
                ["Category", "Extension of Approval (existing institution)"],
                ["Academic year", a.academic_year],
                ["Application type", APPLICATION_TYPE_LABELS[a.application_type]],
                ["Marked ready (internal)", formatDateTime(a.submitted_at)],
                ["Created", formatDateTime(a.created_at)],
                ["Last updated", formatDateTime(a.updated_at)],
                ["Total proposed intake", String(a.total_proposed_intake)],
              ]}
            />
          </Card>

          <Card title="Declared programmes and intake">
            <div className={TABLE.wrap}>
              <table className={`${TABLE.table} min-w-[32rem]`}>
                <caption className="sr-only">Declared programmes</caption>
                <thead>
                  <tr>
                    <th scope="col" className={TABLE.th}>Level</th>
                    <th scope="col" className={TABLE.th}>Course</th>
                    <th scope="col" className={TABLE.th}>Shift</th>
                    <th scope="col" className={`${TABLE.th} text-right`}>Existing</th>
                    <th scope="col" className={`${TABLE.th} text-right`}>Proposed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {a.programmes.map((p) => (
                    <tr key={`${p.programme_level}-${p.course_name}-${p.shift}`}>
                      <td className={TABLE.td}>{PROGRAMME_LEVEL_LABELS[p.programme_level]}</td>
                      <td className={TABLE.td}>{p.course_name}</td>
                      <td className={TABLE.td}>{SHIFT_LABELS[p.shift]}</td>
                      <td className={`${TABLE.td} text-right tabular-nums`}>{p.existing_intake}</td>
                      <td className={`${TABLE.td} text-right tabular-nums`}>{p.proposed_intake}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-ink-subtle">Declared by the applicant; not yet verified against documents.</p>
          </Card>
          </div>
        </>
      )}
      </div>

      <div id="documents" className="scroll-mt-28">
        <DocumentsPanel applicationCode={a.application_code} intakeOpen={a.document_intake_open} refreshKey={documentsVersion}
          onChanged={bump} />
      </div>

      <div id="scrutiny" className="scroll-mt-28">
        <ScrutinyPanel applicationCode={a.application_code} onRunCompleted={bump} focus={focus} />
      </div>

      <div id="evidence" className="scroll-mt-28">
        <EvidenceRequestsPanel applicationCode={a.application_code} version={documentsVersion} onChanged={bump} />
      </div>

      <div id="copilot" className="scroll-mt-28">
        <CopilotPanel applicationCode={a.application_code}
          onOpenFinding={(findingId) => {
            setFocus({ findingId, nonce: Date.now() });
            document.getElementById("scrutiny")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
          }} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card id="alerts" title="Alerts for this application">
          <AlertList key={documentsVersion} applicationCode={a.application_code} compact />
        </Card>
        <Card id="institution"
          title="Institution"
        actions={
          <Link to={`/institutions/${a.institution.institution_code}`} className={`${buttonStyles.link} text-sm`}>
            View institution
          </Link>
        }
      >
        <DefinitionGrid
          items={[
            ["Name", a.institution.name],
            ["Institution code", a.institution.institution_code],
            ["Type", INSTITUTION_TYPE_LABELS[a.institution.institution_type]],
            ["Location", `${a.institution.district}, ${a.institution.state}`],
          ]}
        />
        {a.institution_snapshot && (
          <div className="mt-4 border-t border-line pt-4">
            <h3 className="text-sm font-semibold text-ink">Recorded when marked ready</h3>
            <p className="mb-3 text-xs text-ink-subtle">
              Captured {formatDateTime(a.institution_snapshot.captured_at)}. Later institution edits do not change this record.
            </p>
            <DefinitionGrid
              items={[
                ["Name", a.institution_snapshot.name],
                ["Address", a.institution_snapshot.address],
                ["Trust or sponsoring body", a.institution_snapshot.trust_name],
                ["Property / survey identifier", a.institution_snapshot.property_identifier],
              ]}
            />
          </div>
        )}
      </Card>
      </div>

      <Card id="activity" title="Activity (audit trail for this application)">
        <ActivityLog key={documentsVersion} applicationCode={a.application_code} />
      </Card>
    </div>
  );
}
