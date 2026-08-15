import { cn } from "@/lib/utils";

/**
 * The app's ground: a black field with a corner light, skewed streaks, a noise
 * grain and a dot lattice.
 *
 * Converted from the supplied .tsx — this codebase is pure JavaScript by
 * direction (see design_guidelines.json), so types are dropped rather than
 * carried in a file React would have to strip anyway.
 *
 * Four changes from the original, each marked LOCAL FIX below. Three of them
 * are things that would have bitten in production; the fourth is brand.
 */

/**
 * LOCAL FIX 1 — the grain is generated, not fetched.
 *
 * The original pointed `backgroundImage` at a PNG on framerusercontent.com.
 * On a CRM that is a third-party request on every page load, a referrer leak to
 * a CDN that has no business knowing our staff browse an invoicing tool, and a
 * hard dependency that shows a flat background the day it 404s.
 *
 * Fractal noise as an inline SVG data URI is the same texture, weighs about
 * 300 bytes, needs no network and cannot rot. `baseFrequency` sets the grain
 * size; 0.8 lands close to the original's 149.76px tile.
 */
const GRAIN =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="140" height="140">
       <filter id="n">
         <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" stitchTiles="stitch"/>
         <feColorMatrix type="saturate" values="0"/>
       </filter>
       <rect width="140" height="140" filter="url(#n)" opacity="0.55"/>
     </svg>`,
  );

/** The five streaks. Only the mask differs — each is a different rhythm of
 *  bands, which is what stops them reading as evenly spaced stripes. */
const STREAK_MASKS = [
  "linear-gradient(90deg, rgba(0,0,0,0) 0%, rgb(0,0,0) 20%, rgba(0,0,0,0) 36%, rgb(0,0,0) 55%, rgba(0,0,0,0.13) 67%, rgb(0,0,0) 78%, rgba(0,0,0,0) 97%)",
  "linear-gradient(90deg, rgba(0,0,0,0) 11%, rgb(0,0,0) 25%, rgba(0,0,0,0.55) 41%, rgba(0,0,0,0.13) 67%, rgb(0,0,0) 78%, rgba(0,0,0,0) 97%)",
  "linear-gradient(90deg, rgba(0,0,0,0) 9%, rgb(0,0,0) 20%, rgba(0,0,0,0.55) 28%, rgba(0,0,0,0.424) 40%, rgb(0,0,0) 48%, rgba(0,0,0,0.267) 54%, rgba(0,0,0,0.13) 78%, rgb(0,0,0) 88%, rgba(0,0,0,0) 97%)",
  "linear-gradient(90deg, rgba(0,0,0,0) 0%, rgb(0,0,0) 17%, rgba(0,0,0,0.55) 26%, rgb(0,0,0) 35%, rgba(0,0,0,0) 47%, rgba(0,0,0,0.13) 69%, rgb(0,0,0) 79%, rgba(0,0,0,0) 97%)",
  "linear-gradient(90deg, rgba(0,0,0,0) 0%, rgb(0,0,0) 20%, rgba(0,0,0,0.55) 27%, rgb(0,0,0) 42%, rgba(0,0,0,0) 48%, rgba(0,0,0,0.13) 67%, rgb(0,0,0) 74%, rgb(0,0,0) 82%, rgba(0,0,0,0.47) 88%, rgba(0,0,0,0) 97%)",
];

/**
 * @param {object}  props
 * @param {"mono"|"cyan"} [props.accent]  Streak colour. See LOCAL FIX 2.
 * @param {boolean} [props.fixed]         Pin to the viewport instead of flowing.
 * @param {number}  [props.dots]          Dot-lattice opacity, 0 to disable.
 */
export function DarkGradientBg({
  children,
  className,
  accent = "mono",
  fixed = false,
  dots = 0.1,
}) {
  /**
   * LOCAL FIX 2 — streaks default to white, not cyan.
   *
   * The original streaks are rgb(0,207,255). That is a colour, and both this
   * product and obrinex.space are monochrome by direction — and the brief one
   * message before this one was specifically "black and white gradient".
   *
   * So mono is the default and the cyan is kept intact one prop away:
   * `<DarkGradientBg accent="cyan" />` restores the supplied look exactly.
   */
  const streak =
    accent === "cyan"
      ? "linear-gradient(rgb(0,207,255) 0%, rgba(0,207,255,0) 100%)"
      : "linear-gradient(rgba(255,255,255,0.9) 0%, rgba(255,255,255,0) 100%)";

  // Mono streaks need to be fainter than coloured ones: white on black is far
  // higher contrast than cyan on black at the same alpha, and at 0.2 they
  // banded visibly across a page of text.
  const streakOpacity = accent === "cyan" ? 0.2 : 0.09;

  return (
    <div
      className={cn(
        "w-full overflow-hidden bg-black",
        // LOCAL FIX 3 — `fixed` mode. The original is `min-h-screen` and
        // scrolls with its content, which is right for a landing page and
        // wrong for an app: the gradient would slide away up a long table and
        // leave the bottom of the page flat black. Fixed, it belongs to the
        // viewport and every route sits on the same light.
        fixed ? "fixed inset-0 -z-10" : "relative min-h-screen",
        className,
      )}
      aria-hidden={fixed || undefined}
    >
      <div className="absolute inset-0">
        <div
          className="absolute inset-0 opacity-100"
          style={{
            background:
              "radial-gradient(100% 100% at 0% 0%, rgb(46,46,46) 0%, rgb(0,0,0) 100%)",
            WebkitMask:
              "radial-gradient(125% 100% at 0% 0%, rgb(0,0,0) 0%, rgba(0,0,0,0.224) 88.2883%, rgba(0,0,0,0) 100%)",
            mask: "radial-gradient(125% 100% at 0% 0%, rgb(0,0,0) 0%, rgba(0,0,0,0.224) 88.2883%, rgba(0,0,0,0) 100%)",
          }}
        >
          {STREAK_MASKS.map((maskImage, i) => (
            <div
              key={i}
              className="absolute inset-0"
              style={{
                opacity: streakOpacity,
                background: streak,
                // `WebkitMask` alongside `mask`: Safari still wants the prefix,
                // and without it the streaks render as five solid bars.
                WebkitMask: maskImage,
                mask: maskImage,
                transform: "skewX(45deg)",
              }}
            />
          ))}
        </div>
      </div>

      {/* Grain */}
      <div
        className="absolute inset-0 opacity-[0.06] bg-repeat"
        style={{ backgroundImage: `url("${GRAIN}")`, backgroundSize: "140px" }}
      />

      {/* Dot lattice. Dialled down from 0.2 and made a prop: at full strength
          it moirés against dense table rows, which is most of this product. */}
      {dots > 0 && (
        <div
          className="absolute inset-0"
          style={{
            opacity: dots,
            backgroundImage:
              "radial-gradient(circle at 1px 1px, rgba(255,255,255,0.5) 1px, transparent 0)",
            backgroundSize: "20px 20px",
          }}
        />
      )}

      {/* LOCAL FIX 4 — the radial highlight is an inline gradient.
          The original used `bg-gradient-radial`, which is not a Tailwind class
          and is not defined in this config, so the whole layer silently did
          nothing. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(60% 50% at 50% 0%, rgba(148,163,184,0.14), transparent 70%)",
        }}
      />

      {children && <div className="relative z-10">{children}</div>}
    </div>
  );
}

export default DarkGradientBg;
