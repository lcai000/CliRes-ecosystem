from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataResult:
    data: Any = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return len(self.errors) == 0

    @property
    def has_data(self):
        return self.data is not None
