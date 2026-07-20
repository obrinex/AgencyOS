import { STAGE_CONFIG } from "@/lib/statusConfig";

/**
 * `archived` deliberately lives here rather than in STAGE_CONFIG.
 *
 * CRMPipeline renders one Kanban column per STAGES_LIST entry, and an
 * archived lead has been removed from the working set - it should not occupy
 * a column on the active board. Keeping it in an SDR-only config gives the
 * SDR pages a complete label map without changing the CRM board.
 */
export const SDR_STAGE_CONFIG = {
  ...STAGE_CONFIG,
  archived: { label: "Archived", color: "graphite" },
};

export const QUALIFICATION_CONFIG = {
  qualified: { label: "Qualified", color: "success" },
  needs_review: { label: "Needs Review", color: "warning" },
  unqualified: { label: "Unqualified", color: "graphite" },
  disqualified: { label: "Disqualified", color: "danger" },
};

export const ENRICHMENT_CONFIG = {
  pending: { label: "Pending", color: "graphite" },
  partial: { label: "Partial", color: "warning" },
  complete: { label: "Complete", color: "success" },
  failed: { label: "Failed", color: "danger" },
};

/** Score bands used for the colour of the score pill. */
export function scoreColor(score) {
  if (score >= 70) return "text-success";
  if (score >= 55) return "text-info";
  if (score >= 40) return "text-warning";
  return "text-graphite";
}

/**
 * Inbound reply categories.
 *
 * `machine: true` marks the two that must never read as engagement. The UI
 * leans on this rather than a colour: an out-of-office rendered like a real
 * reply is how someone concludes a dead lead answered them.
 */
export const INBOUND_CATEGORY_CONFIG = {
  interested: { label: "Interested", color: "success", machine: false },
  not_now: { label: "Not now", color: "warning", machine: false },
  objection: { label: "Objection", color: "warning", machine: false },
  wrong_person: { label: "Wrong person", color: "info", machine: false },
  out_of_office: { label: "Out of office", color: "graphite", machine: true },
  auto_reply: { label: "Auto-reply", color: "graphite", machine: true },
  unsubscribe_request: { label: "Unsubscribe", color: "danger", machine: false },
  bounce: { label: "Bounce", color: "danger", machine: false },
};

/** Pill classes for an inbound category, matching the SDR micro-pill idiom. */
export const INBOUND_CATEGORY_STYLE = {
  interested: "bg-success/15 text-success",
  not_now: "bg-warning/15 text-warning",
  objection: "bg-warning/15 text-warning",
  wrong_person: "bg-info/15 text-info",
  out_of_office: "bg-surface-3 text-graphite",
  auto_reply: "bg-surface-3 text-graphite",
  unsubscribe_request: "bg-danger/15 text-danger",
  bounce: "bg-danger/15 text-danger",
};

/** How a reply was tied back to what we sent. */
export const MATCH_METHOD_CONFIG = {
  threaded: { label: "Threaded", hint: "Matched on the Message-ID we sent — exact." },
  sender: { label: "By sender", hint: "Threading headers were missing; matched on the from-address, which cannot tell two campaigns apart." },
  none: { label: "Unmatched", hint: "Nobody could route this reply. Someone answered and is waiting." },
};
