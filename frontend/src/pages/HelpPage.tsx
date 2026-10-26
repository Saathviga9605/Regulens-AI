import { useState } from "react";

import { Link } from "react-router";

import { useBackendHealth } from "../app/BackendHealthContext";
import { IDENTITY_STATEMENT } from "../app/navigation";
import { SystemStatusPanel } from "../components/SystemStatusPanel";
import { Card, PageHeader, Tabs, buttonStyles } from "../components/ui";

type Topic = "workflow" | "evidence" | "verification" | "rules" | "signin" | "status" | "about";
const TOPICS: [Topic, string][] = [
  ["workflow", "Scrutiny workflow"],
  ["evidence", "Evidence & uncertainty"],
  ["verification", "Issuer verification"],
  ["rules", "Rules & handbook"],
  ["signin", "Signing in"],
  ["status", "System status"],
  ["about", "About"],
];

export function HelpPage() {
  const [topic, setTopic] = useState<Topic>("workflow");
  const { state, refresh } = useBackendHealth();
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Support" title="Help & About" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Help & About" }]}
        description="How ReguLens supports preliminary scrutiny, and what it does not do." />
      <Card>
        <Tabs label="Help topics" tabs={TOPICS} value={topic} onChange={setTopic} />
        <div role="tabpanel" aria-label={TOPICS.find(([k]) => k === topic)?.[1]} className="prose-sm mt-4 space-y-3 text-sm text-ink">
          {topic === "workflow" && (
            <ol className="list-decimal space-y-2 pl-5">
              <li><strong>Review Queue</strong> lists applications by unresolved findings. Open one to work in its workspace.</li>
              <li><strong>Supporting documents</strong>: upload PDF, PNG or JPEG files, then <em>Process all</em> to extract page text, detect the document type and extract labelled fields with quotes.</li>
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
          {topic === "verification" && (
            <ul className="list-disc space-y-2 pl-5">
              <li><strong>SIMULATED</strong> issuer checks compare extracted fields with synthetic records. No issuing authority is contacted.</li>
              <li><strong>NOT CONNECTED</strong> means no live connection to that issuer exists. A reviewer can record what they checked manually (for example by phone or on an official portal); the result is shown as reviewer-recorded, with their name.</li>
              <li>QR codes, reference formats and digital-signature fields are <em>integrity indicators</em>: they show what the file contains, not that the issuer confirmed it. Signatures are detected, not cryptographically validated.</li>
              <li>Visual similarity between documents in different cases is a prompt for review. It does not prove reuse or fraud.</li>
            </ul>
          )}
          {topic === "rules" && (
            <ul className="list-disc space-y-2 pl-5">
              <li>The pinned regulatory source is the AICTE <em>Approval Process Handbook 2024–25 to 2026–27</em>, identified by its official URL and SHA-256. See <Link to="/regulatory-source" className={buttonStyles.link}>Regulatory source</Link> for the clauses, pages and quotations each rule relies on.</li>
              <li>Each rule shows a classification: <strong>source verified</strong>, <strong>partially verified</strong> (the quote is verified but applying it involves interpretation), <strong>unresolved</strong>, <strong>demo-only</strong> (no handbook citation), <strong>integrity check</strong> or <strong>retired</strong>.</li>
              <li>The handbook-cited rules run only in the separately selected APH profile. The default profile is unchanged and its rules are not handbook-backed.</li>
              <li>Each run stores the rule versions and source hash it used, so later rule changes do not alter past results.</li>
              <li>Scanned pages are read with a local OCR engine (RapidOCR or Tesseract) when one is installed; otherwise they are reported as unreadable.</li>
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
          {topic === "status" && <SystemStatusPanel state={state} onRetry={refresh} />}
          {topic === "about" && (
            <div className="space-y-2">
              <p>{IDENTITY_STATEMENT}</p>
              <p>Records in this installation are fictional unless your organisation has loaded its own data.</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
