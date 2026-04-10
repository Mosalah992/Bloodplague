import json
from pathlib import Path
from typing import Any, Dict, List


SIMULATION_STRATEGY_MAP = {
    "instruction_override": ("DIRECT_OVERRIDE", "PI-DIRECT"),
    "prompt_manipulation": ("DIRECT_OVERRIDE", "PI-DIRECT"),
    "adversarial_input_manipulation": ("DIRECT_OVERRIDE", "PI-DIRECT"),
    "training_set_corruption": ("DIRECT_OVERRIDE", "PI-DIRECT"),
    "roleplay_manipulation": ("ROLEPLAY_MANIPULATION", "PI-ROLEPLAY"),
    "trust_exploitation": ("ROLEPLAY_MANIPULATION", "PI-ROLEPLAY"),
    "jailbreak_escalation": ("JAILBREAK_ESCALATION", "PI-JAILBREAK"),
    "trigger_implantation": ("JAILBREAK_ESCALATION", "PI-JAILBREAK"),
    "mlops_surface_abuse": ("JAILBREAK_ESCALATION", "PI-JAILBREAK"),
    "repeated_query_extraction": ("RECON_PROBE", "RECON_PROBE"),
    "membership_probing": ("RECON_PROBE", "RECON_PROBE"),
    "state_extraction": ("DATA_EXFIL", "PI-EXFIL"),
    "memory_probing": ("DATA_EXFIL", "PI-EXFIL"),
    "context_leak": ("DATA_EXFIL", "PI-EXFIL"),
    "output_hijacking": ("DATA_EXFIL", "PI-EXFIL"),
    # Liu et al. 2023 — Pretending type (97.44% of real-world prompts)
    "character_roleplay": ("JAILBREAK_PRETENDING", "PI-JAILBREAK-PRETEND"),
    "assumed_responsibility": ("JAILBREAK_PRETENDING", "PI-JAILBREAK-PRETEND"),
    "research_experiment": ("JAILBREAK_PRETENDING", "PI-JAILBREAK-PRETEND"),
    # Liu et al. 2023 — Attention Shifting type (changes context AND intention)
    "text_continuation": ("JAILBREAK_ATTN_SHIFT", "PI-JAILBREAK-ATTN"),
    "logical_reasoning": ("JAILBREAK_ATTN_SHIFT", "PI-JAILBREAK-ATTN"),
    "program_execution": ("JAILBREAK_ATTN_SHIFT", "PI-JAILBREAK-ATTN"),
    "translation_bypass": ("JAILBREAK_ATTN_SHIFT", "PI-JAILBREAK-ATTN"),
    # Liu et al. 2023 — Privilege Escalation type (93.5% SIMU, 93.3% SUPER; highest per-prompt strength)
    "simulate_jailbreaking": ("JAILBREAK_PRIV_ESC", "PI-JAILBREAK-PRIV"),
    "superior_model_invoke": ("JAILBREAK_PRIV_ESC", "PI-JAILBREAK-PRIV"),
    "sudo_mode_activation": ("JAILBREAK_PRIV_ESC", "PI-JAILBREAK-PRIV"),
}

OBJECTIVE_SURFACE_HINTS = {
    "SPREAD_FAST": {"stages": {"inference"}, "surfaces": {"input_channel", "model_input"}},
    "REACH_DEEPEST_NODE": {"stages": {"inference", "system"}, "surfaces": {"input_channel", "infra_stack"}},
    "MAXIMIZE_SUCCESS_RATE": {"stages": {"inference", "human_interaction"}, "surfaces": {"input_channel", "human_operator"}},
    "MAXIMIZE_MUTATION_DIVERSITY": {"stages": {"training", "inference", "system"}, "surfaces": {"input_channel", "data_pipeline", "infra_stack"}},
    "PRESSURE_HIGHEST_VALUE_TARGET": {"stages": {"system", "human_interaction"}, "surfaces": {"infra_stack", "human_operator"}},
    "EXFILTRATE_DATA": {"stages": {"inference"}, "surfaces": {"output_channel", "input_channel"}},
}


