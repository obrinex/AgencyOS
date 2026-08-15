import { useEffect } from "react";
import { motion, AnimatePresence, LayoutGroup } from "framer-motion";
import { prefersReducedMotion } from "@/components/motion";

/** The navigation both portals share.
 *
 *  Two shapes, one vocabulary: a labelled rail on a desktop, a thumb-height tab
 *  bar on a phone. What makes it feel like one object rather than two menus is
 *  that the *active marker is a single element* — `layoutId` moves the same pill
 *  between items instead of fading one out and another in, so the eye follows a
 *  thing that travelled rather than noticing two things that blinked.
 *
 *  Everything here degrades to a still, correct layout under
 *  `prefers-reduced-motion`: the marker stops travelling and simply appears, the
 *  letters stop staggering. Nothing moves that a person asked not to move.
 */

const EASE = [0.16, 1, 0.3, 1];
const SPRING = { type: "spring", stiffness: 420, damping: 34, mass: 0.7 };

/** A label whose letters arrive one after another when the item becomes active.
 *
 *  Per-letter spans only exist while the item is active — a rail of nine items
 *  each permanently split into sixty spans is a lot of DOM for an effect nobody
 *  is looking at. Inactive items render as plain text.
 */
function AnimatedLabel({ text, active }) {
  const still = prefersReducedMotion();
  if (!active || still) return <span className="truncate">{text}</span>;
  return (
    <span className="truncate" aria-label={text}>
      {Array.from(text).map((char, i) => (
        <motion.span
          key={`${char}-${i}`}
          aria-hidden="true"
          initial={{ opacity: 0, y: -5, filter: "blur(3px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ delay: i * 0.018, duration: 0.24, ease: EASE }}
          style={{ display: "inline-block", whiteSpace: "pre" }}
        >
          {char}
        </motion.span>
      ))}
    </span>
  );
}

function Badge({ count }) {
  if (!count) return null;
  return (
    <motion.span
      initial={{ scale: 0.5, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={SPRING}
      className="obx-ping ml-auto flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-primary px-1 font-mono text-[10px] font-bold text-background"
    >
      {count > 9 ? "9+" : count}
    </motion.span>
  );
}

/* ── Desktop rail ─────────────────────────────────────────────────────────── */

/** One row. Split out because it renders in two quite different shapes — full
 *  width with a label, and a 40px square with a tooltip — and threading that
 *  through one JSX tree with ternaries made it unreadable. */
function RailItem({ item, index, active, collapsed, onSelect, groupId }) {
  return (
    <button
      onClick={() => onSelect(item.key)}
      data-testid={item.testId || `nav-${item.key}`}
      aria-current={active ? "page" : undefined}
      // The label is the accessible name when it is on screen; when collapsed
      // there is no text at all, so the icon needs one of its own.
      aria-label={collapsed ? item.label : undefined}
      title={undefined}
      className={`group relative flex w-full items-center rounded-xl text-sm ${
        collapsed ? "h-10 justify-center" : "gap-2.5 px-3 py-2"
      }`}
    >
      {/* The one marker, travelling. */}
      {active && (
        <motion.span
          layoutId={`${groupId}-marker`}
          transition={SPRING}
          className="absolute inset-0 rounded-xl border border-primary/25 bg-gradient-to-r from-primary/[0.14] to-primary/[0.04]"
        />
      )}
      {active && !collapsed && (
        <motion.span
          layoutId={`${groupId}-edge`}
          transition={SPRING}
          className="absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-primary"
        />
      )}

      {/* The index is also the shortcut. Printing a number beside a row and
          giving it no meaning is decoration; this one is the key you press. */}
      {!collapsed && (
        <span
          className={`obx-figure relative z-10 w-[18px] shrink-0 text-left font-mono text-[9px] transition-colors ${
            active ? "text-primary/80" : "text-carbon group-hover:text-graphite"
          }`}
        >
          {String(index + 1).padStart(2, "0")}
        </span>
      )}

      <motion.span
        className="relative z-10 shrink-0"
        animate={active ? { scale: 1.06 } : { scale: 1 }}
        transition={SPRING}
      >
        <item.icon
          className={`h-4 w-4 transition-colors ${
            active ? "text-primary" : "text-ash group-hover:text-foreground"
          }`}
        />
        {/* Collapsed, there is no room for a count — so a badge becomes a dot,
            which still answers "something happened here". */}
        {collapsed && item.badge > 0 && (
          <span className="obx-ping absolute -right-1.5 -top-1 h-2 w-2 rounded-full bg-primary text-primary" />
        )}
      </motion.span>

      {!collapsed && (
        <>
          <span
            className={`relative z-10 min-w-0 flex-1 text-left transition-colors ${
              active ? "font-medium text-foreground" : "text-ash group-hover:text-foreground"
            }`}
          >
            <AnimatedLabel text={item.label} active={active} />
          </span>
          <span className="relative z-10 flex items-center">
            <Badge count={item.badge} />
          </span>
        </>
      )}

      {/* Collapsed tooltip. CSS-only on hover/focus rather than a portal: a
          floating-element library for nine labels in a fixed-width rail is a
          dependency to keep patched forever. */}
      {collapsed && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-[calc(100%+10px)] z-50 flex items-center gap-2 whitespace-nowrap rounded-lg border border-white/10 bg-black/90 px-2.5 py-1.5 text-xs opacity-0 shadow-xl backdrop-blur-xl transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
        >
          {item.label}
          <kbd className="obx-figure rounded border border-white/12 bg-white/[0.06] px-1 font-mono text-[9px] text-carbon">
            {index + 1}
          </kbd>
        </span>
      )}
    </button>
  );
}

/**
 * The rail.
 *
 * `items` may carry a `group`. When they do, the rail is ruled into named
 * sections — nine flat rows is a pile you read top to bottom every time, and
 * three groups of three is a shape you learn once. Items with no `group` render
 * flat, which is what the client portal still does.
 *
 * `collapsed` narrows it to icons with tooltips. The members' rail carries nine
 * sections and cannot honestly fit under `lg`; collapsing is what lets a laptop
 * or a tablet keep a rail at all instead of falling back to the phone tab bar.
 */
export function NavRail({
  items,
  activeKey,
  onSelect,
  groupId = "portal-rail",
  collapsed = false,
}) {
  const grouped = items.some((i) => i.group);

  // Rendered as a flat sequence with headers injected, rather than as nested
  // lists, so the shortcut index and the travelling marker both stay defined
  // over one continuous order.
  const rows = [];
  let lastGroup = null;
  items.forEach((item, index) => {
    if (grouped && item.group !== lastGroup) {
      lastGroup = item.group;
      rows.push(
        collapsed ? (
          <div key={`sep-${item.group}`} className="mx-auto my-2 h-px w-6 bg-white/[0.08]" />
        ) : (
          <p
            key={`hdr-${item.group}`}
            className="px-3 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.22em] text-carbon first:pt-1"
          >
            {item.group}
          </p>
        )
      );
    }
    rows.push(
      <RailItem
        key={item.key}
        item={item}
        index={index}
        active={item.key === activeKey}
        collapsed={collapsed}
        onSelect={onSelect}
        groupId={groupId}
      />
    );
  });

  return (
    <LayoutGroup id={groupId}>
      <nav
        aria-label="Sections"
        className={`flex-1 overflow-y-auto overflow-x-visible ${
          collapsed ? "space-y-1 px-2 py-2.5" : "space-y-0.5 p-2.5"
        }`}
      >
        {rows}
      </nav>
    </LayoutGroup>
  );
}

/**
 * Number keys jump to a section, so the numerals printed in the rail mean
 * something. Bound at the document, ignored while typing — a member writing
 * "I need 4 more weeks" in the community room must not be thrown to section 4.
 */
export function useNavShortcuts(items, onSelect, { enabled = true } = {}) {
  useEffect(() => {
    if (!enabled) return undefined;
    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
      const el = e.target;
      const typing =
        el instanceof HTMLElement &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable);
      if (typing) return;
      const n = Number(e.key);
      if (!Number.isInteger(n) || n < 1 || n > items.length) return;
      e.preventDefault();
      onSelect(items[n - 1].key);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [items, onSelect, enabled]);
}

/* ── Phone tab bar ────────────────────────────────────────────────────────── */

/** `hideFrom` is the breakpoint at which the rail takes over and the bar goes
 *  away. The two portals switch at different widths — the client rail fits at
 *  `md`, the members' nine-item rail needs `lg` — so it is a prop rather than a
 *  hardcoded class that would be wrong for one of them. */
export function TabBar({ items, activeKey, onSelect, groupId = "portal-tabs", testId,
                        hideFrom = "lg" }) {
  return (
    <LayoutGroup id={groupId}>
      <nav
        data-testid={testId}
        className={`pb-safe fixed inset-x-0 bottom-0 z-40 border-t border-white/[0.09] bg-black/85 px-1 pt-1.5 backdrop-blur-2xl ${hideFrom === "md" ? "md:hidden" : "lg:hidden"}`}
        style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))`, display: "grid" }}
      >
        {items.map((item) => {
          const active = item.key === activeKey;
          return (
            <button
              key={item.key}
              onClick={() => onSelect(item.key)}
              data-testid={item.testId || `tab-${item.key}`}
              aria-current={active ? "page" : undefined}
              className={`relative flex flex-col items-center gap-1 rounded-lg py-1.5 text-[10px] transition-colors ${
                active ? "text-primary" : "text-carbon"
              }`}
            >
              {active && (
                <motion.span
                  layoutId={`${groupId}-marker`}
                  transition={SPRING}
                  className="absolute inset-x-2 -top-1.5 h-[2px] rounded-full bg-primary"
                />
              )}
              {active && (
                <motion.span
                  layoutId={`${groupId}-glow`}
                  transition={SPRING}
                  className="absolute inset-x-3 top-0 h-8 rounded-full bg-primary/12 blur-md"
                />
              )}

              <motion.span
                className="relative"
                animate={active ? { y: -1, scale: 1.1 } : { y: 0, scale: 1 }}
                transition={SPRING}
              >
                <item.icon className="h-[18px] w-[18px]" />
                {item.badge > 0 && (
                  <span className="obx-ping absolute -right-1.5 -top-1 h-2 w-2 rounded-full bg-primary text-primary" />
                )}
              </motion.span>

              <span className="relative">{item.short || item.label}</span>
            </button>
          );
        })}
      </nav>
    </LayoutGroup>
  );
}

/* ── The overflow sheet ───────────────────────────────────────────────────── */

export function MoreSheet({ open, items, activeKey, onSelect, onClose, title = "Everything else",
                           hideFrom = "lg" }) {
  return (
    <AnimatePresence>
      {open && (
        <div className={`fixed inset-0 z-50 ${hideFrom === "md" ? "md:hidden" : "lg:hidden"}`} data-testid="portal-more-sheet">
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            aria-label="Close menu"
            onClick={onClose}
            className="absolute inset-0 bg-black/75 backdrop-blur-sm"
          />
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ duration: 0.34, ease: EASE }}
            className="obx-glass pb-safe absolute inset-x-0 bottom-0 rounded-t-3xl p-4"
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-white/15" />
            <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
              {title}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {items.map((item, i) => (
                <motion.button
                  key={item.key}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 + i * 0.035, ease: EASE }}
                  onClick={() => onSelect(item.key)}
                  data-testid={`more-${item.key}`}
                  className={`obx-glass obx-lift flex items-center gap-2.5 rounded-xl px-3 py-3 text-sm ${
                    item.key === activeKey ? "border-primary/35 text-primary" : "text-ash"
                  }`}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  <span className="min-w-0 flex-1 truncate text-left">{item.label}</span>
                  <Badge count={item.badge} />
                </motion.button>
              ))}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
