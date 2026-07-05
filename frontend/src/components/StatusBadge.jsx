import { cn } from "@/lib/utils";
import { COLOR_CLASSES } from "@/lib/statusConfig";

export default function StatusBadge({ config, value, testId }) {
  const item = config[value] || { label: value, color: "graphite" };
  return (
    <span
      data-testid={testId}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-mono uppercase tracking-wide whitespace-nowrap",
        COLOR_CLASSES[item.color] || COLOR_CLASSES.graphite
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", {
        "bg-success": item.color === "success",
        "bg-warning": item.color === "warning",
        "bg-danger": item.color === "danger",
        "bg-info": item.color === "info",
        "bg-graphite": item.color === "graphite",
      })} />
      {item.label}
    </span>
  );
}
