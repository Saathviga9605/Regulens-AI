import { useState } from "react";

import { TRUST_NOTICE } from "../app/navigation";
import { Alert, Card, PageHeader, Tabs } from "../components/ui";

type Topic = "workflow" | "evidence" | "limits" | "signin";
const TOPICS: [Topic, string][] = [
  ["workflow", "Scrutiny workflow"],
  ["evidence", "Evidence & uncertainty"],
  ["limits", "Demo rules & simulation"],
  ["signin", "Signing in"],
];

export function HelpPage() {
  const [topic, setTopic] = useState<Topic>("workflow");
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Support" title="Help & About" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Help & About" }]}
        description="How ReguLens supports preliminary scrutiny, and what it does not do." />
      <Alert tone="warning" title="About this prototype">
        {TRUST_NOTICE} ReguLens AI is an independent Smart India Hackathon prototype using fictional data. It is not an
        AICTE service and is not affiliated with or endorsed by any government body.
      </Alert>
      <Card>
        <Tabs label="Help topics" tabs={TOPICS} value={topic} onChange={setTopic} />
        <div role="tabpanel" aria-label={TOPICS.find(([k]) => k === topic)?.[1]} className="prose-sm mt-4 space-y-3 text-sm text-ink">
          {topic === "workflow" && (
            <ol className="list-decimal space-y-2 pl-5">
              <li><strong>Review Queue</strong> lists applications by unresolved findings. Open one to work in its workspace.</li>
              <li><strong>Supporting documents</strong>: upload PDFs, then <em>Process all</em> to extract page text, detect the document type and extract labelled fields with quotes.</li>
              <li><strong>Preliminary scrutiny</strong> runs the configured rules and anomaly detectors and records a run. Reruns keep history.</li>
              <li>Open a finding to read its explanation and evidence, then <strong>confirm, dismiss, escalate, request evidence, resolve or add an observation</strong>. Reasons are required for consequential actions; every action is kept in the history and audit log.</li>
              <li><strong>Evidence requests</strong> track what you asked for. Link uploaded documents explicitly, then mark the request fulfilled.</li>
              <li>Download the <strong>preliminary report</strong> (PDF) for a run. It is marked “Preliminary scrutiny — human review required”.</li>
            </ol>
          )}
          {topic === "evidence" && (
            <ul className="list-disc space-y-2 pl-5">
              <li>Extracted values come only from explicitly labelled text and show the quoted line and page number.</li>
              <li><strong>Not found</strong>: no labelled value in readable text. <strong>Ambiguous</strong>: several values or an unclear date. <strong>Unverified</strong>: the quote could not be matched to the page text. None of these are treated as verified.</li>
              <li><strong>Inconclusive</strong> findings mean the evidence was missing, unreadable or unclear — they are not passes.</li>
              <li>An exact duplicate (same SHA-256) means identical file content. It is not evidence of wrongdoing.</li>
              <li>The copilot answers only from this application's stored records and cites them; it never decides.</li>
            </ul>
          )}
          {topic === "limits" && (
            <ul className="list-disc space-y-2 pl-5">
              <li>Rules labelled <strong>Demo-only</strong> are prototype expectations that have not been verified against the AICTE Approval Process Handbook or any official source.</li>
              <li>Issuer checks are <strong>SIMULATED — NOT VERIFIED WITH THE ISSUING AUTHORITY</strong>: they compare extracted fields with synthetic demo records. No authority is contacted.</li>
              <li>OCR for scanned pages needs a local Tesseract installation; without it those pages are reported as unreadable.</li>
              <li>The audit log is application-level append-only; it is not a certified tamper-evident record.</li>
            </ul>
          )}
          {topic === "signin" && (
            <div className="space-y-2">
              <p>Local demo accounts are configured in the backend <code>.env</code> file (<code>REGULENS_DEMO_*</code>) and created by <code>python -m app.cli seed</code>. The README lists the default local demo usernames and passwords.</p>
              <p><strong>Reviewers</strong> can review applications, act on findings, request evidence and generate reports. <strong>Administrators</strong> can also manage users, configure scrutiny rules and view the global audit trail.</p>
              <p>Demo credentials are for local demonstration only — change them before sharing the application.</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
