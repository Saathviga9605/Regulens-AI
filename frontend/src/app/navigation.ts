import { ClipboardList, FileCheck2, FileText, History, LayoutDashboard, ShieldCheck, type LucideIcon } from "lucide-react";

export interface ModuleDefinition {
  path: string;
  label: string;
  icon: LucideIcon;
  summary: string;
  plannedScope: string[];
}

export const DASHBOARD_NAV = { path: "/", label: "Dashboard", icon: LayoutDashboard } as const;

export const MODULES: ModuleDefinition[] = [
  {
    path: "/applications",
    label: "Applications",
    icon: FileText,
    summary: "Manage Extension of Approval applications and institutional records.",
    plannedScope: [
      "Create and view EoA application records",
      "Upload PDF supporting documents",
      "OCR and evidence-linked structured extraction",
    ],
  },
  {
    path: "/review-queue",
    label: "Review Queue",
    icon: ClipboardList,
    summary: "Prioritised queue of applications awaiting human scrutiny.",
    plannedScope: [
      "Rule-based validation findings with regulatory provenance",
      "Cross-document consistency checks",
      "Preliminary anomaly flags for reviewer attention",
    ],
  },
  {
    path: "/verification",
    label: "Verification",
    icon: ShieldCheck,
    summary: "Issuer-verification workflows for supporting documents.",
    plannedScope: [
      "Simulated issuer verification requests (no real government APIs)",
      "Verification status tracking per document",
    ],
  },
  {
    path: "/reports",
    label: "Reports",
    icon: FileCheck2,
    summary: "Preliminary scrutiny reports to support reviewer decisions.",
    plannedScope: [
      "Evidence-cited preliminary scrutiny reports",
      "Reviewer notes and final human decision recording",
    ],
  },
  {
    path: "/audit-trail",
    label: "Audit Trail",
    icon: History,
    summary: "Immutable record of actions taken on applications.",
    plannedScope: ["Chronological audit log of user and system actions", "Filtering by application and actor"],
  },
];
