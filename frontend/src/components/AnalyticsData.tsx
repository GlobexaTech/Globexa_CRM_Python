import type {
  Analytics,
  AnalyticsView,
  PipelineMetric,
} from "@/services/workspace";
import { money } from "@/services/workspace";
export function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="metric-card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </div>
  );
}
export function PipelineMetrics({ stages }: { stages: PipelineMetric[] }) {
  return stages.length ? (
    <div
      className="crm-table-wrap"
      role="region"
      aria-label="Pipeline values"
      tabIndex={0}
    >
      <table>
        <thead>
          <tr>
            <th scope="col">Stage</th>
            <th scope="col">Deals</th>
            <th scope="col">Value</th>
          </tr>
        </thead>
        <tbody>
          {stages.map((stage, index) => (
            <tr key={`${stage.id}:${stage.currency}:${index}`}>
              <td>{stage.name}</td>
              <td>{stage.deals}</td>
              <td>{money(stage.value, stage.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="crm-muted py-4">No pipeline data in this range.</p>
  );
}
export function AnalyticsData({
  view,
  data,
}: {
  view: AnalyticsView;
  data: Analytics;
}) {
  if (view === "pipeline")
    return <PipelineMetrics stages={data.stages ?? []} />;
  if (view === "conversion")
    return (
      <div className="stat-grid">
        <Metric label="Leads" value={data.leads ?? 0} />
        <Metric label="Converted" value={data.converted ?? 0} />
        <Metric
          label="Conversion rate"
          value={`${((data.conversion_rate ?? 0) * 100).toFixed(1)}%`}
        />
      </div>
    );
  if (view === "campaigns")
    return (
      <div className="stat-grid">
        {Object.entries(data.delivery_status ?? {}).map(([status, count]) => (
          <Metric
            key={status}
            label={status.replaceAll("_", " ")}
            value={count}
          />
        ))}
        {!Object.keys(data.delivery_status ?? {}).length && (
          <p>No recipient activity in this range.</p>
        )}
      </div>
    );
  if (view === "activity")
    return (
      <>
        <div className="stat-grid">
          <Metric
            label="Average first response (all time)"
            value={
              data.first_response_seconds == null
                ? "No sample"
                : `${Math.round(data.first_response_seconds)} s`
            }
          />
          <Metric
            label="Response samples (all time)"
            value={data.response_sample_count ?? 0}
          />
        </div>
        <div className="crm-table-wrap mt-4">
          <table>
            <thead>
              <tr>
                <th>Processed event</th>
                <th>Count in selected range</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.events ?? {}).map(([event, count]) => (
                <tr key={event}>
                  <td>{event}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  if (view === "ai")
    return (
      <div
        className="crm-table-wrap"
        role="region"
        aria-label="AI usage"
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th>Outcome</th>
              <th>Requests</th>
              <th>Tokens</th>
              <th>Known cost (USD)</th>
              <th>Unpriced requests</th>
            </tr>
          </thead>
          <tbody>
            {(data.usage ?? []).map((row) => (
              <tr key={String(row.success)}>
                <td>{row.success ? "Successful" : "Failed"}</td>
                <td>{row.requests}</td>
                <td>{row.tokens ?? 0}</td>
                <td>
                  {row.known_cost_usd == null
                    ? "Unavailable"
                    : Number(row.known_cost_usd).toFixed(4)}
                </td>
                <td>{row.unpriced_requests}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.usage?.length && (
          <p className="crm-muted py-4">No AI usage in this range.</p>
        )}
      </div>
    );
  return (
    <div className="stat-grid">
      {(
        [
          ["Leads", data.leads],
          ["Deals", data.deals],
          ["Open tasks", data.open_tasks],
          ["Completed tasks", data.completed_tasks],
          ["Pending jobs", data.pending_jobs],
          ["Failed or unknown jobs", data.failed_jobs],
        ] as const
      ).map(([label, value]) => (
        <Metric key={label} label={label} value={value ?? 0} />
      ))}
    </div>
  );
}
