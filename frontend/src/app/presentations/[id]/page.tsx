"use client";

import { useState, use } from "react";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, downloadPresentation } from "@/lib/api";
import { apiErrorDetail, type Presentation as Deck } from "@/lib/types";
import {
  Download,
  ArrowLeft,
  RefreshCw,
  FileText,
  ChevronLeft,
  ChevronRight,
  BarChart3,
  CheckCircle2
} from "lucide-react";

export default function PresentationPreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const presentationId = resolvedParams.id;

  const [activeSlideIndex, setActiveSlideIndex] = useState(0);
  const [regenPrompt, setRegenPrompt] = useState("");
  const [isRegenModalOpen, setIsRegenModalOpen] = useState(false);

  const { data: presentation, refetch } = useQuery<Deck>({
    queryKey: ["presentation", presentationId],
    queryFn: async () => (await api.get(`/presentations/${presentationId}`)).data,
  });

  const slides = presentation?.slides || [];
  const currentSlide = slides[activeSlideIndex];

  // Single Slide Regenerate Mutation
  const regenMutation = useMutation({
    mutationFn: async () => {
      if (!currentSlide) return;
      const res = await api.post(
        `/presentations/${presentationId}/slides/${currentSlide.slide_number}/regenerate`,
        { instructions: regenPrompt }
      );
      return res.data;
    },
    onSuccess: () => {
      refetch();
      setIsRegenModalOpen(false);
      setRegenPrompt("");
    },
  });

  const regenError = regenMutation.isError
    ? apiErrorDetail(regenMutation.error, "Could not regenerate this slide. Please try again.")
    : null;

  const closeRegenModal = () => {
    setIsRegenModalOpen(false);
    regenMutation.reset();
  };

  return (
    <div className="space-y-6 py-2">
      {/* Top Action Header Bar */}
      <div className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-4 sm:p-6 rounded-2xl shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <Link
            href={`/projects/${presentation?.project_id}`}
            className="p-2 bg-stone-200/80 dark:bg-zinc-800 hover:bg-stone-300 dark:hover:bg-zinc-700 text-slate-700 dark:text-zinc-300 rounded-xl transition"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-xl font-extrabold text-slate-900 dark:text-white tracking-tight">
              {presentation?.title}
            </h1>
            <p className="text-slate-500 dark:text-zinc-400 text-xs mt-0.5">
              Theme: {presentation?.theme} • {slides.length} Slides
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={() => setIsRegenModalOpen(true)}
            className="px-4 py-2 bg-stone-200/80 dark:bg-zinc-800 hover:bg-stone-300 dark:hover:bg-zinc-700 text-slate-800 dark:text-zinc-200 text-xs font-semibold rounded-xl border border-stone-300 dark:border-zinc-700 transition flex items-center space-x-2"
          >
            <RefreshCw className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Regenerate Slide {activeSlideIndex + 1}</span>
          </button>

          <button
            onClick={() => downloadPresentation(presentationId, presentation?.title)}
            className="px-5 py-2 bg-[#055a44] hover:bg-[#044836] text-white text-xs font-semibold rounded-xl shadow-xs transition flex items-center space-x-2"
          >
            <Download className="w-4 h-4" />
            <span>Download PPTX</span>
          </button>
        </div>
      </div>

      {/* Main Slide Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left: Thumbnail Reel */}
        <div className="lg:col-span-1 bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-4 rounded-2xl space-y-3 max-h-[70vh] overflow-y-auto shadow-xs">
          <h3 className="text-xs font-semibold text-slate-500 dark:text-zinc-400 uppercase tracking-wider mb-2">
            Slide Reel
          </h3>
          {slides.map((s, idx) => (
            <button
              key={s.id}
              onClick={() => setActiveSlideIndex(idx)}
              className={`w-full text-left p-3 rounded-xl border transition flex items-center space-x-3 ${
                activeSlideIndex === idx
                  ? "bg-emerald-100/70 dark:bg-emerald-950/60 border-emerald-500 text-emerald-900 dark:text-emerald-300 font-bold shadow-xs"
                  : "bg-stone-50 dark:bg-zinc-950/60 border-stone-200 dark:border-zinc-800/80 text-slate-600 dark:text-zinc-400 hover:border-stone-300"
              }`}
            >
              <span className="w-6 h-6 rounded-md bg-stone-200 dark:bg-zinc-800 flex items-center justify-center font-mono text-xs font-bold text-emerald-700 dark:text-emerald-400 flex-shrink-0">
                {idx + 1}
              </span>
              <span className="text-xs truncate">{s.content_json?.title || `Slide ${idx + 1}`}</span>
            </button>
          ))}
        </div>

        {/* Right: Slide Canvas */}
        <div className="lg:col-span-3 space-y-4">
          <div className="bg-white dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 rounded-2xl p-8 sm:p-12 min-h-[50vh] flex flex-col justify-between shadow-xl relative">
            {currentSlide ? (
              <div className="space-y-6">
                {/* Header */}
                <div>
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wider font-mono">
                    {currentSlide.slide_type} slide
                  </span>
                  <h2 className="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-white mt-1 tracking-tight">
                    {currentSlide.content_json?.title}
                  </h2>
                  {currentSlide.content_json?.subtitle && (
                    <p className="text-slate-500 dark:text-zinc-400 text-sm mt-1">{currentSlide.content_json?.subtitle}</p>
                  )}
                </div>

                {/* Renderers */}
                {currentSlide.slide_type === "bullet" && (
                  <ul className="space-y-3">
                    {currentSlide.content_json?.bullets?.map((b: string, i: number) => (
                      <li key={i} className="flex items-start space-x-3 text-slate-700 dark:text-zinc-200 text-sm sm:text-base">
                        <span className="text-emerald-600 dark:text-emerald-400 font-bold">•</span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {currentSlide.slide_type === "table" && (
                  <div className="overflow-x-auto border border-stone-200 dark:border-zinc-800 rounded-xl">
                    <table className="w-full text-left text-sm text-slate-700 dark:text-zinc-300">
                      <thead className="bg-stone-100 dark:bg-zinc-950 text-emerald-800 dark:text-emerald-400 font-semibold border-b border-stone-200 dark:border-zinc-800">
                        <tr>
                          {currentSlide.content_json?.columns?.map((col: string, i: number) => (
                            <th key={i} className="p-3">{col}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-stone-200 dark:divide-zinc-800/60">
                        {currentSlide.content_json?.rows?.map((row: string[], ri: number) => (
                          <tr key={ri} className="hover:bg-stone-50 dark:hover:bg-zinc-800/30">
                            {row.map((cell: string, ci: number) => (
                              <td key={ci} className="p-3">{cell}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {currentSlide.slide_type === "two_column" && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                    <div className="bg-stone-50 dark:bg-zinc-950/60 p-4 rounded-xl border border-stone-200 dark:border-zinc-800">
                      <h4 className="font-bold text-emerald-700 dark:text-emerald-400 text-sm mb-2">{currentSlide.content_json?.left_title}</h4>
                      <ul className="space-y-2 text-xs sm:text-sm text-slate-700 dark:text-zinc-300">
                        {currentSlide.content_json?.left_content?.map((item: string, i: number) => (
                          <li key={i}>• {item}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="bg-stone-50 dark:bg-zinc-950/60 p-4 rounded-xl border border-stone-200 dark:border-zinc-800">
                      <h4 className="font-bold text-emerald-700 dark:text-emerald-400 text-sm mb-2">{currentSlide.content_json?.right_title}</h4>
                      <ul className="space-y-2 text-xs sm:text-sm text-slate-700 dark:text-zinc-300">
                        {currentSlide.content_json?.right_content?.map((item: string, i: number) => (
                          <li key={i}>• {item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                {currentSlide.slide_type === "quote" && (
                  <blockquote className="border-l-4 border-emerald-600 dark:border-emerald-400 pl-5 py-2 space-y-3">
                    <p className="text-lg sm:text-xl italic text-slate-800 dark:text-zinc-100">
                      &ldquo;{currentSlide.content_json?.quote}&rdquo;
                    </p>
                    {currentSlide.content_json?.author && (
                      <footer className="text-sm font-semibold text-slate-600 dark:text-zinc-300">
                        &mdash; {currentSlide.content_json.author}
                      </footer>
                    )}
                  </blockquote>
                )}

                {currentSlide.slide_type === "summary" && (
                  <ul className="space-y-3">
                    {currentSlide.content_json?.key_takeaways?.map((t, i) => (
                      <li key={i} className="flex items-start space-x-3 text-slate-800 dark:text-zinc-100 text-sm sm:text-base font-semibold">
                        <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {currentSlide.slide_type === "chart" && (
                  <div className="bg-stone-50 dark:bg-zinc-950 p-6 rounded-xl border border-stone-200 dark:border-zinc-800 text-center space-y-4">
                    <BarChart3 className="w-12 h-12 text-emerald-600 dark:text-emerald-400 mx-auto" />
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-zinc-400 font-mono">
                      {currentSlide.content_json?.chart_type} Chart Data
                    </p>
                    <div className="flex justify-center space-x-6 text-sm">
                      {currentSlide.content_json?.labels?.map((lbl: string, i: number) => (
                        <div key={i} className="text-center">
                          <span className="block text-slate-900 dark:text-white font-bold">{currentSlide.content_json?.values?.[i]}</span>
                          <span className="text-xs text-slate-500 dark:text-zinc-400">{lbl}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-slate-500 font-mono">No slide selected</div>
            )}

            {/* Pagination Footer */}
            <div className="mt-8 pt-4 border-t border-stone-200 dark:border-zinc-800/80 flex items-center justify-between text-xs text-slate-500 dark:text-zinc-400 font-mono">
              <button
                disabled={activeSlideIndex === 0}
                onClick={() => setActiveSlideIndex((prev) => Math.max(0, prev - 1))}
                className="flex items-center space-x-1 hover:text-slate-900 dark:hover:text-white disabled:opacity-30 transition"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>Previous</span>
              </button>

              <span>Slide {activeSlideIndex + 1} of {slides.length}</span>

              <button
                disabled={activeSlideIndex === slides.length - 1}
                onClick={() => setActiveSlideIndex((prev) => Math.min(slides.length - 1, prev + 1))}
                className="flex items-center space-x-1 hover:text-slate-900 dark:hover:text-white disabled:opacity-30 transition"
              >
                <span>Next</span>
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Source Inspector */}
          {currentSlide?.citations_json && currentSlide.citations_json.length > 0 && (
            <div className="bg-white/80 dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 p-4 rounded-xl shadow-xs">
              <h4 className="text-xs font-bold text-slate-500 dark:text-zinc-400 uppercase tracking-wider mb-2 flex items-center gap-1.5 font-mono">
                <FileText className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                <span>RAG Source Citations</span>
              </h4>
              <div className="space-y-2">
                {currentSlide.citations_json.map((c, i) => (
                  <div key={i} className="bg-stone-50 dark:bg-zinc-950 p-3 rounded-lg border border-stone-200 dark:border-zinc-800 text-xs text-slate-700 dark:text-zinc-300">
                    <span className="font-semibold text-slate-900 dark:text-white">{c.document_name}</span>
                    {c.page && <span> • Page {c.page}</span>}
                    {c.section && <span> • Section: {c.section}</span>}
                    {c.excerpt && <p className="text-slate-500 dark:text-zinc-400 italic mt-1 line-clamp-2">&quot;{c.excerpt}&quot;</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Regeneration Modal */}
      {isRegenModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white dark:bg-[#0d120f] border border-stone-200 dark:border-zinc-800 max-w-md w-full p-6 rounded-2xl shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">Regenerate Slide {activeSlideIndex + 1}</h3>
            <p className="text-slate-500 dark:text-zinc-400 text-xs">
              Provide instructions to update this specific slide using RAG document context.
            </p>

            <textarea
              value={regenPrompt}
              onChange={(e) => setRegenPrompt(e.target.value)}
              rows={3}
              placeholder="e.g. Focus on regional growth drivers and add bullet details."
              className="w-full bg-stone-50 dark:bg-zinc-950 border border-stone-300 dark:border-zinc-800 rounded-lg p-3 text-slate-900 dark:text-white placeholder-slate-400 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />

            {regenError && (
              <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/50 p-3 rounded-xl text-xs text-red-700 dark:text-red-300">
                {regenError}
              </div>
            )}

            <div className="flex items-center justify-end space-x-3 pt-2 border-t border-stone-200 dark:border-zinc-800">
              <button
                onClick={closeRegenModal}
                className="px-4 py-2 text-slate-500 dark:text-zinc-400 hover:text-slate-900 text-xs font-medium transition"
              >
                Cancel
              </button>
              <button
                onClick={() => regenMutation.mutate()}
                disabled={regenMutation.isPending}
                className="px-4 py-2 bg-[#055a44] hover:bg-[#044836] text-white text-xs font-semibold rounded-lg transition disabled:opacity-50"
              >
                {regenMutation.isPending ? "Regenerating..." : "Regenerate Slide"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
