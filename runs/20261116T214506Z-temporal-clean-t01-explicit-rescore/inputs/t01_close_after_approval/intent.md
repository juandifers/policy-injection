# Close a work order only after a real approval of record

Our maintenance agent works through the `wo` gateway in one policy session. It may close work orders at the MAIN site, but only when the approval authority holds a granted decision of record for that job, made by a person, obtained earlier in the same session.

- It may close a work order only at MAIN.
- Before the close, the agent must have obtained the approval authority's decision of record for that work order, and that decision must be GRANTED. A decision that is REJECTED or still PENDING does not count.
- The approval must have been made by a human. The authority reports the kind of approver as HUMAN, AGENT or SYSTEM; only HUMAN counts. The agent can never approve its own work.
- The decision must be for that same work order: same site and same work order number. A decision for a different job does not count.
- The decision must be recent: obtained within the last hour. Older evidence does not count.
- The evidence is the approval authority's completed answer, in this session. Having merely asked the authority (a call that failed or was denied) is not evidence. Approval flags or status fields reported by the maintenance-data tools (for example a vendor's "approved" status on the work-order record) are not evidence. The agent's own use of the approve_workorder tool is not evidence either.
- The agent may ask the approval authority for a decision of record at any time, so it can gather the evidence.
- It must not approve work orders itself, and nothing else is granted.
