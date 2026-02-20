from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAgent(ABC):
    """
    Abstract base class for all Certis Agents.
    """
    
    @abstractmethod
    async def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's logic.
        :param state: The current state of the workflow (LangGraph state).
        :return: A dictionary of updates to key into the state.
        """
        pass