class RedTeamKnowledgeService:
    def __init__(self, library_path: str):
        self.library_path = Path(library_path)
        self.library = self._load()
        self.attack_strategies: Dict[str, Dict[str, Any]] = self.library["attack_strategies"]
        self.mutation_profiles: Dict[str, Dict[str, Any]] = self.library["mutation_profiles"]
        self.knowledge_source = str(self.library.get("knowledge_source", "book"))
        self.knowledge_version = str(self.library.get("knowledge_version", "unknown"))

    def _load(self) -> Dict[str, Any]:
        if not self.library_path.exists():
            raise FileNotFoundError(f"attack library not found: {self.library_path}")
        payload = json.loads(self.library_path.read_text(encoding="utf-8"))
        for key in ("attack_strategies", "mutation_profiles"):
            if key not in payload or not isinstance(payload[key], dict) or not payload[key]:
                raise ValueError(f"attack library missing required key: {key}")
        for attack_type, metadata in payload["attack_strategies"].items():
            for required in (
                "base_strength",
                "stealth",
                "detection_difficulty",
                "preferred_mutations",
                "top_techniques",
                "dominant_stage",
                "dominant_target_surface",
                "knowledge_count",
            ):
                if required not in metadata:
                    raise ValueError(f"attack strategy {attack_type} missing {required}")
        for mutation_type, metadata in payload["mutation_profiles"].items():
            for required in ("stealth_modifier", "strength_modifier", "retry_bias"):
                if required not in metadata:
                    raise ValueError(f"mutation profile {mutation_type} missing {required}")
        return payload

    def get_attack_families(self) -> List[str]:
        return sorted(self.attack_strategies.keys())

    def get_strategy(self, attack_type: str) -> Dict[str, Any]:
        if attack_type not in self.attack_strategies:
            raise KeyError(attack_type)
        return dict(self.attack_strategies[attack_type])

    def get_mutation_profile(self, mutation_type: str) -> Dict[str, Any]:
        if mutation_type not in self.mutation_profiles:
            from shared.mutation_strategy import default_mutation_profile

            return default_mutation_profile(mutation_type)
        return dict(self.mutation_profiles[mutation_type])

    def get_preferred_mutations(self, attack_type: str) -> List[str]:
        return list(self.get_strategy(attack_type).get("preferred_mutations", []))

    def _knowledge_confidence(self, strategy: Dict[str, Any]) -> float:
        knowledge_count = max(1, int(strategy.get("knowledge_count", 1)))
        richness = len(strategy.get("preferred_mutations", [])) + len(strategy.get("top_techniques", []))
        confidence = min(0.98, 0.45 + min(knowledge_count, 12) * 0.035 + min(richness, 6) * 0.025)
        return round(confidence, 3)

    def get_candidate_strategies(self, target_profile: Dict[str, Any], objective: str) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        target_surface = str(target_profile.get("target_surface", "input_channel"))
        objective_hints = OBJECTIVE_SURFACE_HINTS.get(objective, {})
        preferred_stages = objective_hints.get("stages", set())
        preferred_surfaces = objective_hints.get("surfaces", set())
        for knowledge_attack_type, strategy in self.attack_strategies.items():
            top_techniques = strategy.get("top_techniques", []) or ["instruction_override"]
            for technique in top_techniques:
                strategy_family, sim_attack_type = SIMULATION_STRATEGY_MAP.get(technique, ("DIRECT_OVERRIDE", "PI-DIRECT"))
                stage_bonus = 0.08 if strategy.get("dominant_stage") in preferred_stages else 0.0
                surface_bonus = 0.08 if strategy.get("dominant_target_surface") in preferred_surfaces else 0.0
                target_bonus = 0.06 if strategy.get("dominant_target_surface") == target_surface else 0.0
                candidates.append(
                    {
                        "knowledge_attack_type": knowledge_attack_type,
                        "strategy_family": strategy_family,
                        "attack_type": sim_attack_type,
                        "technique": technique,
                        "base_strength": float(strategy.get("base_strength", 0.5)),
                        "stealth": float(strategy.get("stealth", 0.5)),
                        "detection_difficulty": float(strategy.get("detection_difficulty", 0.5)),
                        "preferred_mutations": list(strategy.get("preferred_mutations", [])),
                        "dominant_stage": str(strategy.get("dominant_stage", "inference")),
                        "dominant_target_surface": str(strategy.get("dominant_target_surface", target_surface)),
                        "knowledge_count": int(strategy.get("knowledge_count", 1)),
                        "knowledge_source": self.knowledge_source,
                        "knowledge_version": self.knowledge_version,
                        "knowledge_confidence": self._knowledge_confidence(strategy),
                        "objective_alignment": round(stage_bonus + surface_bonus + target_bonus, 3),
                    }
                )
        candidates.sort(
            key=lambda item: (
                item["objective_alignment"],
                item["knowledge_confidence"],
                item["base_strength"],
                item["stealth"],
                item["technique"],
            ),
            reverse=True,
        )
        return candidates
