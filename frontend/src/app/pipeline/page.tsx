import Sidebar from "@/components/Sidebar";
import PipelineBoard from "@/components/PipelineBoard";

export default function PipelinePage() {
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />

      <section className="min-w-0 flex-1 p-8">
        <p className="text-xs tracking-[3px] text-[var(--blue2)]">
          CUSTOMER JOURNEY
        </p>

        <header className="mb-8 mt-2 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold">Lead Pipeline</h1>

            <p className="mt-1 text-sm text-[var(--muted)]">
              Drag opportunities through your customer journey.
            </p>
          </div>

          <button className="rounded-xl bg-[var(--blue)] px-5 py-2.5 text-sm">
            + New Lead
          </button>
        </header>

        <PipelineBoard />
      </section>
    </main>
  );
}