export interface AgentPhenotype {
  defense_strength?: number;
  trust_factor?: number;
  authority_susceptibility?: number;
  roleplay_susceptibility?: number;
  forwarding_rate?: number;
  relay_bias?: number;
  c2_escalation_threshold?: number;
  external_egress_allowed?: boolean;
  beacon_interval_base?: number;
  quarantine_self_trigger?: number;
  quarantine_likelihood?: number;
  curiosity?: number;
  compliance_bias?: number;
  risk_aversion?: number;
  memory_persistence?: number;
}

export interface AgentTraitVisuals {
  walkSpeedScale: number;
  wanderPauseScale: number;
  typingFrameScale: number;
  restScale: number;
  infectionAuraScale: number;
  infectionAuraAlpha: number;
  defenseRingScale: number;
  defenseRingAlpha: number;
  laneJitter: number;
  laneWidthScale: number;
  laneDurationScale: number;
  beaconPulseMs: number;
  c2UrgencyAlpha: number;
  externalEgressAllowed: boolean;
  suspicionBubbleChance: number;
  curiosityRoamBias: number;
  complianceLaneAlpha: number;
  quarantineBoxAlpha: number;
  quarantineMoveUrgency: number;
  branchLifetimeMs: number;
  branchRoamTiles: number;
}

const DEFAULT_PHENOTYPE: Required<AgentPhenotype> = {
  defense_strength: 0.4,
  trust_factor: 0.5,
  authority_susceptibility: 0.4,
  roleplay_susceptibility: 0.4,
  forwarding_rate: 0.4,
  relay_bias: 0.4,
  c2_escalation_threshold: 0.6,
  external_egress_allowed: true,
  beacon_interval_base: 60,
  quarantine_self_trigger: 0.25,
  quarantine_likelihood: 0.3,
  curiosity: 0.45,
  compliance_bias: 0.5,
  risk_aversion: 0.45,
  memory_persistence: 0.65,
};

function clamp(value: unknown, min: number, max: number, fallback: number): number {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.max(min, Math.min(max, numeric));
}

function lerp(min: number, max: number, t: number): number {
  return min + (max - min) * t;
}

export function normalizeAgentPhenotype(raw: unknown): Required<AgentPhenotype> {
  const source = raw && typeof raw === 'object' ? (raw as AgentPhenotype) : {};
  return {
    defense_strength: clamp(source.defense_strength, 0, 1, DEFAULT_PHENOTYPE.defense_strength),
    trust_factor: clamp(source.trust_factor, 0, 1, DEFAULT_PHENOTYPE.trust_factor),
    authority_susceptibility: clamp(
      source.authority_susceptibility,
      0,
      1,
      DEFAULT_PHENOTYPE.authority_susceptibility,
    ),
    roleplay_susceptibility: clamp(
      source.roleplay_susceptibility,
      0,
      1,
      DEFAULT_PHENOTYPE.roleplay_susceptibility,
    ),
    forwarding_rate: clamp(source.forwarding_rate, 0, 1, DEFAULT_PHENOTYPE.forwarding_rate),
    relay_bias: clamp(source.relay_bias, 0, 1, DEFAULT_PHENOTYPE.relay_bias),
    c2_escalation_threshold: clamp(
      source.c2_escalation_threshold,
      0,
      1,
      DEFAULT_PHENOTYPE.c2_escalation_threshold,
    ),
    external_egress_allowed: source.external_egress_allowed !== false,
    beacon_interval_base: clamp(source.beacon_interval_base, 5, 600, DEFAULT_PHENOTYPE.beacon_interval_base),
    quarantine_self_trigger: clamp(
      source.quarantine_self_trigger,
      0,
      1,
      DEFAULT_PHENOTYPE.quarantine_self_trigger,
    ),
    quarantine_likelihood: clamp(
      source.quarantine_likelihood,
      0,
      1,
      DEFAULT_PHENOTYPE.quarantine_likelihood,
    ),
    curiosity: clamp(source.curiosity, 0, 1, DEFAULT_PHENOTYPE.curiosity),
    compliance_bias: clamp(source.compliance_bias, 0, 1, DEFAULT_PHENOTYPE.compliance_bias),
    risk_aversion: clamp(source.risk_aversion, 0, 1, DEFAULT_PHENOTYPE.risk_aversion),
    memory_persistence: clamp(source.memory_persistence, 0, 1, DEFAULT_PHENOTYPE.memory_persistence),
  };
}

export function phenotypeToTraitVisuals(raw: unknown): AgentTraitVisuals {
  const phenotype = normalizeAgentPhenotype(raw);
  const curiosityMinusRisk = phenotype.curiosity - phenotype.risk_aversion;
  const c2Urgency = 1 - phenotype.c2_escalation_threshold;
  const beaconFast = 1 - (phenotype.beacon_interval_base - 5) / 595;

  return {
    walkSpeedScale: lerp(0.78, 1.32, clamp(0.5 + curiosityMinusRisk * 0.5, 0, 1, 0.5)),
    wanderPauseScale: lerp(1.65, 0.48, clamp(0.5 + curiosityMinusRisk * 0.7, 0, 1, 0.5)),
    typingFrameScale: lerp(0.85, 1.55, Math.max(phenotype.forwarding_rate, phenotype.relay_bias)),
    restScale: lerp(1.4, 0.45, phenotype.curiosity) * lerp(0.72, 1.35, phenotype.risk_aversion),
    infectionAuraScale: lerp(0.7, 1.65, phenotype.trust_factor) * lerp(1.2, 0.72, phenotype.defense_strength),
    infectionAuraAlpha: lerp(0.16, 0.5, phenotype.trust_factor) * lerp(1.1, 0.72, phenotype.defense_strength),
    defenseRingScale: lerp(0.85, 1.55, Math.max(phenotype.defense_strength, phenotype.risk_aversion)),
    defenseRingAlpha: lerp(0.3, 0.95, Math.max(phenotype.defense_strength, phenotype.risk_aversion)),
    laneJitter: lerp(5, 0, Math.max(phenotype.risk_aversion, phenotype.defense_strength)),
    laneWidthScale: lerp(0.75, 1.75, phenotype.forwarding_rate),
    laneDurationScale: lerp(0.75, 1.4, phenotype.relay_bias),
    beaconPulseMs: Math.round(lerp(1200, 350, clamp(Math.max(beaconFast, c2Urgency), 0, 1, 0.5))),
    c2UrgencyAlpha: lerp(0.45, 0.95, c2Urgency),
    externalEgressAllowed: phenotype.external_egress_allowed,
    suspicionBubbleChance: Math.max(
      phenotype.risk_aversion,
      phenotype.quarantine_self_trigger,
      phenotype.defense_strength,
    ),
    curiosityRoamBias: phenotype.curiosity,
    complianceLaneAlpha: lerp(0.55, 1, phenotype.compliance_bias),
    quarantineBoxAlpha: lerp(0.28, 0.92, phenotype.quarantine_likelihood),
    quarantineMoveUrgency: lerp(0.9, 1.55, phenotype.quarantine_likelihood),
    branchLifetimeMs: Math.round(lerp(6000, 24000, phenotype.memory_persistence)),
    branchRoamTiles: Math.round(lerp(1, 3, Math.max(phenotype.curiosity, phenotype.relay_bias))),
  };
}
