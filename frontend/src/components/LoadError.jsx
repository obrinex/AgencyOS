import { motion } from "framer-motion";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Shown when a page's initial data load fails.
 *
 * The pattern this replaces: `useState(null)` + a fetch with no catch +
 * `if (!data) return <Skeleton/>`. When the request fails the state never
 * leaves null, so the page renders a loading skeleton forever - it looks
 * identical to "still loading" and to "empty", and the rejection is
 * unhandled, so nothing reaches the console either.
 *
 * A page that cannot load must say so. Showing the server's own message
 * matters more than it looks: it is usually the only place the real cause
 * (expired session, 500, unreachable backend) is visible to anyone who is
 * not holding devtools open.
 */
export default function LoadError({ message, onRetry, testId = "load-error" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      data-testid={testId}
      className="flex flex-col items-center justify-center rounded-xl border border-danger/25 bg-danger/5 py-20 px-6 text-center"
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-2 border border-danger/25">
        <AlertTriangle className="h-6 w-6 text-danger" />
      </div>
      <h3 className="font-display text-lg font-semibold text-foreground">
        Couldn't load this page
      </h3>
      <p className="mt-1.5 max-w-md text-sm text-graphite" data-testid={`${testId}-message`}>
        {message}
      </p>
      {onRetry && (
        <Button
          onClick={onRetry}
          size="sm"
          variant="outline"
          className="mt-5 gap-1.5 border-white/10"
          data-testid={`${testId}-retry`}
        >
          <RotateCw className="h-3.5 w-3.5" /> Try again
        </Button>
      )}
    </motion.div>
  );
}
