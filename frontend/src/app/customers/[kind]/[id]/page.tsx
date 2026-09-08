import CustomerProfile from "../../CustomerProfile";
export default async function CustomerPage({
  params,
}: {
  params: Promise<{ kind: string; id: string }>;
}) {
  const { kind, id } = await params;
  return <CustomerProfile kind={kind} id={id} />;
}
