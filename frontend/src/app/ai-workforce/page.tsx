import { WorkforceWorkspace } from "@/components/WorkforceWorkspace";
import type { WorkforceContext } from "@/types/workforce";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const kind = params.entity_type;
  const id = params.entity_id;
  const context: WorkforceContext =
    typeof kind === "string" &&
    ["lead", "contact", "deal", "conversation", "campaign"].includes(kind) &&
    typeof id === "string" &&
    /^[a-f\d-]{36}$/i.test(id)
      ? { entity_type: kind as WorkforceContext["entity_type"], entity_id: id }
      : {};
  return <WorkforceWorkspace initialContext={context} />;
}
