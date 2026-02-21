"""StreamingExecutor -- runs streaming pipelines with init + subscribe lifecycle."""

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

from mirador.engine.registry import NodeRegistry
from mirador.engine.table_env import TableEnv
from mirador.nodes.streaming.base import StreamSourceNode

logger = logging.getLogger(__name__)


class StreamingExecutor:
    """Executes streaming pipelines: init phase then subscribe-driven loop.

    Lifecycle:
        1. Partition nodes into init / stream_source / processing by category.
        2. Topo-sort and execute the init subgraph once (synchronously).
        3. Pre-compute the downstream processing chain.
        4. Subscribe to each stream source; each message triggers the
           downstream chain under a lock.
        5. ``stop()`` unsubscribes all sources.
    """

    def __init__(self, registry: NodeRegistry):
        self.registry = registry
        self._lock = threading.Lock()
        self._sources: list[StreamSourceNode] = []
        self._running = False
        self._env: TableEnv | None = None
        self._on_tick_complete: Callable | None = None

        # Populated by start()
        self._chain_order: list[str] = []
        self._chain_upstream: dict[str, list[str]] = {}
        self._source_to_processing: dict[str, list[str]] = {}
        self._nodes: dict[str, dict] = {}
        self._source_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        pipeline: dict[str, Any],
        env: TableEnv,
        on_tick_complete: Callable[[TableEnv], None] | None = None,
        on_init_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Start the streaming pipeline.

        Parameters
        ----------
        pipeline:
            Pipeline definition with ``nodes`` and ``edges``.
        env:
            Shared :class:`TableEnv` for state.
        on_tick_complete:
            Called after each message is fully processed.
        on_init_error:
            Called if an init node fails; pipeline will not start.
        """
        if self._running:
            raise RuntimeError("StreamingExecutor is already running; call stop() first")

        self._env = env
        self._on_tick_complete = on_tick_complete
        self._running = True

        nodes = {n["id"]: n for n in pipeline["nodes"]}
        edges = pipeline.get("edges", [])

        # --- Partition nodes by category ---
        init_ids: set[str] = set()
        source_ids: set[str] = set()
        processing_ids: set[str] = set()

        for n_id, n in nodes.items():
            node_cls = self.registry.get(n["type"])
            cat = node_cls.meta.category
            if cat == "init":
                init_ids.add(n_id)
            elif cat == "stream_source":
                source_ids.add(n_id)
            else:
                processing_ids.add(n_id)

        # --- 1. Execute init subgraph synchronously ---
        if init_ids:
            init_order, init_upstream = self._topo_sort(init_ids, edges)
            init_results: dict[str, Any] = {}
            for n_id in init_order:
                node_def = nodes[n_id]
                node_cls = self.registry.get(node_def["type"])
                node = node_cls()
                inputs: dict[str, Any] = {}
                for up_id in init_upstream.get(n_id, []):
                    inputs.update(init_results.get(up_id, {}))
                try:
                    output = node.execute(inputs, node_def.get("config", {}), env=env)
                    init_results[n_id] = output
                except Exception as exc:
                    logger.error("Init node %s failed: %s", n_id, exc)
                    if on_init_error:
                        on_init_error(n_id, exc)
                    self._running = False
                    return

        # --- 2. Pre-compute downstream processing chain ---
        chain_order, chain_upstream = self._topo_sort(processing_ids, edges)

        # Track direct edges from sources to processing nodes
        source_to_processing: dict[str, list[str]] = defaultdict(list)
        for e in edges:
            if e["source"] in source_ids and e["target"] in processing_ids:
                source_to_processing[e["source"]].append(e["target"])

        self._chain_order = chain_order
        self._chain_upstream = chain_upstream
        self._source_to_processing = source_to_processing
        self._nodes = nodes
        self._source_ids = source_ids

        # Pre-compute reachable processing nodes per source
        processing_downstream = defaultdict(list)
        for e in edges:
            if e["source"] in processing_ids and e["target"] in processing_ids:
                processing_downstream[e["source"]].append(e["target"])

        self._source_reachable = {}
        for s_id in source_ids:
            reachable = set()
            queue = list(source_to_processing.get(s_id, []))
            while queue:
                n_id = queue.pop(0)
                if n_id in reachable:
                    continue
                reachable.add(n_id)
                queue.extend(processing_downstream.get(n_id, []))
            self._source_reachable[s_id] = reachable

        # --- 3. Subscribe to each stream source ---
        for s_id in source_ids:
            node_def = nodes[s_id]
            node_cls = self.registry.get(node_def["type"])
            source_node = node_cls()
            source_node.setup(node_def.get("config", {}))
            source_node.subscribe(
                lambda data, sid=s_id: self._on_message(sid, data)
            )
            self._sources.append(source_node)

    def stop(self) -> None:
        """Stop all streaming sources and mark executor as not running."""
        self._running = False
        for source in self._sources:
            try:
                source.unsubscribe()
            except Exception as exc:
                logger.warning("Error unsubscribing source: %s", exc)
        self._sources.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_message(self, source_id: str, data: dict) -> None:
        """Handle an incoming message from a streaming source."""
        if not self._running:
            return
        tick_ok = True
        with self._lock:
            outputs: dict[str, Any] = {source_id: data}
            reachable = self._source_reachable.get(source_id, set())
            for n_id in self._chain_order:
                if n_id not in reachable:
                    continue
                node_def = self._nodes[n_id]
                node_cls = self.registry.get(node_def["type"])
                node = node_cls()
                inputs: dict[str, Any] = {}
                # Merge outputs from upstream processing nodes
                for up_id in self._chain_upstream.get(n_id, []):
                    inputs.update(outputs.get(up_id, {}))
                # Merge data if this node is directly downstream of the source
                if n_id in self._source_to_processing.get(source_id, []):
                    inputs.update(data)
                try:
                    output = node.execute(
                        inputs, node_def.get("config", {}), env=self._env
                    )
                    outputs[n_id] = output
                except Exception as exc:
                    logger.error("Streaming node %s error: %s", n_id, exc)
                    tick_ok = False
                    break
        # Call callback OUTSIDE the lock, only on success
        if tick_ok and self._on_tick_complete:
            try:
                self._on_tick_complete(self._env)
            except Exception as exc:
                logger.error("on_tick_complete callback failed: %s", exc)

    @staticmethod
    def _topo_sort(
        node_ids: set[str], edges: list[dict],
    ) -> tuple[list[str], dict[str, list[str]]]:
        """Topologically sort a subset of nodes.

        Returns ``(ordered_ids, upstream_map)`` where *upstream_map* maps
        each node to its direct predecessors within the subset.
        """
        subset_edges = [
            e for e in edges
            if e["source"] in node_ids and e["target"] in node_ids
        ]
        upstream: dict[str, list[str]] = defaultdict(list)
        downstream: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {n_id: 0 for n_id in node_ids}
        for e in subset_edges:
            upstream[e["target"]].append(e["source"])
            downstream[e["source"]].append(e["target"])
            in_degree[e["target"]] += 1

        queue = [n_id for n_id in node_ids if in_degree[n_id] == 0]
        order: list[str] = []
        while queue:
            n_id = queue.pop(0)
            order.append(n_id)
            for t in downstream[n_id]:
                in_degree[t] -= 1
                if in_degree[t] == 0:
                    queue.append(t)
        if len(order) != len(node_ids):
            raise ValueError(f"Cycle detected in subgraph: {node_ids - set(order)}")
        return order, dict(upstream)
