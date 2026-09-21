"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { Presentation, Lock, Mail, AlertCircle } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((state) => state.setAuth);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await api.post("/auth/login", { email, password });
      setAuth(res.data.user, res.data.access_token);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Invalid email or password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[75vh] py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white/90 dark:bg-[#0d120f] p-8 rounded-2xl border border-stone-200 dark:border-zinc-800 shadow-xl">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-emerald-100/70 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-900/40 mb-4">
            <Presentation className="w-7 h-7" />
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white">Sign in to AI SlideRAG</h2>
          <p className="mt-2 text-xs sm:text-sm text-slate-500 dark:text-zinc-400">Generate presentations directly from your knowledge base</p>
        </div>

        {error && (
          <div className="bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900/50 rounded-xl p-4 flex items-center space-x-3 text-red-700 dark:text-red-400 text-xs">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Email Address</label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400 dark:text-zinc-500" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl pl-10 pr-4 py-2.5 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-xs sm:text-sm"
                  placeholder="name@company.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 absolute left-3.5 top-3.5 text-slate-400 dark:text-zinc-500" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl pl-10 pr-4 py-2.5 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-xs sm:text-sm"
                  placeholder="••••••••"
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 px-4 bg-[#055a44] hover:bg-[#044836] text-white font-semibold rounded-xl shadow-xs transition disabled:opacity-50 text-xs sm:text-sm"
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="text-center text-xs text-slate-500 dark:text-zinc-400 mt-4">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-emerald-700 dark:text-emerald-400 hover:underline font-bold">
            Create account
          </Link>
        </p>
      </div>
    </div>
  );
}
