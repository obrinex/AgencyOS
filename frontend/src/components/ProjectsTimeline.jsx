import { useNavigate } from "react-router-dom";
import { differenceInCalendarDays, addDays, format } from "date-fns";
import StatusBadge from "@/components/StatusBadge";
import { PROJECT_STATUS_CONFIG } from "@/lib/statusConfig";

const COLOR_BAR = {
  planning: "bg-graphite", onboarding: "bg-info", development: "bg-info", automation: "bg-info",
  testing: "bg-warning", review: "bg-warning", waiting_client: "bg-warning", completed: "bg-success", archived: "bg-graphite",
};

export default function ProjectsTimeline({ projects }) {
  const navigate = useNavigate();

  const withDates = projects.map((p) => ({
    ...p,
    start: new Date(p.start_date || p.created_at),
    end: p.end_date ? new Date(p.end_date) : addDays(new Date(p.start_date || p.created_at), 21),
  }));

  if (withDates.length === 0) return null;

  const rangeStart = new Date(Math.min(...withDates.map((p) => p.start.getTime())));
  const rangeEnd = new Date(Math.max(...withDates.map((p) => p.end.getTime())));
  const totalDays = Math.max(differenceInCalendarDays(rangeEnd, rangeStart), 7) + 7;

  const weeks = [];
  for (let d = 0; d <= totalDays; d += 7) weeks.push(addDays(rangeStart, d));

  return (
    <div className="rounded-xl border border-white/10 bg-surface-1/60 overflow-x-auto" data-testid="projects-timeline-chart">
      <div className="min-w-[800px]">
        <div className="flex border-b border-white/10 sticky top-0 bg-surface-1">
          <div className="w-48 shrink-0 px-3 py-2 font-mono text-[10px] uppercase text-graphite">Project</div>
          <div className="flex-1 flex">
            {weeks.map((w, i) => (
              <div key={i} className="flex-1 px-1 py-2 text-center font-mono text-[10px] text-carbon border-l border-white/5">
                {format(w, "MMM d")}
              </div>
            ))}
          </div>
        </div>
        {withDates.map((p) => {
          const offsetDays = differenceInCalendarDays(p.start, rangeStart);
          const durationDays = Math.max(differenceInCalendarDays(p.end, p.start), 2);
          const leftPct = (offsetDays / totalDays) * 100;
          const widthPct = (durationDays / totalDays) * 100;
          return (
            <div key={p.id} className="flex items-center border-b border-white/5 hover:bg-surface-2/50">
              <div className="w-48 shrink-0 px-3 py-3 flex items-center gap-2 min-w-0">
                <span className="text-sm truncate">{p.name}</span>
              </div>
              <div className="flex-1 relative h-10">
                <div
                  data-testid={`timeline-bar-${p.id}`}
                  onClick={() => navigate(`/projects/${p.id}`)}
                  className={`absolute top-2 h-6 rounded-md cursor-pointer opacity-80 hover:opacity-100 transition-opacity ${COLOR_BAR[p.status] || "bg-graphite"}`}
                  style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 4)}%` }}
                  title={`${p.name}: ${format(p.start, "MMM d")} - ${format(p.end, "MMM d")}`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
