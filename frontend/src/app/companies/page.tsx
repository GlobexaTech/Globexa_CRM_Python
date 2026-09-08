import { Suspense } from "react";
import CrmEntityPage from "@/app/leads/CrmEntityPage";
export default function CompaniesPage() {
  return (
    <Suspense fallback={<p role="status">Loading companies…</p>}>
      <CrmEntityPage kind="companies" />
    </Suspense>
  );
}
