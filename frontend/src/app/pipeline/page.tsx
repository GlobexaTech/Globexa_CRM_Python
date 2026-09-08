import { Suspense } from "react";
import Sidebar from "@/components/Sidebar";
import PipelineBoard from "@/components/PipelineBoard";
export default function PipelinePage() {
  return (
    <main className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar />
      <section className="min-w-0 flex-1 p-8">
        <Suspense fallback={<p role="status">Loading pipeline…</p>}>
          <PipelineBoard />
        </Suspense>
      </section>
    </main>
  );
}
