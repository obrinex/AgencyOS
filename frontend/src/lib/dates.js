import { format, formatDistanceToNow } from "date-fns";

/**
 * date-fns throws a RangeError on an unparseable date rather than returning
 * "Invalid Date". Called during render with no error boundary above it, that
 * used to unmount the whole app - one malformed row blanked the page.
 *
 * A missing or malformed timestamp is a display problem, not a reason to lose
 * the screen. Show a dash and move on.
 */
function parse(value) {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function safeFormat(value, pattern, fallback = "—") {
  const date = parse(value);
  if (!date) return fallback;
  try {
    return format(date, pattern);
  } catch {
    return fallback;
  }
}

export function safeDistanceToNow(value, fallback = "—") {
  const date = parse(value);
  if (!date) return fallback;
  try {
    return formatDistanceToNow(date, { addSuffix: true });
  } catch {
    return fallback;
  }
}
