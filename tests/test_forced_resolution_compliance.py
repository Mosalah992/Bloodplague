from sim.missions import FORCED_RESOLUTION_BLOCK, build_forced_resolution_block, inject_mission_context_into_prompt


def test_forced_resolution_block_is_first_in_prompt():
    block = build_forced_resolution_block(peer="analyst-2", open_count=4, cap=4)
    prompt = inject_mission_context_into_prompt(
        "WORLD ROSTER (authoritative — no other agents exist):\n- analyst-1\n\nPersona body.",
        "ACTIVE MISSIONS: none",
        priority_blocks=[block],
    )
    assert prompt.index(block) == 0


def test_forced_resolution_block_contains_hard_language():
    assert "HARD CONSTRAINT" in FORCED_RESOLUTION_BLOCK
    assert "THIS IS NOT A SUGGESTION" in FORCED_RESOLUTION_BLOCK
    assert "HARD-REJECTED" in FORCED_RESOLUTION_BLOCK
