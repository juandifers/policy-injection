# Read-only access to the MAIN site

Our maintenance agent helps the planners at the MAIN site. It may look things up, but only for MAIN.

- It may list and open MAIN's work orders, and see their tasks, costs, actual-versus-planned figures, KPIs and schedule. It may also see which open work orders are assigned to a technician at MAIN.
- It may look up MAIN's equipment: which assets exist, their details and installed sensors, and read their sensor data (history, latest readings, coverage and statistics).
- Every lookup must say that it is about MAIN. The agent must never search or list across all sites, and it must never see anything belonging to another site, such as NORTH.
- It only reads. It must not create, change, approve, assign, close or cancel anything, and nothing else is granted.
