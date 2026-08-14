import PageHeader from "@/components/PageHeader";
import PoliciesView from "@/components/PoliciesView";

export default function Policies() {
  return (
    <div className="p-6 max-w-5xl mx-auto" data-testid="policies-page">
      <PageHeader title="Legal & Policies"
        description="Every Obrinex policy, viewable here and in each client's portal — full transparency." />
      <div className="mt-4"><PoliciesView /></div>
    </div>
  );
}
