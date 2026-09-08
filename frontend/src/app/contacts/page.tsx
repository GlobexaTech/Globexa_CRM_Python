import { Suspense } from "react";
import CrmEntityPage from "@/app/leads/CrmEntityPage";
export default function ContactsPage() {
  return (
    <Suspense fallback={<p role="status">Loading contacts…</p>}>
      <CrmEntityPage kind="contacts" />
    </Suspense>
  );
}
