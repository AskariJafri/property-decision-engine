"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AnalysisResult } from "@/components/AnalysisResult";
import { LoadingOr, RequireAuth } from "@/components/RequireAuth";
import { apiFetch, type SavedAnalysis } from "@/lib/api";

export default function SavedAnalysisPage() {
  return <RequireAuth>{() => <Saved />}</RequireAuth>;
}

function Saved() {
  const { id } = useParams<{ id: string }>();
  const [analysis, setAnalysis] = useState<SavedAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<SavedAnalysis>(`/analyses/${id}`)
      .then(setAnalysis)
      .catch((caught: Error) => setError(caught.message));
  }, [id]);

  return (
    <LoadingOr error={error} ready={analysis !== null}>
      {analysis && (
        <div className="space-y-6">
          <div>
            <Link href="/dashboard" className="text-sm text-muted hover:text-ink">
              ← Your analyses
            </Link>
            <h1 className="mt-2 text-xl font-semibold">{analysis.title ?? "Property"}</h1>
            <p className="text-xs text-muted">
              Analysed {analysis.created_at ? new Date(analysis.created_at).toLocaleString("en-CA") : ""}
              {" "}· saved results are exactly as computed then
            </p>
          </div>
          <AnalysisResult result={analysis} deepDiveUnlocked={analysis.deep_dive_unlocked} />
        </div>
      )}
    </LoadingOr>
  );
}
