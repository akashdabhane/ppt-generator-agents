import axios from "axios";
import { useAuthStore } from "@/lib/store";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Downloads a generated deck through the authenticated client (a plain link can't send the Bearer token)
export async function downloadPresentation(presentationId: string, title?: string) {
  const res = await api.get(`/presentations/${presentationId}/download`, { responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${(title || "presentation").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "_") || "presentation"}.pptx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// Interceptor to attach Auth bearer token
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Missing/expired token: clear the session and send the user to sign in (the login form handles its own errors)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isAuthRequest = String(error.config?.url || "").startsWith("/auth/");
    if (typeof window !== "undefined" && error.response?.status === 401 && !isAuthRequest) {
      useAuthStore.getState().logout();
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/register") {
        // Outside React there is no router; a full reload to the login page also clears every cached query
        window.location.assign(new URL("/login", window.location.origin));
      }
    }
    return Promise.reject(error);
  }
);
