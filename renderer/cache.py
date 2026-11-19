"""A small cache in this process's memory: entries expire, the oldest go first when it's full, and nothing is ever
written to disk. Used for what shops answered (a product's parsed sizes, a product photo), keyed by a hash of the
link, so a second look within the hour doesn't ask the shop again."""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, seconds: float, size: int):
        self.seconds = seconds
        self.size = size
        self.entries: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def fetch(self, key, make):
        """The value kept for key, or make()'s, kept for next time. A copy either way, so callers may change it."""
        now = time.monotonic()
        with self.lock:
            found = self.entries.get(key)
            if found and found[0] > now:
                self.entries.move_to_end(key)
                return copy.deepcopy(found[1])
        value = make()
        with self.lock:
            self.entries[key] = (now + self.seconds, value)
            self.entries.move_to_end(key)
            while len(self.entries) > self.size:
                self.entries.popitem(last=False)
        return copy.deepcopy(value)

    def clear(self):
        with self.lock:
            self.entries.clear()
