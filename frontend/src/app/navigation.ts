import {
  Building2,
  ClipboardList,
  FileCheck2,
  FileText,
  History,
  LayoutDashboard,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export interface ModuleDefinition {
  path: string;
  label: string;
  icon: LucideIcon;
  summary: string;
  /** false = route renders a clearly labelled "Planned" placeholder. */
  available: boolean;
  plannedScope: string[];
}

export const DASHBOARD_NAV = { path: "/", label: "Dashboard", icon: LayoutDashboard } as const;

export const MODULES: ModuleDefinition[] = [
  {
    path: "/applications",
    label: "Applications",
    icon: FileText,
    summary: "Create, list and update EoA applications and their internal workflow status.",
    available: true,
    plannedScope: ["Upload PDF supporting documents", "OCR and evidence-linked structured extraction"],
  },
  {
    path: "/institutions",
    label: "Institutions",
    icon: Building2,
    summary: "Manage fictional institution records used by applications.",
    available: true,
    plannedScope: [],
  },
  {
    path: "/review-queue",
    label: "Review Queue",
    icon: ClipboardList,
    summary: "Prioritised queue of applications awaiting human scrutiny.",
    available: false,
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
    available: false,
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
    available: false,
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
    available: false,
    plannedScope: ["Chronological audit log of user and system actions", "Filtering by application and actor"],
  },
];
