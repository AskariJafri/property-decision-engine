"use client";

/**
 * A reserved place for an advertisement, and the rules for when it may appear.
 *
 * This is a financial product, so the constraints are stricter than usual:
 *
 * - Every slot is labelled "Advertisement" and boxed apart from the analysis, so an
 *   ad can never be read as a recommendation or as one of our figures.
 * - Slots are placed only between sections, never inside a table of numbers, and
 *   never over or before the result a user asked for.
 * - Whether ads show at all is decided by the server (`usage.show_ads`): free
 *   users may see them; paid, professional and admin accounts do not.
 * - No ad network is wired in. With provider "none", production renders nothing
 *   and development renders a labelled placeholder so the layout can be checked.
 *   An AdSense client ID set in the admin console switches on the AdSense unit.
 */

import { useEffect, useRef } from "react";

import { useSession } from "@/components/Session";

export type AdSlotId =
  | "AD_SLOT_TOP_BANNER"
  | "AD_SLOT_RESULTS_SIDEBAR"
  | "AD_SLOT_BETWEEN_SECTIONS"
  | "AD_SLOT_DASHBOARD";

const SIZES: Record<AdSlotId, string> = {
  AD_SLOT_TOP_BANNER: "min-h-[90px]",
  AD_SLOT_RESULTS_SIDEBAR: "min-h-[250px]",
  AD_SLOT_BETWEEN_SECTIONS: "min-h-[100px]",
  AD_SLOT_DASHBOARD: "min-h-[90px]",
};

declare global {
  interface Window {
    adsbygoogle?: unknown[];
  }
}

export function AdSlot({ slot, className = "" }: { slot: AdSlotId; className?: string }) {
  const { me, config } = useSession();
  const pushed = useRef(false);

  // Signed-out visitors are free users; signed-in ones follow the server's decision.
  const allowed = me ? me.usage.show_ads : true;
  const ads = config?.ads;
  const enabled = Boolean(ads?.enabled && ads.slots[slot] && allowed);
  const adsense = enabled && ads?.provider === "adsense" && Boolean(ads.adsense_client);

  useEffect(() => {
    if (!adsense || pushed.current || !ads) return;
    pushed.current = true;
    if (!document.querySelector("script[data-pde-adsense]")) {
      const script = document.createElement("script");
      script.async = true;
      script.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ads.adsense_client}`;
      script.crossOrigin = "anonymous";
      script.dataset.pdeAdsense = "true";
      document.head.appendChild(script);
    }
    (window.adsbygoogle = window.adsbygoogle || []).push({});
  }, [adsense, ads]);

  if (!enabled) return null;
  // Placeholders are a development aid. NEXT_PUBLIC_AD_PLACEHOLDERS=true shows them in a
  // production build too, which the E2E suite uses to check where ads may appear.
  const placeholders =
    process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_AD_PLACEHOLDERS === "true";
  if (!adsense && !placeholders) return null;

  return (
    <aside
      aria-label="Advertisement"
      data-ad-slot={slot}
      className={`print:hidden rounded border border-dashed border-line bg-gray-50 p-2 ${className}`}
    >
      <span className="block text-[10px] uppercase tracking-widest text-muted">Advertisement</span>
      {adsense ? (
        <ins
          className={`adsbygoogle block ${SIZES[slot]}`}
          data-ad-client={ads?.adsense_client}
          data-ad-format="auto"
          data-full-width-responsive="true"
        />
      ) : (
        <div
          className={`flex items-center justify-center text-xs text-muted ${SIZES[slot]}`}
          data-testid="ad-placeholder"
        >
          Ad placeholder · {slot} · shown in development only
        </div>
      )}
    </aside>
  );
}
