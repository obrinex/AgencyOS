import { Component } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Catches render-time exceptions and shows them instead of blanking the app.
 *
 * Without a boundary anywhere in the tree, React's behaviour on an uncaught
 * render error is to unmount *everything* - so a single bad field in a single
 * row takes out the entire page, sidebar included, with no message anywhere
 * the user can see it. That is indistinguishable from "the page is broken"
 * and gives nobody a thread to pull.
 *
 * Two real examples this catches, both live in this codebase:
 *   - `format(new Date(e.date), ...)` - date-fns throws RangeError on an
 *     unparseable date, so one malformed expense row blanked Finance.
 *   - `log.steps.map(...)` - an older automation_log without `steps` blanked
 *     Automations.
 *
 * Guarding those two call sites individually is still worth doing, and is
 * done. This exists because the next one has not been written yet.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Kept: this is the only trace of what happened once the tree unmounts.
    console.error("Render error:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="p-6" data-testid="error-boundary">
        <div className="flex flex-col items-center justify-center rounded-xl border border-danger/25 bg-danger/5 py-16 px-6 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-2 border border-danger/25">
            <AlertTriangle className="h-6 w-6 text-danger" />
          </div>
          <h3 className="font-display text-lg font-semibold text-foreground">
            This page hit an error
          </h3>
          <p className="mt-1.5 max-w-md text-sm text-graphite">
            The rest of the app is fine — you can navigate away using the menu.
          </p>
          <code
            data-testid="error-boundary-message"
            className="mt-4 max-w-lg overflow-x-auto rounded-md border border-white/10 bg-surface-2 px-3 py-2 text-left font-mono text-xs text-ash"
          >
            {this.state.error?.message || String(this.state.error)}
          </code>
          <Button
            onClick={() => this.setState({ error: null })}
            size="sm" variant="outline"
            className="mt-5 gap-1.5 border-white/10"
            data-testid="error-boundary-retry"
          >
            <RotateCw className="h-3.5 w-3.5" /> Try again
          </Button>
        </div>
      </div>
    );
  }
}
