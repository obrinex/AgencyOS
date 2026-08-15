import { useEffect, useState } from "react";
import { Plus, Trash2, Loader2, Eye, EyeOff, IdCard, Hammer, Contact } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

/** What the rest of the circle sees.
 *
 *  Editing this never touches the application — that record is fixed. Contact
 *  details are opt-in one field at a time, and the switch says which state it
 *  is in rather than leaving a bare checkbox to be interpreted.
 */

const SHARE_FIELDS = [
  { key: "email", label: "Email", placeholder: "you@company.com" },
  { key: "phone", label: "Phone", placeholder: "+91…" },
  { key: "linkedin", label: "LinkedIn", placeholder: "https://linkedin.com/in/…" },
  { key: "instagram", label: "Instagram", placeholder: "https://instagram.com/…" },
  { key: "twitter", label: "X / Twitter", placeholder: "https://x.com/…" },
];

const field =
  "obx-glass w-full rounded-xl px-3 py-2 text-sm outline-none focus:border-primary/40 placeholder:text-carbon";

function Section({ icon: Icon, title, description, action, children }) {
  return (
    <section className="obx-glass rounded-2xl p-4 sm:p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary ring-1 ring-primary/25">
            <Icon className="h-4 w-4" />
          </div>
          <div>
            <h2 className="font-display font-semibold tracking-tight">{title}</h2>
            {description && (
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-graphite">{description}</p>
            )}
          </div>
        </div>
        {action}
      </header>
      <div className="mt-4 space-y-3">{children}</div>
    </section>
  );
}

/** A switch that reads as a sentence. A bare checkbox next to a phone number
 *  does not say whether ticking it publishes the number or hides it. */
function ShareToggle({ on, onChange, testId }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      data-testid={testId}
      className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2 py-1 text-[10px] font-medium transition-colors ${
        on
          ? "border-primary/35 bg-primary/12 text-primary"
          : "border-white/10 bg-white/[0.03] text-carbon hover:text-ash"
      }`}
    >
      {on ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
      {on ? "Shared" : "Hidden"}
    </button>
  );
}

export default function MemberProfile() {
  const [p, setP] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    api.get("/founding/profile").then(({ data }) => setP(data)).catch(() => setP(false));
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.put("/founding/profile", {
        headline: p.headline, bio: p.bio, email: p.email, phone: p.phone,
        linkedin: p.linkedin, instagram: p.instagram, twitter: p.twitter,
        projects: (p.projects || []).filter((x) => x.title?.trim()),
        visibility: p.visibility, listed: p.listed,
      });
      setP(data);
      setDirty(false);
      toast.success("Saved.");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  if (p === null) return <Skeleton className="h-96 w-full rounded-2xl bg-surface-1" />;
  if (p === false) {
    return (
      <div className="obx-glass rounded-2xl p-6 text-sm text-graphite">Profile unavailable.</div>
    );
  }

  const set = (patch) => { setP({ ...p, ...patch }); setDirty(true); };
  const setProject = (i, patch) => {
    const projects = [...(p.projects || [])];
    projects[i] = { ...projects[i], ...patch };
    set({ projects });
  };

  return (
    <div className="space-y-4 pb-24 sm:pb-4" data-testid="founding-profile">
      <Section
        icon={IdCard}
        title="You"
        description="The line and the paragraph other members read first."
      >
        <label className="block">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
            One line about what you do
          </span>
          <input
            value={p.headline || ""}
            onChange={(e) => set({ headline: e.target.value })}
            data-testid="founding-profile-headline"
            className={`mt-1.5 ${field}`}
          />
        </label>
        <label className="block">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
            Anything else worth knowing
          </span>
          <textarea
            rows={4}
            value={p.bio || ""}
            onChange={(e) => set({ bio: e.target.value })}
            className={`mt-1.5 resize-y ${field}`}
          />
        </label>
      </Section>

      <Section
        icon={Hammer}
        title="What you're building"
        description="Everything here shows on the circle's Projects board."
        action={
          <button
            onClick={() => set({ projects: [...(p.projects || []), { title: "", summary: "", status: "", link: "" }] })}
            data-testid="founding-profile-add-project"
            className="obx-glass obx-lift flex shrink-0 items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs"
          >
            <Plus className="h-3.5 w-3.5" /> Add
          </button>
        }
      >
        {(p.projects || []).length === 0 && (
          <p className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-graphite">
            Nothing yet. What you add here is what the circle sees.
          </p>
        )}
        {(p.projects || []).map((pr, i) => (
          <div key={i} className="obx-glass space-y-2 rounded-xl p-3">
            <div className="flex gap-2">
              <input
                value={pr.title || ""}
                placeholder="Project"
                onChange={(e) => setProject(i, { title: e.target.value })}
                className={field}
              />
              <input
                value={pr.status || ""}
                placeholder="Status"
                onChange={(e) => setProject(i, { status: e.target.value })}
                className={`w-28 shrink-0 ${field}`}
              />
              <button
                onClick={() => set({ projects: p.projects.filter((_, n) => n !== i) })}
                aria-label="Remove project"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-carbon transition-colors hover:bg-white/[0.06] hover:text-danger"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <input
              value={pr.summary || ""}
              placeholder="One line"
              onChange={(e) => setProject(i, { summary: e.target.value })}
              className={field}
            />
            <input
              value={pr.link || ""}
              placeholder="Link (optional)"
              onChange={(e) => setProject(i, { link: e.target.value })}
              className={field}
            />
          </div>
        ))}
      </Section>

      <Section
        icon={Contact}
        title="Contact details"
        description="Each of these is hidden from other members until you share it. Your name, company and projects are always visible."
      >
        {SHARE_FIELDS.map((f) => (
          <div key={f.key} className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <span className="w-24 shrink-0 font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
              {f.label}
            </span>
            <input
              value={p[f.key] || ""}
              placeholder={f.placeholder}
              onChange={(e) => set({ [f.key]: e.target.value })}
              className={field}
            />
            <ShareToggle
              on={!!p.visibility?.[f.key]}
              onChange={(next) => set({ visibility: { ...p.visibility, [f.key]: next } })}
              testId={`founding-share-${f.key}`}
            />
          </div>
        ))}

        <label className="flex items-center gap-2.5 border-t border-white/[0.07] pt-3 text-sm">
          <input
            type="checkbox"
            checked={p.listed !== false}
            onChange={(e) => set({ listed: e.target.checked })}
            data-testid="founding-listed"
            className="h-4 w-4 accent-primary"
          />
          List me in the directory
        </label>
      </Section>

      {/* Sticky on a phone, where the save button would otherwise be three
          screens below whatever was just typed. Sits on the floor now — it was
          offset by 14 to clear a bottom tab bar that no longer exists. */}
      <div className="pb-safe fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-black/70 px-4 py-3 backdrop-blur-xl sm:static sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
        <button
          onClick={save}
          disabled={busy || !dirty}
          data-testid="founding-profile-save"
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-background transition-opacity disabled:opacity-40 sm:w-auto"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {dirty ? "Save changes" : "Saved"}
        </button>
      </div>
    </div>
  );
}
