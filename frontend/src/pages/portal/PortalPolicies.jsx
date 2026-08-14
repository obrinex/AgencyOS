import PoliciesView from "@/components/PoliciesView";

export default function PortalPolicies() {
  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto" data-testid="portal-policies">
      <h1 className="font-display text-2xl font-bold mb-1">Policies</h1>
      <p className="text-sm text-graphite mb-4">
        Our terms, privacy, refund, service level, and other policies — open for you to read anytime.
      </p>
      <PoliciesView />
    </div>
  );
}
