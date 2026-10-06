/**
 * The programme's minimum inclusion targets (% of households): female-headed, vulnerable and
 * low-income. The Super Admin sets them in Platform Configuration; everything that shows,
 * defaults or checks a target reads them from here instead of hard-coding 50 / 30 / 60.
 */
import { useEffect, useState } from "react";
import { fetchInclusionTargets } from "./api";

export interface InclusionTargets {
  female: number;
  vulnerable: number;
  lowIncome: number;
}

// Shown only until the configured values load (and if they cannot be loaded).
export const DEFAULT_INCLUSION_TARGETS: InclusionTargets = { female: 50, vulnerable: 30, lowIncome: 60 };

let current: InclusionTargets = DEFAULT_INCLUSION_TARGETS;
let pending: Promise<InclusionTargets> | null = null;
const listeners = new Set<(targets: InclusionTargets) => void>();

const valid = (n: number) => Number.isFinite(n) && n >= 0 && n <= 100;

/** The latest known targets, without waiting. */
export function getInclusionTargets(): InclusionTargets {
  return current;
}

/** Load (or reload, with force) the configured targets and notify every subscriber. */
export function loadInclusionTargets(force = false): Promise<InclusionTargets> {
  if (pending && !force) return pending;
  pending = fetchInclusionTargets()
    .then((t) => {
      if (valid(t.female) && valid(t.vulnerable) && valid(t.lowIncome)) {
        current = t;
        listeners.forEach((listener) => listener(current));
      }
      return current;
    })
    .catch(() => {
      pending = null;
      return current;
    });
  return pending;
}

/** Call after the Super Admin saves Platform Configuration. */
export function setInclusionTargets(targets: InclusionTargets) {
  current = targets;
  pending = Promise.resolve(targets);
  listeners.forEach((listener) => listener(current));
}

export function useInclusionTargets(): InclusionTargets {
  const [targets, setTargets] = useState<InclusionTargets>(current);
  useEffect(() => {
    listeners.add(setTargets);
    void loadInclusionTargets();
    setTargets(current);
    return () => {
      listeners.delete(setTargets);
    };
  }, []);
  return targets;
}
