import { useEffect, useMemo, useState } from "react";
import { Search, Linkedin, Instagram, Mail, Phone, Twitter, EyeOff, Users } from "lucide-react";
import api from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

/** Who is in the circle.
 *
 *  Each person is a card rather than a row because a directory of ten is read
 *  by browsing, not by scanning a column. What a member chose not to share is
 *  simply absent — the card never shows a greyed-out field, which would tell
 *  everyone that a private number exists.
 */

function hueOf(name = "") {
  let h = 0;
  for (let i = 0; i < name.length; i += 1) h = (h * 31 + name.charCodeAt(i)) % 360;
  return h;
}

const initials = (name = "?") =>
  name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";

const CHANNELS = [
  { key: "linkedin", label: "LinkedIn", icon: Linkedin, href: (v) => v },
  { key: "instagram", label: "Instagram", icon: Instagram, href: (v) => v },
  { key: "twitter", label: "X", icon: Twitter, href: (v) => v },
  { key: "email", label: "Email", icon: Mail, href: (v) => `mailto:${v}` },
  { key: "phone", label: "Phone", icon: Phone, href: (v) => `tel:${v}` },
];

function MemberCard({ person, index }) {
  const hue = hueOf(person.name || "");
  const links = CHANNELS.filter((c) => person[c.key]);

  return (
    <article
      style={{ animationDelay: `${index * 50}ms` }}
      data-testid={`founding-member-${person.id}`}
      className="obx-glass obx-lift obx-sheen obx-reveal relative rounded-2xl p-4 sm:p-5"
    >
      <div className="flex items-start gap-3">
        <div
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl font-mono text-sm font-semibold"
          style={{
            background: `linear-gradient(140deg, hsl(${hue} 62% 55% / 0.24), hsl(${(hue + 40) % 360} 62% 50% / 0.10))`,
            color: `hsl(${hue} 72% 80%)`,
            boxShadow: `inset 0 0 0 1px hsl(${hue} 60% 62% / 0.32)`,
          }}
        >
          {initials(person.name)}
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-base font-semibold tracking-tight">
            {person.name}
          </h3>
          {person.company && (
            <p className="truncate font-mono text-[10px] uppercase tracking-[0.16em] text-primary/75">
              {person.company}
            </p>
          )}
          {person.headline && (
            <p className="mt-1.5 text-sm leading-snug text-ash">{person.headline}</p>
          )}
        </div>
      </div>

      {person.bio && (
        <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-graphite">
          {person.bio}
        </p>
      )}

      {person.projects?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {person.projects.map((p, i) => (
            <span
              key={i}
              className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 text-[11px] text-ash"
            >
              {p.title}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 border-t border-white/[0.07] pt-3">
        {links.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {links.map((c) => (
              <a
                key={c.key}
                href={c.href(person[c.key])}
                target="_blank"
                rel="noopener noreferrer"
                title={c.label}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-ash transition-colors hover:border-primary/40 hover:text-primary"
              >
                <c.icon className="h-3 w-3" /> {c.label}
              </a>
            ))}
          </div>
        ) : (
          <p className="flex items-center gap-1.5 text-[11px] text-carbon">
            <EyeOff className="h-3 w-3" />
            Shares no contact details — reach them in the room.
          </p>
        )}
      </div>
    </article>
  );
}

export default function MemberDirectory() {
  const [people, setPeople] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.get("/founding/directory").then(({ data }) => setPeople(data)).catch(() => setPeople([]));
  }, []);

  const shown = useMemo(() => {
    if (!people) return [];
    const q = query.trim().toLowerCase();
    if (!q) return people;
    return people.filter((p) =>
      [p.name, p.company, p.headline, p.bio, ...(p.projects || []).map((x) => x.title)]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [people, query]);

  if (!people) return <Skeleton className="h-64 w-full rounded-2xl bg-surface-1" />;

  return (
    <div className="space-y-4" data-testid="founding-directory">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-graphite">
          The circle · {people.length}
        </p>
        <div className="obx-glass flex items-center gap-2 rounded-xl px-3 py-2 focus-within:border-primary/40 sm:w-64">
          <Search className="h-3.5 w-3.5 shrink-0 text-carbon" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the circle…"
            data-testid="founding-directory-search"
            className="w-full bg-transparent text-sm outline-none placeholder:text-carbon"
          />
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="obx-glass rounded-2xl px-6 py-12 text-center">
          <Users className="mx-auto h-5 w-5 text-carbon" />
          <p className="mt-2 text-sm text-graphite">Nobody matches “{query}”.</p>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {shown.map((p, i) => (
            <MemberCard key={p.id} person={p} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
