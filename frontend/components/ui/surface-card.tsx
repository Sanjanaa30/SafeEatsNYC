import type { ReactNode } from "react";

export function SurfaceCard({
  title,
  children,
  interactive = false,
}: {
  title: string;
  children: ReactNode;
  interactive?: boolean;
}) {
  return (
    <section
      className={`surface-card reveal ${interactive ? "interactive" : ""}`}
    >
      <h2>{title}</h2>
      {children}
    </section>
  );
}
