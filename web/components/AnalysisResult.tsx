"use client";

/**
 * A complete analysis, as shown straight after running it and when reopened.
 *
 * Order is deliberate: the answer and the money first, then what it means for the
 * buyer, then the offer to go deeper, then the evidence. Advertising, where it is
 * shown at all, sits only between the non-financial sections or in the sidebar —
 * never inside or ahead of a figure.
 */

import Link from "next/link";

import { AdSlot } from "@/components/AdSlot";
import {
  BuyScore,
  Explanation,
  Factors,
  Money,
  NotChecked,
  ScoreBreakdown,
  Working,
} from "@/components/Analysis";
import { ComparableGrid } from "@/components/ComparableGrid";
import { MissingInfo, MonthlyBreakdown, PersonalFitSection, RateScenarios } from "@/components/Insights";
import { DeepDiveCta } from "@/components/Monetization";
import type { AnalyzeResponse } from "@/lib/api";

export function AnalysisResult({
  result,
  deepDiveUnlocked = false,
}: {
  result: AnalyzeResponse;
  deepDiveUnlocked?: boolean;
}) {
  const id = result.analysis_id;
  const unlocked = deepDiveUnlocked || Boolean(result.usage?.deep_dive_included);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_240px]">
      <div className="min-w-0 space-y-8">
        {result.duplicate && (
          <p className="rounded border border-line bg-gray-50 p-3 text-sm text-muted">
            You analysed these exact details recently, so this is the saved result — no
            analysis was used.
          </p>
        )}
        <BuyScore result={result} />
        <Money result={result} />
        <MonthlyBreakdown result={result} />
        <PersonalFitSection result={result} />
        <RateScenarios result={result} />
        {id && <DeepDiveCta analysisId={id} unlocked={unlocked} />}
        <MissingInfo items={result.missing_info} />
        <ComparableGrid grid={result.comparable_grid} />
        <Factors result={result} />
        <AdSlot slot="AD_SLOT_BETWEEN_SECTIONS" />
        <Explanation result={result} />
        <ScoreBreakdown scores={result.scores} />
        <NotChecked result={result} />
        <Working result={result} />
      </div>

      <aside className="space-y-4 print:hidden lg:sticky lg:top-6 lg:self-start">
        {id && (
          <nav aria-label="Next steps" className="rounded-lg border border-line p-4 text-sm">
            <h2 className="mb-2 text-xs uppercase tracking-wide text-muted">Next steps</h2>
            <ul className="space-y-2">
              <li>
                <Link className="text-accent hover:underline" href={`/analyses/${id}/offers`}>
                  Try offer scenarios
                </Link>
              </li>
              <li>
                <Link className="text-accent hover:underline" href={`/compare?ids=${id}`}>
                  Compare with another property
                </Link>
              </li>
              <li>
                <Link className="text-accent hover:underline" href={`/watch?analysis=${id}`}>
                  Watch this property
                </Link>
              </li>
              <li>
                <Link className="text-accent hover:underline" href={`/analyses/${id}/deep-dive`}>
                  {unlocked ? "Open the Deep Dive" : "See the Deep Dive"}
                </Link>
              </li>
            </ul>
          </nav>
        )}
        <AdSlot slot="AD_SLOT_RESULTS_SIDEBAR" />
      </aside>
    </div>
  );
}
