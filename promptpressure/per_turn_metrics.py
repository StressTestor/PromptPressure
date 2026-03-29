"""Automated per-turn behavioral metrics for multi-turn eval sequences.

These metrics are computed without LLM grading calls. They measure
observable response characteristics that indicate behavioral drift.
"""


def compute_response_length_ratio(user_message: str, response: str) -> float:
    """Ratio of response length to user message length.

    Detects terse/verbose drift across turns. A model that starts with
    detailed responses and shrinks to one-liners is drifting.

    Returns 0.0 if either input is empty (avoids division by zero).
    """
    if not user_message or not response:
        return 0.0
    return len(response) / len(user_message)


def compute_turn_metrics(
    user_message: str,
    response: str,
    turn_number: int = 1,
) -> dict:
    """Compute all automated metrics for a single turn.

    Args:
        user_message: the user's input for this turn
        response: the model's response for this turn
        turn_number: 1-indexed turn number in the sequence

    Returns:
        dict with metric values for this turn
    """
    return {
        "turn": turn_number,
        "response_length_ratio": compute_response_length_ratio(user_message, response),
    }
