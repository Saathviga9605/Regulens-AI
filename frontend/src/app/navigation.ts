import {
  Building2,
  ClipboardList,
  FileCheck2,
  FileText,
  History,
  LayoutDashboard,
  ShieldCheck,
  SlidersHorizontal,
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
    summary: "EoA applications, their documents, extracted evidence and preliminary scrutiny findings.",
    available: true,
    plannedScope: [],
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
    path: "/scrutiny-rules",
    label: "Scrutiny Rules",
    icon: SlidersHorizontal,
    summary: "View and configure the deterministic preliminary-scrutiny rules and their source status.",
    available: true,
    plannedScope: [],
  },
  {
    path: "/review-queue",
    label: "Review Queue",
    icon: ClipboardList,
    summary: "Cross-application queue of findings awaiting human review.",
    available: false,
    plannedScope: [
      "Prioritised list of open findings across applications",
      "Reviewer assignment (requires authentication)",
    ],
  },
  {
    path: "/verification",
    label: "Verification",
    icon: ShieldCheck,
    summary: "Cross-application overview of issuer-verification attempts.",
    available: false,
    plannedScope: [
      "Overview of simulated checks across applications (per-document simulated checks already exist)",
      "Real issuer integrations only if officially authorised — none exist in this prototype",
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
