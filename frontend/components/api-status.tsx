"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchApiHealth } from "@/lib/api";

export function ApiStatus() {
  const health = useQuery({
    queryKey: ["api-health"],
    queryFn: fetchApiHealth,
  });

  return (
    <div className="status-card" aria-live="polite">
      <h3>Application connection</h3>
      {health.isPending && <p>Checking the FastAPI connection…</p>}
      {health.isError && (
        <p>The frontend cannot reach the API. Check the Docker services.</p>
      )}
      {health.data && (
        <p>
          Connected to {health.data.service}. Backend status:{" "}
          {health.data.status}.
        </p>
      )}
    </div>
  );
}
