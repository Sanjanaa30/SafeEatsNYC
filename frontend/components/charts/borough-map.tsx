"use client";

import { useQuery } from "@tanstack/react-query";
import { ErrorState, LoadingState } from "@/components/ui/data-states";
import {
  confidenceIncludesZero,
  correlationDirection,
  correlationLabel,
  correlationStrength,
  evidenceLabel,
} from "@/lib/correlation";
import type { BoroughCorrelation } from "@/types/dashboard";

type Position = [number, number];
type Geometry = {
  type: "Polygon" | "MultiPolygon";
  coordinates: Position[][] | Position[][][];
};
type GeoJson = {
  features: { properties: { boroname: string }; geometry: Geometry }[];
};

const relationshipDetails = (correlation: number | null | undefined) => {
  const strength = correlationStrength(correlation);
  const negative = correlation != null && correlation < 0;
  const negativeColors: Record<string, string> = {
    Weak: "#e1ad94",
    Moderate: "#d18462",
    Strong: "#a94731",
  };
  const positiveColors: Record<string, string> = {
    Weak: "#d6ad55",
    Moderate: "#76a88a",
    Strong: "#2f684f",
  };
  const color = negative
    ? (negativeColors[strength] ?? "#d8d3cc")
    : (positiveColors[strength] ?? "#d8d3cc");
  return { label: correlationLabel(correlation), color };
};

const displayBorough = (value: string) =>
  value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

export function BoroughMap({
  rows,
  lagWeeks,
}: {
  rows: BoroughCorrelation[];
  lagWeeks: number;
}) {
  const query = useQuery<GeoJson>({
    queryKey: ["borough-boundaries"],
    queryFn: async () => {
      const response = await fetch("/maps/nyc_borough_boundaries.geojson");
      if (!response.ok) throw new Error("Map boundaries are unavailable.");
      return response.json();
    },
    staleTime: Infinity,
  });
  if (query.isLoading) return <LoadingState label="Loading borough map" />;
  if (query.isError || !query.data)
    return <ErrorState message="The borough map could not be loaded." />;

  const positions = query.data.features.flatMap((feature) =>
    flatten(feature.geometry),
  );
  const xs = positions.map(([x]) => x);
  const ys = positions.map(([, y]) => y);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const viewWidth = 520,
    viewHeight = 560,
    padding = 28;
  const longitudeScale = Math.cos((((minY + maxY) / 2) * Math.PI) / 180);
  const geographicWidth = (maxX - minX) * longitudeScale;
  const geographicHeight = maxY - minY;
  const scale = Math.min(
    (viewWidth - 2 * padding) / geographicWidth,
    (viewHeight - 2 * padding) / geographicHeight,
  );
  const offsetX = (viewWidth - geographicWidth * scale) / 2;
  const offsetY = (viewHeight - geographicHeight * scale) / 2;
  const project = ([x, y]: Position) => [
    offsetX + (x - minX) * longitudeScale * scale,
    viewHeight - offsetY - (y - minY) * scale,
  ];
  const makePath = (geometry: Geometry) =>
    polygons(geometry)
      .map((polygon) =>
        polygon
          .map(
            (ring) =>
              ring
                .map(
                  (point, index) =>
                    `${index ? "L" : "M"}${project(point).join(",")}`,
                )
                .join(" ") + " Z",
          )
          .join(" "),
      )
      .join(" ");

  const lagText =
    lagWeeks === 0
      ? "in the same week"
      : `${lagWeeks} week${lagWeeks === 1 ? "" : "s"} later`;
  const sortedRows = [...rows].sort((left, right) =>
    left.borough_name.localeCompare(right.borough_name),
  );

  return (
    <div className="borough-map-layout relationship-map-layout">
      <div>
        <svg
          className="borough-map"
          viewBox={`0 0 ${viewWidth} ${viewHeight}`}
          role="img"
          aria-label={`Map showing how closely weekly complaints matched critical inspections ${lagText} in each borough`}
        >
          {query.data.features.map((feature) => {
            const row = rows.find(
              (item) =>
                item.borough_name === feature.properties.boroname.toUpperCase(),
            );
            const correlation =
              row?.correlation == null ? null : Number(row.correlation);
            const details = relationshipDetails(correlation);
            const observations = Number(row?.observations ?? 0);
            const averageWeeklyComplaintRate =
              observations && row?.complaints_per_1000_restaurants != null
                ? Number(row.complaints_per_1000_restaurants) / observations
                : null;
            const criticalInspectionRate =
              row?.inspections_with_critical_per_100 == null
                ? null
                : Number(row.inspections_with_critical_per_100);
            const reliability = observations
              ? evidenceLabel(observations)
              : "Not enough data";
            const uncertain = confidenceIncludesZero(row?.confidence_interval);
            const tooltip = [
              feature.properties.boroname,
              `Complaints and later violations: ${details.label}`,
              `Direction: ${correlationDirection(correlation)}`,
              `Complaint rate: ${averageWeeklyComplaintRate == null ? "Not available" : `${averageWeeklyComplaintRate.toFixed(0)} per 1,000 restaurants`}`,
              `Inspections finding a critical violation: ${criticalInspectionRate == null ? "Not available" : `${criticalInspectionRate.toFixed(0)}%`}`,
              `Period: ${observations} weeks`,
              `Reliability: ${reliability}${uncertain ? "; confidence range includes no connection" : ""}`,
            ].join("\n");
            return (
              <path
                key={feature.properties.boroname}
                d={makePath(feature.geometry)}
                style={{ fill: details.color }}
                tabIndex={0}
                aria-label={tooltip}
                data-tooltip={tooltip}
              >
                <title>{tooltip}</title>
              </path>
            );
          })}
        </svg>
        <div className="relationship-color-key" aria-label="Map color guide">
          <span>
            <i className="map-weak" />
            Weak
          </span>
          <span>
            <i className="map-moderate" />
            Moderate
          </span>
          <span>
            <i className="map-strong" />
            Strong
          </span>
          <span>
            <i className="map-opposite" />
            Opposite direction
          </span>
        </div>
      </div>
      <ul className="map-legend relationship-map-list">
        {sortedRows.map((row) => {
          const details = relationshipDetails(
            row.correlation == null ? null : Number(row.correlation),
          );
          return (
            <li key={row.borough_name}>
              <span>
                <i style={{ background: details.color }} />
                {displayBorough(row.borough_name)}
              </span>
              <span className="relationship-list-result">
                <strong>{details.label}</strong>
                <small>{evidenceLabel(row.observations)}</small>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function polygons(geometry: Geometry): Position[][][] {
  return geometry.type === "Polygon"
    ? [geometry.coordinates as Position[][]]
    : (geometry.coordinates as Position[][][]);
}
function flatten(geometry: Geometry): Position[] {
  return polygons(geometry).flat(2) as Position[];
}
