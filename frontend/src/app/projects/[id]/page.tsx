"use client";

import { useState, use, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, downloadPresentation } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";
import { apiErrorDetail, type GenerationProgress, type Presentation as Deck, type Project, type ProjectDocument } from "@/lib/types";
import { useDropzone, type FileRejection } from "react-dropzone";
import {
  FileText,
  UploadCloud,
  Presentation,
  Trash2,
  RefreshCw,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Clock,
  Download,
  Eye,
  ArrowLeft,
  Pencil,
  X
} from "lucide-react";

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const projectId = resolvedParams.id;
  const router = useRouter();
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<"documents" | "generate" | "presentations">("documents");

  // PPT Generation State
  const [prompt, setPrompt] = useState("");
  const [numSlides, setNumSlides] = useState(10);
  const [audience, setAudience] = useState("Senior Management");
  const [theme, setTheme] = useState("Professional");
  const [tone, setTone] = useState("Professional & Informative");
  const [language, setLanguage] = useState("English");
  // The deck whose generation is being tracked; its progress is polled by the query below
  const [activeDeckId, setActiveDeckId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [editing, setEditing] = useState<{ name: string; description: string } | null>(null);
  const [presentationToDelete, setPresentationToDelete] = useState<{ id: string; title: string } | null>(null);
  const [documentToDelete, setDocumentToDelete] = useState<{ id: string; filename: string } | null>(null);

  // Queries
  const { data: project } = useQuery<Project>({
    queryKey: ["project", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}`)).data,
  });

  const { data: documents = [], refetch: refetchDocs } = useQuery<ProjectDocument[]>({
    queryKey: ["documents", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/documents`)).data,
    // Ingestion runs in the background: keep polling until every document reaches a terminal status.
    refetchInterval: (query) => {
      const docs = query.state.data ?? [];
      return docs.some((d) => d.status !== "INDEXED" && d.status !== "FAILED") ? 2000 : false;
    },
  });

  const { data: presentations = [], refetch: refetchPresentations } = useQuery<Deck[]>({
    queryKey: ["presentations", projectId],
    queryFn: async () => (await api.get(`/projects/${projectId}/presentations`)).data,
  });

  // Document Upload Mutation
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post(`/projects/${projectId}/documents`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data;
    },
    onSuccess: () => {
      refetchDocs();
    },
  });

  const onDrop = (acceptedFiles: File[], rejections: FileRejection[]) => {
    setUploadErrors(rejections.map((r) => `${r.file.name}: unsupported file type`));
    acceptedFiles.forEach((file) =>
      uploadMutation.mutate(file, {
        onError: (err) =>
          setUploadErrors((prev) => [...prev, `${file.name}: ${apiErrorDetail(err, "upload failed")}`]),
      })
    );
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
    },
  });

  // Generate PPT Mutation
  const generateMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post<GenerationProgress>(`/projects/${projectId}/presentations/generate`, {
        prompt,
        num_slides: numSlides,
        audience,
        theme,
        tone,
        language,
      });
      return res.data;
    },
    onMutate: () => setStartError(null),
    onError: (err) => {
      setStartError(apiErrorDetail(err, "Could not start generation. Is the backend running?"));
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["progress", data.presentation_id], data);
      setActiveDeckId(data.presentation_id);
    },
  });

  // Progress polling stops by itself on COMPLETED/FAILED, and when the page unmounts
  const progressQuery = useQuery<GenerationProgress>({
    queryKey: ["progress", activeDeckId],
    queryFn: async () => (await api.get(`/presentations/${activeDeckId}/progress`)).data,
    enabled: activeDeckId !== null,
    refetchInterval: (query) =>
      ["COMPLETED", "FAILED"].includes(query.state.data?.status ?? "") ? false : 2000,
    retry: 2,
  });
  const progress = progressQuery.data;
  const isGenerating =
    generateMutation.isPending ||
    (activeDeckId !== null && !progressQuery.isError && !["COMPLETED", "FAILED"].includes(progress?.status ?? ""));
  const generationError =
    startError ??
    (progress?.status === "FAILED" ? progress.error_message || "Presentation generation failed." : null) ??
    (progressQuery.isError ? "Lost connection to the server while generating." : null);

  useEffect(() => {
    if (progress?.status === "COMPLETED" && activeDeckId) {
      queryClient.invalidateQueries({ queryKey: ["presentations", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/presentations/${activeDeckId}`);
    } else if (progress?.status === "FAILED") {
      queryClient.invalidateQueries({ queryKey: ["presentations", projectId] });
    }
  }, [progress?.status, activeDeckId, projectId, queryClient, router]);

  // Edit project name/description
  const updateProjectMutation = useMutation({
    mutationFn: async (body: { name: string; description: string }) =>
      (await api.patch<Project>(`/projects/${projectId}`, body)).data,
    onSuccess: (data) => {
      queryClient.setQueryData(["project", projectId], data);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setEditing(null);
    },
  });

  // Delete presentation
  const deletePresentationMutation = useMutation({
    mutationFn: async (presentationId: string) => await api.delete(`/presentations/${presentationId}`),
    onSuccess: (_data, presentationId) => {
      refetchPresentations();
      queryClient.removeQueries({ queryKey: ["presentation", presentationId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setPresentationToDelete(null);
    },
  });

  const closeDeletePresentationDialog = () => {
    setPresentationToDelete(null);
    deletePresentationMutation.reset();
  };

  // Delete document
  const deleteDocMutation = useMutation({
    mutationFn: async (docId: string) => await api.delete(`/documents/${docId}`),
    onSuccess: () => {
      refetchDocs();
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setDocumentToDelete(null);
    },
  });

  const closeDeleteDocumentDialog = () => {
    setDocumentToDelete(null);
    deleteDocMutation.reset();
  };

  // Retry ingestion of a failed document (the list then polls until it's INDEXED/FAILED again)
  const reindexMutation = useMutation({
    mutationFn: async (docId: string) => await api.post(`/documents/${docId}/reindex`),
    onSuccess: () => refetchDocs(),
  });

  const indexedCount = documents.filter((d) => d.status === "INDEXED").length;

  return (
    <div className="space-y-8 py-2">
      {/* Workspace Header */}
      <div className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 sm:p-8 rounded-2xl shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center space-x-2 text-emerald-700 dark:text-emerald-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Link href="/dashboard" className="hover:underline flex items-center space-x-1">
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Dashboard</span>
            </Link>
            <span>/</span>
            <span>{project?.name || "Workspace"}</span>
          </div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
              {project?.name}
            </h1>
            {project && (
              <button
                type="button"
                onClick={() => {
                  updateProjectMutation.reset();
                  setEditing({ name: project.name, description: project.description ?? "" });
                }}
                className="p-1.5 rounded-lg text-slate-400 dark:text-zinc-500 hover:text-emerald-700 dark:hover:text-emerald-400 hover:bg-stone-100 dark:hover:bg-zinc-900 transition"
                title="Edit project"
                aria-label="Edit project name and description"
              >
                <Pencil className="w-4 h-4" />
              </button>
            )}
          </div>
          <p className="text-slate-500 dark:text-zinc-400 text-sm mt-1">
            {project?.description || "Document RAG Knowledge Base Workspace"}
          </p>
        </div>

        {/* Tab Controls (Pill Bar) */}
        <div className="flex items-center bg-stone-200/70 dark:bg-zinc-950 p-1.5 rounded-full border border-stone-300/70 dark:border-zinc-800 self-start md:self-auto text-xs font-semibold">
          <button
            onClick={() => setActiveTab("documents")}
            className={`flex items-center space-x-2 px-4 py-2 rounded-full transition ${
              activeTab === "documents"
                ? "bg-[#055a44] text-white shadow-xs"
                : "text-slate-700 dark:text-zinc-300 hover:text-emerald-700 dark:hover:text-emerald-400"
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Documents ({documents.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("generate")}
            className={`flex items-center space-x-2 px-4 py-2 rounded-full transition ${
              activeTab === "generate"
                ? "bg-[#055a44] text-white shadow-xs"
                : "text-slate-700 dark:text-zinc-300 hover:text-emerald-700 dark:hover:text-emerald-400"
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Generate PPT</span>
          </button>

          <button
            onClick={() => setActiveTab("presentations")}
            className={`flex items-center space-x-2 px-4 py-2 rounded-full transition ${
              activeTab === "presentations"
                ? "bg-[#055a44] text-white shadow-xs"
                : "text-slate-700 dark:text-zinc-300 hover:text-emerald-700 dark:hover:text-emerald-400"
            }`}
          >
            <Presentation className="w-4 h-4" />
            <span>Decks ({presentations.length})</span>
          </button>
        </div>
      </div>

      {/* TAB 1: DOCUMENTS */}
      {activeTab === "documents" && (
        <div className="space-y-6">
          {/* Upload Dropzone Box */}
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-2xl p-8 sm:p-12 text-center cursor-pointer transition ${
              isDragActive
                ? "border-emerald-600 bg-emerald-50 dark:bg-emerald-950/30"
                : "border-stone-300 dark:border-zinc-800 bg-white/60 dark:bg-[#0d120f]/60 hover:border-emerald-500"
            }`}
          >
            <input {...getInputProps()} />
            <UploadCloud className="w-12 h-12 text-emerald-700 dark:text-emerald-400 mx-auto mb-4" />
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Drag & Drop Documents Here</h3>
            <p className="text-slate-500 dark:text-zinc-400 text-xs sm:text-sm mt-1 max-w-md mx-auto">
              Supports PDF, DOCX, XLSX, CSV, PPTX, TXT, and Markdown files. Full factual chunking with vector indexing.
            </p>
            <button
              type="button"
              className="mt-6 px-5 py-2.5 bg-stone-200/80 dark:bg-zinc-800 hover:bg-stone-300 dark:hover:bg-zinc-700 text-slate-800 dark:text-zinc-200 text-xs font-semibold rounded-full border border-stone-300 dark:border-zinc-700 transition"
            >
              Browse Files
            </button>
          </div>

          {uploadErrors.length > 0 && (
            <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/50 p-4 rounded-xl flex items-start gap-2 text-xs text-red-700 dark:text-red-300">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <ul className="flex-1 space-y-1">
                {uploadErrors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => setUploadErrors([])}
                className="text-red-500 hover:text-red-700 dark:hover:text-red-200"
                aria-label="Dismiss upload errors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Ingested Documents List */}
          <div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Ingested Document Knowledge</h3>
            {documents.length === 0 ? (
              <div className="text-center py-8 text-slate-500 dark:text-zinc-500 text-sm bg-white/50 dark:bg-[#0d120f]/50 rounded-xl border border-stone-200 dark:border-zinc-800">
                No documents uploaded yet. Upload files above to build your RAG index.
              </div>
            ) : (
              <div className="space-y-3">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-4 rounded-xl flex items-center justify-between hover:border-emerald-500/50 transition shadow-xs"
                  >
                    <div className="flex items-center space-x-4">
                      <div className="p-3 bg-emerald-100/70 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 rounded-xl border border-emerald-200 dark:border-emerald-900/40">
                        <FileText className="w-5 h-5" />
                      </div>
                      <div>
                        <h4 className="font-semibold text-slate-900 dark:text-white text-sm">{doc.filename}</h4>
                        <div className="flex items-center space-x-3 text-xs text-slate-500 dark:text-zinc-400 font-mono mt-1">
                          <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                          <span>•</span>
                          <span className="uppercase">{doc.file_type}</span>
                        </div>
                        {doc.status === "FAILED" && doc.error_message && (
                          <p className="text-xs text-red-600 dark:text-red-400 mt-1 line-clamp-2" title={doc.error_message}>
                            {doc.error_message}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center space-x-4">
                      {/* Ingestion Status Badge */}
                      <span className={`text-xs px-3 py-1 rounded-full font-semibold flex items-center space-x-1.5 ${
                        doc.status === "INDEXED"
                          ? "bg-emerald-100/80 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 border border-emerald-300/80 dark:border-emerald-800"
                          : doc.status === "FAILED"
                          ? "bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border border-red-300 dark:border-red-800"
                          : "bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800"
                      }`}>
                        {doc.status === "INDEXED" && <CheckCircle2 className="w-3.5 h-3.5" />}
                        {doc.status === "FAILED" && <AlertCircle className="w-3.5 h-3.5" />}
                        {doc.status !== "INDEXED" && doc.status !== "FAILED" && <Clock className="w-3.5 h-3.5 animate-spin" />}
                        <span>{doc.status}</span>
                      </span>

                      {doc.status === "FAILED" && (
                        <button
                          onClick={() => reindexMutation.mutate(doc.id)}
                          disabled={reindexMutation.isPending && reindexMutation.variables === doc.id}
                          className="flex items-center space-x-1 px-2.5 py-1 text-xs font-semibold rounded-lg border border-stone-300 dark:border-zinc-700 text-slate-700 dark:text-zinc-300 hover:border-emerald-500 hover:text-emerald-700 dark:hover:text-emerald-400 transition disabled:opacity-50"
                          title="Retry indexing this document"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                          <span>Retry</span>
                        </button>
                      )}

                      <button
                        onClick={() => setDocumentToDelete({ id: doc.id, filename: doc.filename })}
                        className="text-slate-400 hover:text-red-500 p-2 transition"
                        title="Delete Document"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: GENERATE PPT */}
      {activeTab === "generate" && (
        <div className="max-w-3xl mx-auto bg-white/90 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 sm:p-8 rounded-2xl shadow-xl space-y-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-emerald-700 dark:text-emerald-400" />
              <span>Prompt Presentation Studio</span>
            </h2>
            <p className="text-slate-500 dark:text-zinc-400 text-xs sm:text-sm mt-1">
              Specify your presentation topic. The RAG agent will query ingested documents for factual ground truth to outline and render your slides.
            </p>
          </div>

          <div className="space-y-5">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-2">
                What presentation would you like to create?
              </label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={4}
                placeholder="e.g. Create a 10-slide presentation explaining our Q3 financial performance, key revenue drivers, regional challenges, and strategic recommendations."
                className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl p-4 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Target Slide Count</label>
                <select
                  value={numSlides}
                  onChange={(e) => setNumSlides(Number(e.target.value))}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-lg px-3 py-2 text-slate-900 dark:text-white text-xs font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value={5}>5 Slides (Brief)</option>
                  <option value={8}>8 Slides (Standard)</option>
                  <option value={10}>10 Slides (Comprehensive)</option>
                  <option value={15}>15 Slides (Detailed)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Target Audience</label>
                <select
                  value={audience}
                  onChange={(e) => setAudience(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-lg px-3 py-2 text-slate-900 dark:text-white text-xs font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="Senior Management">Executive Leadership</option>
                  <option value="General Public">General Audience</option>
                  <option value="Technical Team">Technical Engineers</option>
                  <option value="Investors">Investors / Board</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Visual Theme</label>
                <select
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-lg px-3 py-2 text-slate-900 dark:text-white text-xs font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="Professional">Professional (Emerald Slate)</option>
                  <option value="Minimal">Minimal (Clean Light)</option>
                  <option value="Dark">Dark Obsidian</option>
                  <option value="Corporate">Corporate Blue</option>
                  <option value="Modern">Modern</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Tone</label>
                <select
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-lg px-3 py-2 text-slate-900 dark:text-white text-xs font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="Professional & Informative">Professional &amp; Informative</option>
                  <option value="Concise & Executive">Concise &amp; Executive</option>
                  <option value="Persuasive">Persuasive</option>
                  <option value="Neutral & Academic">Neutral &amp; Academic</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">Slide Language</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-lg px-3 py-2 text-slate-900 dark:text-white text-xs font-medium focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  {["English", "Spanish", "French", "German", "Portuguese", "Italian", "Dutch", "Hindi", "Japanese", "Chinese"].map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Progress Status Bar during generation */}
            {isGenerating && progress && (
              <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800/50 p-4 rounded-xl space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                    <Clock className="w-4 h-4 animate-spin text-emerald-600 dark:text-emerald-400" />
                    {progress.current_step}
                  </span>
                  <span className="font-mono text-emerald-700 dark:text-emerald-400 font-bold">{progress.progress}%</span>
                </div>
                <div className="w-full bg-stone-200 dark:bg-zinc-900 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-emerald-600 dark:bg-emerald-400 h-2 transition-all duration-300 rounded-full"
                    style={{ width: `${progress.progress}%` }}
                  />
                </div>
              </div>
            )}

            {generationError && (
              <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/50 p-4 rounded-xl flex items-start gap-2 text-xs text-red-700 dark:text-red-300">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span><span className="font-semibold">Generation failed:</span> {generationError}</span>
              </div>
            )}

            {indexedCount === 0 && (
              <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/50 p-4 rounded-xl flex items-start gap-2 text-xs text-amber-800 dark:text-amber-300">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Slides are built only from your documents. Upload at least one document in the Documents tab and wait
                  until it shows <span className="font-semibold">INDEXED</span>.
                </span>
              </div>
            )}

            <button
              onClick={() => generateMutation.mutate()}
              disabled={!prompt.trim() || isGenerating || indexedCount === 0}
              className="w-full py-3.5 bg-[#055a44] hover:bg-[#044836] text-white font-bold rounded-xl shadow-md transition disabled:opacity-50 flex items-center justify-center space-x-2 text-sm"
            >
              <Sparkles className="w-5 h-5" />
              <span>{isGenerating ? "Generating Presentation..." : "Generate Presentation Deck"}</span>
            </button>
          </div>
        </div>
      )}

      {/* TAB 3: PRESENTATIONS */}
      {activeTab === "presentations" && (
        <div className="space-y-6">
          <h3 className="text-lg font-bold text-slate-900 dark:text-white">Generated PowerPoint Decks</h3>
          {presentations.length === 0 ? (
            <div className="text-center py-12 text-slate-500 dark:text-zinc-500 text-sm bg-white/50 dark:bg-[#0d120f]/50 rounded-xl border border-stone-200 dark:border-zinc-800">
              No presentations generated yet for this workspace.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {presentations.map((pres) => (
                <div
                  key={pres.id}
                  className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-6 rounded-2xl flex flex-col justify-between hover:border-emerald-500/50 transition shadow-xs"
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <span className="p-2.5 bg-amber-100/70 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 rounded-xl border border-amber-200 dark:border-amber-900/40">
                        <Presentation className="w-5 h-5" />
                      </span>
                      <span className="text-xs text-slate-400 dark:text-zinc-500 font-mono">
                        {new Date(pres.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <h4 className="font-bold text-slate-900 dark:text-white text-lg line-clamp-1">{pres.title}</h4>
                    <p className="text-slate-500 dark:text-zinc-400 text-xs sm:text-sm mt-1 line-clamp-2">{pres.prompt}</p>
                  </div>

                  <div className="mt-6 pt-4 border-t border-stone-200/60 dark:border-zinc-800 flex items-center justify-between">
                    <span className="text-xs text-slate-400 dark:text-zinc-500 font-medium">Theme: {pres.theme}</span>

                    <div className="flex items-center space-x-2">
                      {/* The backend rejects deleting a deck that is still generating (409) */}
                      <button
                        type="button"
                        onClick={() => setPresentationToDelete({ id: pres.id, title: pres.title })}
                        disabled={pres.status === "PENDING" || pres.status === "GENERATING"}
                        className="p-1.5 rounded-lg text-slate-400 dark:text-zinc-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition disabled:opacity-40 disabled:pointer-events-none"
                        title={pres.status === "PENDING" || pres.status === "GENERATING" ? "Can't delete while generating" : "Delete presentation"}
                        aria-label={`Delete presentation ${pres.title}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>

                      <Link
                        href={`/presentations/${pres.id}`}
                        className="px-3 py-1.5 bg-stone-200/80 dark:bg-zinc-800 hover:bg-stone-300 dark:hover:bg-zinc-700 text-slate-800 dark:text-zinc-200 text-xs font-medium rounded-lg transition flex items-center space-x-1"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        <span>Preview</span>
                      </Link>

                      {pres.pptx_path ? (
                        <button
                          onClick={() => downloadPresentation(pres.id, pres.title)}
                          className="px-3 py-1.5 bg-[#055a44] hover:bg-[#044836] text-white text-xs font-semibold rounded-lg transition flex items-center space-x-1 shadow-xs"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>PPTX</span>
                        </button>
                      ) : (
                        <span className={`text-xs px-2.5 py-1 rounded-full font-semibold border ${
                          pres.status === "FAILED"
                            ? "bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-300 border-red-300 dark:border-red-800"
                            : "bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-800"
                        }`}>
                          {pres.status}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Edit Project Modal */}
      {editing && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 max-w-md w-full p-6 rounded-2xl shadow-2xl space-y-4">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white">Edit Project</h3>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                updateProjectMutation.mutate(editing);
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">
                  Project Name
                </label>
                <input
                  type="text"
                  required
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl px-3.5 py-2.5 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-zinc-300 mb-1">
                  Description (Optional)
                </label>
                <textarea
                  rows={3}
                  value={editing.description}
                  onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                  className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-xl px-3.5 py-2.5 text-slate-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              {updateProjectMutation.isError && (
                <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/50 p-3 rounded-xl text-xs text-red-700 dark:text-red-300">
                  {apiErrorDetail(updateProjectMutation.error, "Could not save the project. Please try again.")}
                </div>
              )}
              <div className="flex items-center justify-end space-x-3 pt-4 border-t border-stone-200 dark:border-zinc-800">
                <button
                  type="button"
                  onClick={() => setEditing(null)}
                  className="px-4 py-2 text-slate-500 dark:text-zinc-400 hover:text-slate-800 dark:hover:text-zinc-200 text-sm font-medium transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updateProjectMutation.isPending || !editing.name.trim()}
                  className="px-5 py-2 bg-[#055a44] hover:bg-[#044836] text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 shadow-xs"
                >
                  {updateProjectMutation.isPending ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Document Confirmation */}
      <ConfirmDialog
        open={documentToDelete !== null}
        title="Delete this document?"
        message={
          <>
            Do you really want to delete{" "}
            <span className="font-semibold text-slate-800 dark:text-zinc-200">{documentToDelete?.filename}</span>?
            It will no longer be used or cited in new presentations. Existing decks are not changed. This can&apos;t be undone.
          </>
        }
        confirmLabel="Delete Document"
        isPending={deleteDocMutation.isPending}
        error={deleteDocMutation.isError ? "Could not delete the document. Please try again." : null}
        onConfirm={() => documentToDelete && deleteDocMutation.mutate(documentToDelete.id)}
        onCancel={closeDeleteDocumentDialog}
      />

      {/* Delete Presentation Confirmation */}
      <ConfirmDialog
        open={presentationToDelete !== null}
        title="Delete this presentation?"
        message={
          <>
            Do you really want to delete{" "}
            <span className="font-semibold text-slate-800 dark:text-zinc-200">{presentationToDelete?.title}</span>?
            Its slides and .pptx file will be permanently removed. Your documents are not affected. This can&apos;t be undone.
          </>
        }
        confirmLabel="Delete Presentation"
        isPending={deletePresentationMutation.isPending}
        error={
          deletePresentationMutation.isError
            ? apiErrorDetail(deletePresentationMutation.error, "Could not delete the presentation. Please try again.")
            : null
        }
        onConfirm={() => presentationToDelete && deletePresentationMutation.mutate(presentationToDelete.id)}
        onCancel={closeDeletePresentationDialog}
      />
    </div>
  );
}
