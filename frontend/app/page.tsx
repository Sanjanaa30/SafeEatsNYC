import Link from "next/link";

import { ApiStatus } from "@/components/api-status";
import { PageHeading } from "@/components/ui/page-heading";
import { SurfaceCard } from "@/components/ui/surface-card";

const routes = [
  ["Overview", "/overview"],
  ["Correlation", "/correlation"],
  ["Restaurant Finder", "/finder"],
  ["Predictive Risk", "/risk"],
];

export default function HomePage() {
  return (
    <main id="main-content" className="shell page-shell">
      <PageHeading
        eyebrow="Restaurant safety intelligence"
        title="Understand where New York eats safely."
        description="Explore current inspection grades, 311 patterns, restaurant history, and carefully framed predictive risk across New York City."
      />
      <div className="route-grid" aria-label="Dashboard sections">
        {routes.map(([label, path], index) => (
          <Link
            className="route-card reveal"
            style={{ animationDelay: `${index * 70}ms` }}
            key={path}
            href={path}
          >
            <span className="route-number">0{index + 1}</span>
            <h2>{label}</h2>
            <span className="route-action">
              Explore section <span aria-hidden="true">→</span>
            </span>
          </Link>
        ))}
      </div>
      <SurfaceCard title="Built on verified data">
        <p>
          Daily Bronze ingestion flows through cleaned Silver data and tested
          Gold warehouse models before reaching this website.
        </p>
        <ApiStatus />
      </SurfaceCard>
    </main>
  );
}
