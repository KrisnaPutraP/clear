export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/clear${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
    signal: init?.signal ?? AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item: { msg?: string }) => item.msg || "Invalid request")
              .join("; ")
          : `Request failed (${response.status}). Check that the CLEAR API is running.`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
