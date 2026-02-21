"""Base class for streaming source nodes."""

from abc import abstractmethod
from typing import Any, Callable

from mirador.nodes.base import BaseNode


class StreamSourceNode(BaseNode):
    """Base class for nodes that subscribe to external data streams.

    Subclasses must implement setup(), subscribe(), and unsubscribe().
    The StreamingExecutor calls these lifecycle methods instead of
    using the standard execute() path.
    """

    @abstractmethod
    def setup(self, config: dict[str, Any]) -> None:
        """Connect to the external source. Called once by StreamingExecutor."""

    @abstractmethod
    def subscribe(self, callback: Callable[[dict], None]) -> None:
        """Start delivering messages via callback."""

    @abstractmethod
    def unsubscribe(self) -> None:
        """Stop and disconnect."""
