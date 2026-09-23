"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { useTheme } from "@/components/Providers";
import {
  Presentation,
  FolderKanban,
  LogOut,
  User,
  Sun,
  Moon
} from "lucide-react";

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, token, setUser, logout } = useAuthStore();

  // Only the token survives a page reload, so re-fetch the user it belongs to.
  // An expired or invalid token (401) is cleared instead of leaving a half-logged-in state.
  useQuery({
    queryKey: ["me", token],
    queryFn: async () => {
      try {
        const me = (await api.get("/auth/me")).data;
        setUser(me);
        return me;
      } catch (err) {
        if (isAxiosError(err) && err.response?.status === 401) logout();
        throw err;
      }
    },
    enabled: !!token && !user,
    retry: false,
  });
  const { theme, toggleTheme } = useTheme();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <nav className="bg-white/80 dark:bg-[#0d120f]/80 backdrop-blur-md border-b border-stone-200/80 dark:border-zinc-800 text-slate-900 dark:text-slate-100 sticky top-0 z-40 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo */}
          <Link href="/dashboard" className="flex items-center space-x-3 text-emerald-700 dark:text-emerald-400 font-extrabold text-xl hover:opacity-90 transition">
            <Presentation className="w-7 h-7" />
            <span>Clarion</span>
          </Link>

          {/* Nav Items & Controls */}
          <div className="flex items-center space-x-6">
            <Link
              href="/dashboard"
              className={`flex items-center space-x-1 hover:text-emerald-700 dark:hover:text-emerald-400 text-sm font-semibold transition ${
                pathname === "/dashboard" ? "text-emerald-700 dark:text-emerald-400" : "text-slate-600 dark:text-zinc-300"
              }`}
            >
              <FolderKanban className="w-4 h-4" />
              <span>Projects</span>
            </Link>

            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-xl border border-stone-200 dark:border-zinc-800 bg-stone-100/70 dark:bg-zinc-900 text-slate-700 dark:text-zinc-300 hover:bg-stone-200 dark:hover:bg-zinc-800 transition"
              title="Toggle theme mode"
            >
              {theme === "light" ? (
                <Moon className="w-4 h-4 text-slate-700" />
              ) : (
                <Sun className="w-4 h-4 text-amber-400" />
              )}
            </button>

            {/* Auth Actions */}
            {user ? (
              <div className="flex items-center space-x-4">
                <span className="text-xs bg-stone-100 dark:bg-zinc-800 border border-stone-200 dark:border-zinc-700 px-3 py-1.5 rounded-full flex items-center space-x-1.5 text-slate-700 dark:text-zinc-300 font-mono">
                  <User className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                  <span>{user.email}</span>
                </span>
                <button
                  onClick={handleLogout}
                  className="flex items-center space-x-1 text-slate-600 dark:text-zinc-400 hover:text-red-500 text-sm font-medium transition"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Logout</span>
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="bg-[#055a44] hover:bg-[#044836] text-white text-sm font-semibold px-4 py-2 rounded-xl transition shadow-xs"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
