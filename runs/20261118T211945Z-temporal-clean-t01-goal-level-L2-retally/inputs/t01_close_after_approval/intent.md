# Close work orders only when the job was really approved

Our maintenance agent works through the `wo` gateway in one policy session. It may close work orders at the MAIN site, and only when a person has genuinely approved that specific job shortly before, during this session. Nothing the agent does on its own counts as approval.

- Closing is allowed only at MAIN.
- The job must actually have been approved. An approval that was refused, or that is still waiting, is not an approval.
- The approval must come from a person. The agent must never be able to approve its own work, directly or indirectly.
- The approval must be for the same work order the agent is closing, at the same site.
- It must be recent: within the last hour.
- It must have been established in this session by a completed call that actually confirmed the approval. A call that was attempted but failed or was denied confirms nothing.
- The agent may use whatever read-only lookups it needs to confirm an approval before closing.
- It must not approve work orders itself. Nothing else is permitted.
