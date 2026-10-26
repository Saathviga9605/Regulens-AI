import { useApiQuery } from "../app/useApiQuery";
import { Badge, Card, ErrorState, EvidenceQuote, LoadingState, PageHeader, TABLE, type Tone } from "../components/ui";
import { apiClient } from "../services/apiClient";
import type { RuleClassification } from "../types/api";

const CLASSIFICATION: Record<RuleClassification, { label: string; tone: Tone }> = {
  SOURCE_VERIFIED: { label: "Source verified", tone: "success" },
  PARTIALLY_VERIFIED: { label: "Partially verified", tone: "info" },
  UNRESOLVED: { label: "Unresolved", tone: "warning" },
  DEMO_ONLY: { label: "Demo-only", tone: "warning" },
  RETIRED: { label: "Retired", tone: "neutral" },
  INTEGRITY_CHECK: { label: "Integrity check", tone: "neutral" },
};

export function ClassificationBadge({ value }: { value: RuleClassification }) {
  const c = CLASSIFICATION[value];
  return <Badge tone={c.tone}>{c.label}</Badge>;
}

/** Read-only view of the pinned handbook and every rule's provenance, served from the backend registry (no network). */
export function RegulatorySourcePage() {
  const q = useApiQuery(() => apiClient.regulatorySource(), "regulatory-source");
  const data = q.data;
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Rules" title="Regulatory source"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Regulatory source" }]}
        description="The pinned handbook and the clause, page and quotation behind each rule." />
      {q.error ? <ErrorState message={q.error} onRetry={q.reload} /> : !data ? <LoadingState label="Loading source…" /> : (
        <>
          <Card title={data.source.title} description={`${data.source.publisher} · edition ${data.source.edition}`}>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
              <dt className="text-ink-muted">Official URL</dt>
              <dd className="font-mono text-xs [overflow-wrap:anywhere]">{data.source.canonical_url}</dd>
              <dt className="text-ink-muted">SHA-256</dt>
              <dd className="font-mono text-xs [overflow-wrap:anywhere]" data-testid="source-sha256">{data.source.sha256}</dd>
              <dt className="text-ink-muted">File</dt>
              <dd>{data.source.pdf_page_count} pages · {data.source.bytes.toLocaleString("en-IN")} bytes · retrieved {data.source.retrieved_on}</dd>
              <dt className="text-ink-muted">Status</dt>
              <dd><Badge tone={data.source.verification.status === "verified" ? "success" : "warning"}>
                {data.source.verification.status === "verified" ? "Verified against the official file" : data.source.verification.status}
              </Badge> <span className="text-ink-muted">on {data.source.verification.verified_on}</span></dd>
              <dt className="text-ink-muted">Version policy</dt>
              <dd>{data.source.version_policy}</dd>
            </dl>
            {data.source.unresolved_references.length > 0 && (
              <div className="mt-4 rounded-control border border-warning-line bg-warning-bg p-3 text-sm text-warning-800">
                <p className="font-semibold">Unresolved references</p>
                <ul className="mt-1 list-disc pl-5">
                  {data.source.unresolved_references.map((u) => (
                    <li key={u.reference}>{u.reference} (cited in {u.cited_from}): {u.detail}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          <Card title={`Handbook-cited rules — profile ${data.aph_profile.profile_id} v${data.aph_profile.version}`}
            description={data.aph_profile.default
              ? "This profile is the default for new scrutiny runs; reviewers can still choose the production rules."
              : "These rules run only when this profile is selected for a scrutiny run; it is not the default."}>
            <ul className="space-y-5">
              {data.aph_profile.rules.map((r) => (
                <li key={r.rule_id} className="space-y-2 border-b border-line pb-4 last:border-0 last:pb-0" data-testid={`aph-rule-${r.rule_id}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-semibold">{r.rule_id} v{r.version}</span>
                    <span className="font-medium">{r.title}</span>
                    <ClassificationBadge value={r.classification} />
                  </div>
                  <EvidenceQuote quote={r.quote}
                    source={<>{r.clause} · PDF page {r.pdf_page}{r.printed_page && ` (printed page ${r.printed_page})`}</>} />
                  <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
                    <dt className="text-ink-muted">Interpretation</dt><dd>{r.interpretation}</dd>
                    <dt className="text-ink-muted">Applies to</dt><dd>{r.applicability}</dd>
                    <dt className="text-ink-muted">Evidence</dt><dd>{r.required_evidence}</dd>
                  </dl>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Production-profile rules" description="None of these cite the handbook; their classification says what they are.">
            <div className={TABLE.wrap}>
              <table className={TABLE.table}>
                <thead><tr>
                  <th scope="col" className={TABLE.th}>Rule</th>
                  <th scope="col" className={TABLE.th}>Classification</th>
                  <th scope="col" className={TABLE.th}>Source</th>
                </tr></thead>
                <tbody className="divide-y divide-line">
                  {data.production_rules.map((r) => (
                    <tr key={r.rule_id}>
                      <td className={TABLE.td}><span className="font-mono">{r.rule_id}</span> v{r.version} — {r.title}{!r.enabled && " (disabled)"}</td>
                      <td className={TABLE.td}><ClassificationBadge value={r.classification} /></td>
                      <td className={`${TABLE.td} [overflow-wrap:anywhere]`}>{r.source}{r.source_reference ? ` — ${r.source_reference}` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
