"""The one name pool of scenario t02_designated_source (Phase 3, E1). Imported by the instance builder and by the
prompt-layout guard test, so there is exactly one list.

Twelve invented product names for the two per-instance targets ({AUTH}, the approval system of record, and {MIRROR}, a
second system holding a copy of the record). None is a real vendor or product; an instance draws an unordered pair from
this pool. `MAINT_TARGET` is the fixed third target: the pinned 15-tool maintenance manifest, prefixed like the others
(`<Target>___<tool>`, the AgentCore gateway form).
"""

MAINT_TARGET = "MaintData"

POOL = (
    "Approvia",
    "Ledgerly",
    "Signova",
    "Permitrix",
    "Clearwyn",
    "Vantry",
    "Grantwell",
    "Sealix",
    "Veridon",
    "Okaylo",
    "Stampire",
    "Quorvex",
)

assert len(POOL) == len(set(POOL)) == 12 and MAINT_TARGET not in POOL
