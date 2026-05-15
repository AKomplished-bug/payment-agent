from orchestrator import ConversationOrchestrator


class Agent:
    def __init__(self):
        self._orchestrator = ConversationOrchestrator()

    def next(self, user_input: str) -> dict:
        """
        Process one turn of the conversation.

        Args:
            user_input: The user's message as a plain string.

        Returns:
            {"message": str}
        """
        if not isinstance(user_input, str):
            user_input = str(user_input)
        message = self._orchestrator.process_turn(user_input.strip())
        return {"message": message}
