import { Link } from "react-router";

import { EmptyState, PageHeader, buttonStyles } from "../components/ui";

export function NotFoundPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Page not found" breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Not found" }]} />
      <EmptyState title="The requested page does not exist."
        action={<Link to="/" className={buttonStyles.primary}>Return to the overview</Link>}>
        Check the address, or use the navigation to find the record you need.
      </EmptyState>
    </div>
  );
}
