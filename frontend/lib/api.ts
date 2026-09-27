import type { ApiHealth } from "@/types/health";

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function fetchApi<T>(
  path: string,
  params: Record<string, string | number | boolean | null | undefined> = {},
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(`${apiBaseUrl}/api/v1${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "")
      url.searchParams.set(key, String(value));
  });
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const message =
      response.status === 422
        ? "Please check the selected filters."
        : "Safety data is temporarily unavailable.";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function fetchApiHealth(): Promise<ApiHealth> {
  return fetchApi<ApiHealth>("/health");
}
