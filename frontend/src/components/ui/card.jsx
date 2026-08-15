import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * `obx-panel` gives every panel in the product a lit top edge — a gradient
 * hairline, brightest in the middle — instead of a uniform border. A uniform
 * border reads as a box; an edge that catches light reads as a surface, which
 * is the whole difference between the CRM looking like a wireframe and looking
 * like the website's sections.
 *
 * Applied here rather than per page on purpose: it is one edit that reaches all
 * 55 pages, and it cannot drift out of sync with itself.
 *
 * `shadow` is dropped. Shadows are explicitly out under the Swiss/high-contrast
 * direction, and on a #131315 surface Tailwind's default shadow renders as a
 * muddy smear that fights the hairline it sits next to.
 */
const Card = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "obx-panel overflow-hidden rounded-xl border border-white/10 bg-white/[0.028] text-card-foreground backdrop-blur-sm",
      className
    )}
    {...props} />
))
Card.displayName = "Card"

const CardHeader = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-1.5 p-6", className)}
    {...props} />
))
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("font-semibold leading-none tracking-tight", className)}
    {...props} />
))
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props} />
))
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex items-center p-6 pt-0", className)}
    {...props} />
))
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent }
