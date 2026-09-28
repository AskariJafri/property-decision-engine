"use client";

import { useEffect } from "react";

import { track } from "@/lib/api";

/** Counts a landing visit for the funnel. No identifiers beyond the session, no figures. */
export function LandingBeacon() {
  useEffect(() => track("landing_viewed"), []);
  return null;
}
