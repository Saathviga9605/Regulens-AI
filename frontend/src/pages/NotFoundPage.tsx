import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold text-slate-900">Page not found</h1>
      <p className="mt-2 text-sm text-slate-600">
        The requested page does not exist.{" "}
        <Link to="/" className="font-medium text-blue-700 underline hover:text-blue-800">
          Return to the dashboard
        </Link>
        .
      </p>
    </div>
  );
}
