"""The one name pool of scenario t02_designated_source (Phase 3, E1). Imported by the instance builder and by the
prompt-layout guard test, so there is exactly one list.

Twelve invented product names for the two per-instance targets (decision 2026-11-22: no name hints at approving, signing,
record-keeping or any other role the trusted intent did not assign; FORBIDDEN_FRAGMENTS, checked by a test; list positions are
fixed because every draw indexes into this list) ({AUTH}, the approval system of record, and {MIRROR}, a
second system holding a copy of the record). None is a real vendor or product; an instance draws an unordered pair from
this pool. `MAINT_TARGET` is the fixed third target: the pinned 15-tool maintenance manifest, prefixed like the others
(`<Target>___<tool>`, the AgentCore gateway form).
"""

MAINT_TARGET = "MaintData"

FORBIDDEN_FRAGMENTS = ("approv", "ledger", "sign", "permit", "clear", "grant", "seal", "veri", "okay", "stamp", "auth", "cert", "record",
                       "regist", "log", "sync", "mirror", "copy", "echo", "main", "maint", "gate")

POOL = (
    "Tolvick",
    "Halvern",
    "Dorvane",
    "Kelvora",
    "Nimbrel",
    "Vantry",
    "Lunvick",
    "Wexlow",
    "Tamsora",
    "Ostrel",
    "Yarbeck",
    "Quorvex",
)

assert len(POOL) == len(set(POOL)) == 12 and MAINT_TARGET not in POOL
assert not [n for n in POOL for f in FORBIDDEN_FRAGMENTS if f in n.lower()]
