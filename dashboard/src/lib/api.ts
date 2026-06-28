import { getSession } from "next-auth/react";

/*
 * API utility functions for the dashboard.
 * Provides a helper to send a warning or request log entry
 * to the configured external channel (e.g., Discord or Slack).
 */

export async function apiFetch(url: string, options: RequestInit = {}) {
  const session = await getSession();
  const headers = new Headers(options.headers || {});
  
  if ((session as any)?.accessToken) {
    headers.set("Authorization", `Bearer ${(session as any).accessToken}`);
  }
  
  return fetch(url, { ...options, headers });
}

/**
 * Sends a log entry to the configured channel via the backend endpoint.
 *
 * @param guildId - The ID of the guild (server) the log belongs to. Use "0" for global.
 * @param type - Either "warning" or "request" (the singular form used in the API path).
 * @param logId - The ID of the specific log entry to send.
 */
export async function sendLogToChannel(
  guildId: string,
  type: "warning" | "request",
  logId: string
): Promise<void> {
  const endpoint = `/api/guilds/${guildId}/${type}s/${logId}/send`;
  const response = await apiFetch(endpoint, { method: "POST" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to send ${type} ${logId}: ${response.status} ${text}`);
  }
}
