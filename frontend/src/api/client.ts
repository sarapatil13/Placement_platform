import axios, { AxiosError } from "axios";
import type { AccessToken, TokenPair, WhoAmI } from "./types";

const ACCESS_KEY = "pp.access";
const USER_KEY = "pp.user";

// The refresh token is deliberately NOT stored in JS-accessible storage: it
// lives in an httpOnly, SameSite=Strict cookie set by the server on /api/v1/auth.
// This keeps the long-lived credential out of reach of XSS while the accessory
// access token (short-lived) stays in localStorage as before.

const BASE_URL = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export const api = axios.create({ baseURL: `${BASE_URL}/api/v1`, timeout: 30000 });

export interface ApiErrorPayload {
  detail?: string | { msg: string }[] | { message?: string } | unknown;
}

export class ApiClientError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getStoredUser(): WhoAmI | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as WhoAmI;
  } catch {
    return null;
  }
}

export function storeSession(pair: AccessToken | TokenPair): void {
  localStorage.setItem(ACCESS_KEY, pair.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(pair.user));
}

export function clearSession(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(USER_KEY);
}

export function extractErrorMessage(err: unknown): string {
  if (err instanceof ApiClientError) return err.message;
  if (axios.isAxiosError(err)) {
    const data = (err.response?.data ?? {}) as ApiErrorPayload;
    const detail = (data as { detail?: unknown }).detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (typeof d === "object" && d !== null ? (d as { msg?: string }).msg ?? "" : ""))
        .filter(Boolean)
        .join("; ");
    }
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null) {
      const m = (detail as { message?: string }).message;
      if (m) return m;
    }
    return err.message;
  }
  return err instanceof Error ? err.message : "Unknown error";
}

let refreshInFlight: Promise<string | null> | null = null;

/** Silent refresh via the server-set httpOnly refresh cookie. */
async function tryRefresh(): Promise<string | null> {
  try {
    const { data } = await axios.post<TokenPair>(
      `${BASE_URL}/api/v1/auth/refresh`,
      {},
      {
        timeout: 15000,
        withCredentials: true,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      },
    );
    storeSession(data);
    return data.access_token;
  } catch {
    clearSession();
    return null;
  }
}

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      | (import("axios").InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined;
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      refreshInFlight = refreshInFlight ?? tryRefresh();
      const token = await refreshInFlight;
      refreshInFlight = null;
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api.request(original);
      }
    }
    if (error.response?.status === 401) {
      clearSession();
    }
    return Promise.reject(error);
  },
);

/** Parse a FastAPI error body into a readable message and throw ApiClientError. */
export async function httpError(err: unknown): Promise<ApiClientError> {
  if (err instanceof ApiClientError) return err;
  if (axios.isAxiosError(err)) {
    const data = (err.response?.data ?? {}) as ApiErrorPayload;
    const detail = (data as { detail?: unknown }).detail;
    let msg: string | null = null;
    if (Array.isArray(detail)) {
      msg = detail
        .map((d) => (typeof d === "object" && d !== null ? (d as { msg?: string }).msg ?? "" : ""))
        .filter(Boolean)
        .join("; ");
    } else if (typeof detail === "string") {
      msg = detail;
    } else if (typeof detail === "object" && detail !== null) {
      msg = (detail as { message?: string }).message ?? null;
    }
    if (!msg) msg = err.message;
    return new ApiClientError(msg, err.response?.status);
  }
  return new ApiClientError(err instanceof Error ? err.message : "Unknown error");
}