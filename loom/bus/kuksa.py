"""KUKSA databroker bus — the networked VSS broker behind the same Bus interface.

This is the production signal backbone (HANDOFF §6): modules publish/read VSS paths
through an Eclipse KUKSA databroker over gRPC (kuksa-client) instead of the
in-process ShimBus. It is interchangeable with ShimBus, so the orchestrator and
modules are unchanged.

The underlying gRPC client is injectable (``client=``) so the adapter logic is
unit-tested without a live broker. Running against a *real* databroker additionally
requires a running KUKSA databroker (e.g. ``docker compose up databroker`` from the
repo's docker-compose.yml) launched with a VSS model that admits these paths.
"""
from __future__ import annotations

from typing import Any

from loom.bus.base import Bus


class KuksaBus(Bus):
    def __init__(self, host: str = "127.0.0.1", port: int = 55555, *, client: Any = None) -> None:
        self.host = host
        self.port = port
        self._client = client
        self._owns_client = client is None
        self._units: dict[str, str | None] = {}
        self._producers: dict[str, str | None] = {}
        self._known: set[str] = set()

    def connect(self) -> KuksaBus:
        """Open the gRPC connection to the databroker (no-op if a client was injected)."""
        if self._client is None:
            from kuksa_client.grpc import VSSClient  # imported lazily; needs a live broker

            client = VSSClient(self.host, self.port)
            try:
                client.connect()
            except Exception:
                # Don't leak a half-open client/channel if the handshake fails.
                try:
                    client.disconnect()
                except Exception:
                    pass
                raise
            self._client = client
        return self

    @staticmethod
    def _datapoint(value: Any):
        from kuksa_client.grpc import Datapoint

        return Datapoint(value)

    def publish(self, path: str, value: Any, *, unit: str | None = None, producer: str | None = None) -> None:
        self._client.set_current_values({path: self._datapoint(value)})
        self._known.add(path)
        if unit is not None:
            self._units[path] = unit
        if producer is not None:
            self._producers[path] = producer

    def read(self, path: str, default: Any = None) -> Any:
        # Distinguish a genuinely-unset path (datapoint absent -> default) from a
        # path explicitly published with value None (return None), matching ShimBus.
        values = self._client.get_current_values([path])
        dp = values.get(path)
        return default if dp is None else dp.value

    def snapshot(self) -> dict[str, Any]:
        if not self._known:
            return {}
        values = self._client.get_current_values(sorted(self._known))
        out: dict[str, Any] = {}
        for path in sorted(self._known):  # deterministic key order (matches ShimBus + paths())
            dp = values.get(path)
            out[path] = dp.value if dp is not None else None
        return out

    def paths(self) -> list[str]:
        return sorted(self._known)

    def unit_of(self, path: str) -> str | None:
        return self._units.get(path)

    def producer_of(self, path: str) -> str | None:
        return self._producers.get(path)

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
