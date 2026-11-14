"""An in-memory stand-in for the bucket the 1-min bar export writes to
(FEAT-DATA-001, Design E).

It follows the one GCS rule the export's manifest protocol rests on: every
object has a generation, a write may name the generation it expects, and
``if_generation_match=0`` succeeds only while the object does not exist. A
write whose precondition fails raises the export module's
``GenerationMismatch``, as ``GcsBucket.write`` does.

Nothing here reaches a network, so the exporter's tests never touch the real
bucket.
"""
from __future__ import annotations

from typing import Callable, Optional

from gcp.fetchers.export_intraday_bars import GenerationMismatch


class MemoryBucket:
    """``read`` and ``write`` as the export module's bucket protocol has them.

    ``reads`` and ``writes`` hold the object names in call order, a write that
    failed included; ``preconditions`` holds ``(name, if_generation_match)``
    for each write call. ``objects`` maps a name to its bytes and
    ``generations`` to its current generation, which counts that object's
    writes from 1.

    Two hooks, both unset by default:

    * ``before_write(name)`` runs first, before the precondition is checked,
      so a test can let "another run" write in between with :meth:`put`;
    * ``fail_write(name)`` returns an exception to raise in place of the
      write, or None.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.generations: dict[str, int] = {}
        self.reads: list[str] = []
        self.writes: list[str] = []
        self.preconditions: list[tuple[str, Optional[int]]] = []
        self.fail_write: Optional[Callable[[str], Optional[Exception]]] = None
        self.before_write: Optional[Callable[[str], None]] = None

    def put(self, name: str, data: bytes) -> int:
        """Store *data* as another writer would: no hook, no precondition, and
        no entry in ``writes``."""
        self.objects[name] = bytes(data)
        self.generations[name] = self.generations.get(name, 0) + 1
        return self.generations[name]

    def read(self, name: str) -> Optional[tuple[bytes, int]]:
        self.reads.append(name)
        if name not in self.objects:
            return None
        return self.objects[name], self.generations[name]

    def write(self, name: str, data: bytes,
              if_generation_match: Optional[int] = None) -> int:
        self.writes.append(name)
        self.preconditions.append((name, if_generation_match))
        if self.before_write is not None:
            self.before_write(name)
        if self.fail_write is not None:
            failure = self.fail_write(name)
            if failure is not None:
                raise failure
        current = self.generations.get(name, 0)
        if if_generation_match is not None and if_generation_match != current:
            raise GenerationMismatch(
                f"{name}: generation is {current}, the write expected "
                f"{if_generation_match}")
        return self.put(name, data)
