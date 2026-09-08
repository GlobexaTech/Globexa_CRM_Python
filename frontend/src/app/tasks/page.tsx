import { Suspense } from "react";
import CrmEntityPage from "@/app/leads/CrmEntityPage";
export default function TasksPage() {
  return (
    <Suspense fallback={<p role="status">Loading tasks…</p>}>
      <CrmEntityPage kind="tasks" />
    </Suspense>
  );
}
