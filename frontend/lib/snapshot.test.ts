import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { fetchSnapshot } from "./snapshot";
import type {
  ApiCollection,
  ApiRecord,
  BoroughCorrelation,
  CorrelationSummary,
  GradeTrendPoint,
  History,
  Restaurant,
  RiskRecord,
  Violation,
  WeeklyPoint,
} from "../types/dashboard";

describe("published dashboard snapshot", () => {
  beforeAll(() => {
    vi.stubGlobal("fetch", async (input: string | URL | Request) => {
      const url = typeof input === "string" ? input : input.toString();
      const relative = url.replace(/^\//, "");
      try {
        const body = await readFile(join(process.cwd(), "public", relative));
        return new Response(body, {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      } catch {
        return new Response("Not found", { status: 404 });
      }
    });
  });

  afterAll(() => vi.unstubAllGlobals());

  it("provides all chart datasets without FastAPI", async () => {
    const kpis = await fetchSnapshot<ApiCollection<unknown>>("/overview/kpis");
    const boroughs = await fetchSnapshot<ApiCollection<unknown>>(
      "/overview/boroughs",
      { sort: "safety_rank" },
    );
    const heatmap = await fetchSnapshot<ApiCollection<unknown>>(
      "/overview/cuisine-heatmap",
    );
    const weekly = await fetchSnapshot<ApiCollection<WeeklyPoint>>(
      "/correlation/weekly",
      { weeks: 26, complaint_type: "ALL" },
    );
    const summary = await fetchSnapshot<CorrelationSummary>(
      "/correlation/summary",
      { weeks: 26, lag_weeks: 2, complaint_type: "ALL" },
    );
    const ranking = await fetchSnapshot<ApiCollection<BoroughCorrelation>>(
      "/correlation/borough-ranking",
      { weeks: 26, lag_weeks: 2, complaint_type: "ALL" },
    );
    const gradeTrends = await fetchSnapshot<ApiCollection<GradeTrendPoint>>(
      "/risk/grade-trends",
    );

    expect(kpis.items).toHaveLength(6);
    expect(boroughs.items).toHaveLength(5);
    expect(heatmap.items.length).toBeGreaterThan(0);
    expect(weekly.items).toHaveLength(26);
    expect(summary.observations).toBe(26);
    expect(ranking.items).toHaveLength(5);
    expect(gradeTrends.items).toHaveLength(12);
    expect(gradeTrends.items.map((row) => row.grade_percent)).toContain(93.8);
  });

  it("supports finder filters and restaurant modal data", async () => {
    const initial = await fetchSnapshot<ApiCollection<Restaurant>>(
      "/restaurants",
      { page: 1, page_size: 12, sort: "name" },
    );
    const restaurant = initial.items[0];
    const searched = await fetchSnapshot<ApiCollection<Restaurant>>(
      "/restaurants",
      { query: restaurant.restaurant_id, page: 1, page_size: 12 },
    );
    const detail = await fetchSnapshot<ApiRecord<Restaurant>>(
      `/restaurants/${restaurant.restaurant_key}`,
    );
    const history = await fetchSnapshot<ApiCollection<History>>(
      `/restaurants/${restaurant.restaurant_key}/history`,
    );
    const violations = await fetchSnapshot<ApiCollection<Violation>>(
      `/restaurants/${restaurant.restaurant_key}/violations`,
    );
    const nearby = await fetchSnapshot<ApiCollection<Restaurant>>(
      `/restaurants/${restaurant.restaurant_key}/nearby`,
      { radius_meters: 1000, limit: 8 },
    );

    expect(initial.total).toBeGreaterThan(20_000);
    expect(searched.items.some((row) => row.restaurant_key === restaurant.restaurant_key)).toBe(true);
    expect(detail.data.restaurant_key).toBe(restaurant.restaurant_key);
    expect(history.items.length).toBeGreaterThan(0);
    expect(violations.items.length).toBeLessThanOrEqual(6);
    expect(Array.isArray(nearby.items)).toBe(true);
  });

  it("supports chain modals and predictive-risk analysis", async () => {
    const chains = await fetchSnapshot<ApiCollection<Record<string, unknown>>>(
      "/chains",
      { page: 1, page_size: 12, confirmed_fast_food_only: false },
    );
    const chain = chains.items[0];
    const locations = await fetchSnapshot<ApiCollection<Restaurant>>(
      `/chains/${chain.chain_key}/locations`,
    );
    const risks = await fetchSnapshot<ApiCollection<RiskRecord>>(
      "/risk/restaurants",
      { page: 1, page_size: 20, sort: "risk", direction: "desc" },
    );
    const detail = await fetchSnapshot<ApiRecord<RiskRecord>>(
      `/risk/restaurants/${risks.items[0].restaurant_key}`,
    );

    expect(chains.total).toBeGreaterThan(0);
    expect(locations.items.length).toBeGreaterThan(1);
    expect(risks.total).toBeGreaterThan(20_000);
    expect(detail.data.main_contributing_factors.length).toBeGreaterThan(0);
  });
});
