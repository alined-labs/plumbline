/** Where the browser finds the API. The static export is built once, so this is public. */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export function apiUrl(path: `/api/${string}`): string {
  return `${API_BASE_URL}${path}`;
}
