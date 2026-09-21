"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { FolderPlus, Folder, FileText, Presentation, Plus, ArrowRight, Sparkles } from "lucide-react";

interface Project {
  id: string;
  name: string;
  description: string;
  document_count: number;
  presentation_count: number;
  created_at: string;
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ["projects"],
    queryFn: async () => {
      const res = await api.get("/projects");
      return res.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post("/projects", { name, description });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setIsModalOpen(false);
      setName("");
      setDescription("");
    },
  });

  return (
    <div className="space-y-8 py-2">
      {/* Dashboard Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 sm:p-8 rounded-2xl shadow-xs">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight flex items-center gap-2">
            <span>Workspace Dashboard</span>
            <Sparkles className="w-6 h-6 text-emerald-700 dark:text-emerald-400" />
          </h1>
          <p className="text-slate-500 dark:text-zinc-400 text-sm mt-1">
            Manage your document knowledge bases and generate AI PowerPoint presentations.
          </p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="inline-flex items-center space-x-2 bg-[#055a44] hover:bg-[#044836] text-white font-semibold px-5 py-2.5 rounded-xl transition shadow-xs text-sm"
        >
          <Plus className="w-5 h-5" />
          <span>New Project Workspace</span>
        </button>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        <div className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 rounded-2xl shadow-xs flex items-center space-x-4">
          <div className="p-3 bg-emerald-100/70 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 rounded-xl border border-emerald-200 dark:border-emerald-900/40">
            <Folder className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs text-slate-500 dark:text-zinc-400 font-semibold uppercase tracking-wider">Total Projects</p>
            <p className="text-2xl font-extrabold text-slate-900 dark:text-white mt-0.5">{projects.length}</p>
          </div>
        </div>

        <div className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 rounded-2xl shadow-xs flex items-center space-x-4">
          <div className="p-3 bg-emerald-100/70 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 rounded-xl border border-emerald-200 dark:border-emerald-900/40">
            <FileText className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs text-slate-500 dark:text-zinc-400 font-semibold uppercase tracking-wider">Indexed Documents</p>
            <p className="text-2xl font-extrabold text-slate-900 dark:text-white mt-0.5">
              {projects.reduce((acc, p) => acc + p.document_count, 0)}
            </p>
          </div>
        </div>

        <div className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 rounded-2xl shadow-xs flex items-center space-x-4">
          <div className="p-3 bg-amber-100/70 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 rounded-xl border border-amber-200 dark:border-amber-900/40">
            <Presentation className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs text-slate-500 dark:text-zinc-400 font-semibold uppercase tracking-wider">Generated Decks</p>
            <p className="text-2xl font-extrabold text-slate-900 dark:text-white mt-0.5">
              {projects.reduce((acc, p) => acc + p.presentation_count, 0)}
            </p>
          </div>
        </div>
      </div>

      {/* Projects List */}
      <div>
        <h2 className="text-xl font-extrabold text-slate-900 dark:text-white mb-4">Your Project Workspaces</h2>
        {isLoading ? (
          <div className="text-center py-12 text-slate-500 dark:text-zinc-500 font-mono text-sm">
            Loading workspaces...
          </div>
        ) : projects.length === 0 ? (
          <div className="bg-white/60 dark:bg-[#0d120f]/60 border-2 border-dashed border-stone-300 dark:border-zinc-800 rounded-2xl p-12 text-center">
            <FolderPlus className="w-12 h-12 text-emerald-600 dark:text-emerald-500 mx-auto mb-3" />
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">No projects created yet</h3>
            <p className="text-slate-500 dark:text-zinc-400 text-sm mt-1 max-w-sm mx-auto">
              Create your first workspace, upload PDFs/DOCX/Spreadsheets, and start generating presentations.
            </p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="mt-6 inline-flex items-center space-x-2 bg-[#055a44] hover:bg-[#044836] text-white font-semibold px-4 py-2 rounded-xl transition text-xs shadow-xs"
            >
              <Plus className="w-4 h-4" />
              <span>Create First Project</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects.map((project) => (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                className="group bg-white/80 dark:bg-[#0d120f] hover:bg-emerald-50/30 dark:hover:bg-zinc-900/60 border border-stone-200/80 dark:border-zinc-800 hover:border-emerald-600/50 dark:hover:border-emerald-500/50 p-6 rounded-2xl transition duration-200 shadow-xs hover:shadow-md flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="p-2.5 bg-emerald-100/70 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 rounded-xl group-hover:scale-105 transition border border-emerald-200 dark:border-emerald-900/40">
                      <Folder className="w-5 h-5" />
                    </span>
                    <span className="text-xs text-slate-400 dark:text-zinc-500 font-mono">
                      {new Date(project.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white group-hover:text-emerald-700 dark:group-hover:text-emerald-400 transition">
                    {project.name}
                  </h3>
                  <p className="text-slate-500 dark:text-zinc-400 text-xs sm:text-sm mt-1 line-clamp-2">
                    {project.description || "No description provided."}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t border-stone-200/60 dark:border-zinc-800/80 flex items-center justify-between text-xs text-slate-500 dark:text-zinc-400">
                  <div className="flex items-center space-x-3 font-mono text-[11px]">
                    <span className="bg-stone-100 dark:bg-zinc-800 px-2 py-0.5 rounded text-slate-700 dark:text-zinc-300">
                      {project.document_count} docs
                    </span>
                    <span>•</span>
                    <span className="bg-stone-100 dark:bg-zinc-800 px-2 py-0.5 rounded text-slate-700 dark:text-zinc-300">
                      {project.presentation_count} decks
                    </span>
                  </div>
                  <ArrowRight className="w-4 h-4 text-emerald-600 dark:text-emerald-400 group-hover:translate-x-1 transition" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* New Project Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 max-w-md w-full p-6 rounded-2xl shadow-2xl space-y-4">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white">Create New Project</h3>
            <p className="text-slate-500 dark:text-zinc-400 text-xs">
              A project contains your uploaded documents and generated PowerPoint presentations.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate();
              }}
              className="space-y-4 pt-2"
            >
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">
                  Project Name
                </label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Q3 Financial Revenue Analysis"
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl px-3.5 py-2.5 text-slate-900 dark:text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">
                  Description (Optional)
                </label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  placeholder="Briefly describe the target domain or goal of this workspace..."
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl px-3.5 py-2.5 text-slate-900 dark:text-white placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="flex items-center justify-end space-x-3 pt-4 border-t border-stone-200 dark:border-zinc-800">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-slate-500 dark:text-zinc-400 hover:text-slate-800 text-sm font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-5 py-2 bg-[#055a44] hover:bg-[#044836] text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 shadow-xs"
                >
                  {createMutation.isPending ? "Creating..." : "Create Project"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
