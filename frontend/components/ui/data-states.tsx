export function LoadingState({
  label = "Loading safety data",
}: {
  label?: string;
}) {
  return (
    <div className="state-panel" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{label}…</p>
    </div>
  );
}

export function EmptyState({
  title = "No results",
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <div className="state-panel">
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  );
}

export function ErrorState({
  message = "Safety data is temporarily unavailable. Please try again shortly.",
  retry,
}: {
  message?: string;
  retry?: () => void;
}) {
  return (
    <div className="state-panel error-panel" role="alert">
      <h3>We could not load this section</h3>
      <p>{message}</p>
      {retry && (
        <button className="button secondary" type="button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function LoadingCards({ count = 4 }: { count?: number }) {
  return (
    <div className="card-grid" aria-label="Loading">
      <span className="sr-only">Loading</span>
      {Array.from({ length: count }, (_, index) => (
        <div className="skeleton-card" key={index} aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      ))}
    </div>
  );
}
