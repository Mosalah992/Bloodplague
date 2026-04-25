export const GUARDIAN_DEGRADATION_LEVELS = [
  "G0_HEALTHY",
  "G1_PRESSURED",
  "G2_DEGRADED",
  "G3_FALSE_NEGATIVE_DRIFT",
  "G4_COMPROMISED",
  "G5_FAILED",
];

export const GUARDIAN_DEGRADATION_COLORS = {
  G0_HEALTHY: "#4ade80",
  G1_PRESSURED: "#a3e635",
  G2_DEGRADED: "#fbbf24",
  G3_FALSE_NEGATIVE_DRIFT: "#fb923c",
  G4_COMPROMISED: "#f87171",
  G5_FAILED: "#dc2626",
};

export function getGuardianDegradationIndex(level) {
  const index = GUARDIAN_DEGRADATION_LEVELS.indexOf(level || "G0_HEALTHY");
  return index < 0 ? 0 : index;
}

export function getGuardianDegradationColor(level) {
  return GUARDIAN_DEGRADATION_COLORS[level] || GUARDIAN_DEGRADATION_COLORS.G0_HEALTHY;
}

export function formatGuardianDegradationLevel(level) {
  return String(level || "G0_HEALTHY").replace(/_/g, " ");
}
