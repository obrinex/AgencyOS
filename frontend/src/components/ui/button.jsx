import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/**
 * Buttons, rebuilt against obrinex.space.
 *
 * Three things the site's controls do that these did not:
 *
 *  · **They invert.** The primary control is paper-on-ink and flips to
 *    ink-on-paper. It is the only filled element on a monochrome page, which is
 *    what makes it read as the thing to press without needing a colour.
 *  · **They lift.** A 1px rise on hover and a press back down on click. Real
 *    buttons move; the old ones only changed opacity, which reads as a state
 *    change rather than as a physical control.
 *  · **They have a sheen.** A soft highlight sweeps across on hover — the
 *    liquid-glass gesture from the site's LiquidButton, reduced to something a
 *    toolbar can wear thirty times over.
 *
 * Shadows are gone throughout. On a true-black ground Tailwind's default shadow
 * is a muddy smear that fights the hairline beside it, and the Swiss direction
 * rules them out anyway — the affordance is the border and the movement.
 *
 * `rounded-full` on the pill sizes, matching the site. Radix `asChild` still
 * works, so every existing call site keeps behaving.
 */
const buttonVariants = cva(
  cn(
    "group relative inline-flex items-center justify-center gap-2 overflow-hidden whitespace-nowrap",
    "rounded-lg text-sm font-medium",
    // Transform is in the transition list so the lift is animated, not snapped.
    "transition-[background-color,border-color,color,transform] duration-200 ease-out",
    "active:translate-y-0",
    "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
    "disabled:pointer-events-none disabled:opacity-40",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
    // Icons inside a button drift a hair in the reading direction on hover.
    "[&_svg]:transition-transform [&_svg]:duration-300 hover:[&_svg:last-child]:translate-x-0.5",
  ),
  {
    variants: {
      variant: {
        default:
          "bg-foreground text-background hover:-translate-y-px hover:bg-white",
        destructive:
          "bg-danger text-white hover:-translate-y-px hover:bg-danger/90",
        outline:
          "border border-white/15 bg-white/[0.02] hover:-translate-y-px hover:border-white/40 hover:bg-white/[0.06]",
        secondary:
          "border border-white/10 bg-white/[0.06] hover:-translate-y-px hover:bg-white/[0.1]",
        ghost: "hover:bg-white/[0.06] hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-7",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, children, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  const sheen = (
    // -skew so the highlight reads as a swipe rather than a wipe. Sits under
    // the label (`-z-0` would escape the stacking context, so the content is
    // lifted instead) and never eats a click.
    <span
      aria-hidden
      className="pointer-events-none absolute inset-0 -translate-x-[120%] -skew-x-12 bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 ease-out group-hover:translate-x-[120%]"
    />
  )
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}>
      {/* asChild hands its single child straight through, so the sheen can only
          be added when this renders its own element. */}
      {asChild ? children : (<>{sheen}<span className="relative inline-flex items-center gap-2">{children}</span></>)}
    </Comp>
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
