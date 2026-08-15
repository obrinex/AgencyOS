import { Reveal } from "@/components/motion";

/**
 * The heading every page opens with.
 *
 * Rebuilt to carry obrinex.space's typographic voice, because this is the one
 * component that appears on all 55 pages — changing it changes the whole
 * product's first impression, and leaving it alone means nothing else can rescue
 * the feel.
 *
 * Three things it borrows from the site:
 *
 *  · A mono eyebrow above the title, at 10px with 0.2em tracking. The site uses
 *    the same device on every section. It costs one line and it is most of what
 *    makes a page read as composed rather than as a dump of data.
 *  · A hairline that draws itself in beneath the header. The site rules its
 *    sections off; a static border reads as chrome, one that arrives reads as
 *    the page being set.
 *  · A display title with negative tracking, sized up from `text-2xl`. Archivo
 *    is wide, and at 2xl with default tracking it looked like body copy in bold
 *    rather than like a heading.
 */
export default function PageHeader({ title, description, actions, eyebrow, testId }) {
  return (
    <div data-testid={testId} className="px-6 pt-6 pb-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <Reveal>
          {eyebrow && (
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-carbon">
              {eyebrow}
            </p>
          )}
          <h1 className="font-display text-[1.75rem] font-bold leading-[1.1] tracking-[-0.02em] text-foreground">
            {title}
          </h1>
          {description && (
            <p className="mt-2 max-w-[62ch] text-sm leading-relaxed text-graphite">
              {description}
            </p>
          )}
        </Reveal>
        {actions && (
          <Reveal delay={60} className="flex shrink-0 items-center gap-2">
            {actions}
          </Reveal>
        )}
      </div>

      {/* Scales in from the left rather than simply being there. */}
      <div className="obx-rule mt-5 h-px w-full bg-gradient-to-r from-white/20 via-white/10 to-transparent" />
    </div>
  );
}
