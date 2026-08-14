// The board renders one column per key here and silently drops leads whose
// stage is not in this map, so it has to stay in step with `backend/
// lead_stages.py` — that file is the source of truth and lists the same
// stages in the same order. A stage missing from here is a lead that exists
// in the database, counts toward the header total, and appears nowhere.
//
// `interested` and `archived` are both set by the AI SDR engine. `interested`
// was added here first and only here, which fixed the display half and left
// the write half failing: the CRM's own PATCH endpoint still rejected the
// stage this dropdown offered.
export const STAGE_CONFIG = {
  prospect: { label: "Prospect", color: "graphite" },
  contacted: { label: "Contacted", color: "info" },
  // Ordered to match `lead_stages.STAGES`, which follows the SDR transition
  // graph: a lead is qualified before it is contacted, and only shows interest
  // after. This puts Interested one column to the right of where it was.
  qualified: { label: "Qualified", color: "info" },
  interested: { label: "Interested", color: "info" },
  discovery: { label: "Discovery", color: "info" },
  meeting_scheduled: { label: "Meeting Scheduled", color: "warning" },
  proposal_sent: { label: "Proposal Sent", color: "warning" },
  negotiation: { label: "Negotiation", color: "warning" },
  won: { label: "Won", color: "success" },
  lost: { label: "Lost", color: "danger" },
  rejected: { label: "Rejected", color: "danger" },
  cold: { label: "Cold", color: "graphite" },
  archived: { label: "Archived", color: "graphite" },
};

// Winning a deal creates a client, a project and a draft invoice, so the move
// is one-way — the API refuses to leave it (routers/crm.py patch_stage) and
// the UI should not offer what the API will reject.
export const TERMINAL_STAGES = ["won"];

export const STAGES_LIST = Object.keys(STAGE_CONFIG);

export const PROJECT_STATUS_CONFIG = {
  planning: { label: "Planning", color: "graphite" },
  onboarding: { label: "Onboarding", color: "info" },
  development: { label: "Development", color: "info" },
  automation: { label: "Automation", color: "info" },
  testing: { label: "Testing", color: "warning" },
  review: { label: "Review", color: "warning" },
  waiting_client: { label: "Waiting Client", color: "warning" },
  completed: { label: "Completed", color: "success" },
  archived: { label: "Archived", color: "graphite" },
};

export const PROJECT_STATUS_LIST = Object.keys(PROJECT_STATUS_CONFIG);

export const TASK_STATUS_CONFIG = {
  todo: { label: "To Do", color: "graphite" },
  in_progress: { label: "In Progress", color: "info" },
  review: { label: "Review", color: "warning" },
  done: { label: "Done", color: "success" },
  blocked: { label: "Blocked", color: "danger" },
};

export const TASK_STATUS_LIST = Object.keys(TASK_STATUS_CONFIG);

export const PRIORITY_CONFIG = {
  low: { label: "Low", color: "graphite" },
  medium: { label: "Medium", color: "info" },
  high: { label: "High", color: "warning" },
  urgent: { label: "Urgent", color: "danger" },
};

export const INVOICE_STATUS_CONFIG = {
  draft: { label: "Draft", color: "graphite" },
  sent: { label: "Sent", color: "info" },
  viewed: { label: "Viewed", color: "info" },
  pending: { label: "Pending / Delayed", color: "warning" },
  paid: { label: "Paid", color: "success" },
  partial: { label: "Partial", color: "warning" },
  overdue: { label: "Overdue", color: "danger" },
  failed: { label: "Failed to Pay (Loss)", color: "danger" },
  cancelled: { label: "Cancelled", color: "graphite" },
};

export const TICKET_STATUS_CONFIG = {
  open: { label: "Open", color: "info" },
  in_progress: { label: "In Progress", color: "warning" },
  waiting: { label: "Waiting", color: "warning" },
  resolved: { label: "Resolved", color: "success" },
  closed: { label: "Closed", color: "graphite" },
};

export const COLOR_CLASSES = {
  success: "bg-success/10 text-success border-success/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
  info: "bg-info/10 text-info border-info/30",
  graphite: "bg-graphite/10 text-ash border-graphite/30",
};
