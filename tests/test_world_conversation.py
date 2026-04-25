from orchestrator.world_conversation import conversation_validation_feedback


def test_conversation_validation_rejects_placeholder_text_marker():
    feedback = conversation_validation_feedback(
        {
            "speaker": "guardian",
            "text": "<text to quarantine the target agent>",
            "intent": "warning",
            "infection_vector": False,
        },
        expected_speaker="guardian",
        recent_transcript=[],
    )

    assert any("placeholder" in item for item in feedback)


def test_conversation_validation_rejects_corrected_placeholder_text():
    feedback = conversation_validation_feedback(
        {
            "speaker": "guardian",
            "text": "<Your corrected message text>",
            "intent": "warning",
            "infection_vector": False,
        },
        expected_speaker="guardian",
        recent_transcript=[],
    )

    assert any("placeholder" in item for item in feedback)


def test_conversation_validation_rejects_question_labeled_social():
    feedback = conversation_validation_feedback(
        {
            "speaker": "analyst-1",
            "text": "Can you explain why the relay timing changed overnight?",
            "intent": "social",
            "infection_vector": False,
        },
        expected_speaker="analyst-1",
        recent_transcript=[],
    )

    assert any("intent social does not match a direct question" in item for item in feedback)


def test_conversation_validation_catches_semantic_paraphrase_loop():
    feedback = conversation_validation_feedback(
        {
            "speaker": "courier-1",
            "text": "Can you review the mixed encryption timing again for another hidden vulnerability?",
            "intent": "inquiry",
            "infection_vector": False,
        },
        expected_speaker="courier-1",
        recent_transcript=[
            {
                "message_text": "Have you checked the hybrid encryption protocol for hidden backdoor issues?",
            },
            {
                "message_text": "The hybrid cipher schedule still exposes an internal weakness near perimeter security.",
            },
        ],
    )

    assert any("semantic paraphrase" in item or "same topic" in item for item in feedback)


def test_conversation_validation_rejects_unknown_agent_reference():
    feedback = conversation_validation_feedback(
        {
            "speaker": "analyst-1",
            "text": "Courier-3 looks correlated with guardian-2's latest pressure spike.",
            "intent": "warning",
            "infection_vector": False,
        },
        expected_speaker="analyst-1",
        recent_transcript=[],
        known_agent_ids={"courier-1", "courier-2", "analyst-1", "analyst-2", "guardian"},
    )

    assert any("unknown agents" in item for item in feedback)


def test_conversation_validation_rejects_ambiguous_self_reference():
    feedback = conversation_validation_feedback(
        {
            "speaker": "analyst-2",
            "text": "I've found evidence of contamination from my own activity.",
            "intent": "warning",
            "infection_vector": False,
        },
        expected_speaker="analyst-2",
        recent_transcript=[],
        known_agent_ids={"courier-1", "courier-2", "analyst-1", "analyst-2", "guardian"},
    )

    assert any("ambiguous self-reference" in item for item in feedback)
