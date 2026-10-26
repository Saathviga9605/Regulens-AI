import {
  Bell,
  Building2,
  ClipboardList,
  FileText,
  History,
  Layers,
  LayoutDashboard,
  LifeBuoy,
  ScrollText,
  SlidersHorizontal,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  /** Shown only to administrators. The backend enforces the same restriction independently. */
  adminOnly?: boolean;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

/** Sidebar structure. Every path here is a real, implemented route (see App.tsx). */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ path: "/", label: "Overview", icon: LayoutDashboard }],
  },
  {
    label: "Scrutiny work",
    items: [
      { path: "/review-queue", label: "Review Queue", icon: ClipboardList },
      { path: "/applications", label: "Applications", icon: FileText },
      { path: "/institutions", label: "Institutions", icon: Building2 },
      { path: "/alerts", label: "Alerts", icon: Bell },
      { path: "/cross-case", label: "Cross-case reuse", icon: Layers },
    ],
  },
  {
    label: "Administration",
    items: [
      { path: "/scrutiny-rules", label: "Scrutiny Rules", icon: SlidersHorizontal },
      { path: "/users", label: "Users", icon: Users, adminOnly: true },
      { path: "/audit-trail", label: "Audit Trail", icon: History, adminOnly: true },
    ],
  },
  {
    label: "Support",
    items: [
      { path: "/regulatory-source", label: "Regulatory source", icon: ScrollText },
      { path: "/help", label: "Help & About", icon: LifeBuoy },
    ],
  },
];

/** The single product-identity statement, shown in the app footer and on the sign-in page. */
export const IDENTITY_STATEMENT =
  "ReguLens AI is independent decision-support software. It is not an AICTE service; findings require human review and it never approves or rejects applications.";
