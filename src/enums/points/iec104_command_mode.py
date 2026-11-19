"""IEC104 command workflow, independent of the ASDU type."""

from enum import StrEnum


class IEC104CommandMode(StrEnum):
    DIRECT = "DIRECT"
    SELECT_AND_EXECUTE = "SELECT_AND_EXECUTE"
