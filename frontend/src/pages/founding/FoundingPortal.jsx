import { useEffect, useRef, useState } from "react";
import {
  MessageSquare, Sparkles, Send, Loader2, LogOut, FolderKanban, Users,
  UserPlus, BookOpen, HelpCircle, IdCard, Plus, Trash2, Copy, Check,
} from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { GUIDELINES, FAQ } from "./foundingContent";

/** The Founding Circle's own portal.
 *
 *  Deliberately not the client portal. A member has their own role, so the
 *  client routes are unreachable from here and these are unreachable from
 *  there — the separation is enforced by the API, not by hiding links.
 *
 *  Seven sections rather than the original two. The room and the assistant were
 *  the whole portal, which made membership feel like a group chat with a bot
 *  attached; the directory, the projects page and referrals are the parts that
 *  make it a network rather than a channel.
 */
const TABS = [
  { key: "chat", label: "Community", icon: MessageSquare },
  { key: "projects", label: "Projects", icon: FolderKanban },
  { key: "directory", label: "Members", icon: Users },
  { key: "refer", label: "Refer", icon: UserPlus },
  { key: "profile", label: "Profile", icon: IdCard },
  { key: "guidelines", label: "Guidelines", icon: BookOpen },
  { key: "help", label: "Help", icon: HelpCircle },
  { key: "assistant", label: "Assistant", icon: Sparkles },
];

export default function FoundingPortal() {
  const { user, logout } = useAuth();
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState("chat");

  useEffect(() => {
    api.get("/founding/me").then(({ data }) => setMe(data)).catch(() => setMe(false));
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-white/10 px-6 py-4">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="font-display text-lg font-bold tracking-tight">Founding Circle</h1>
            <p className="text-xs text-graphite">
              {me ? `${me.members} member${me.members === 1 ? "" : "s"}` : " "}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-sm text-graphite">{user?.name}</span>
            <Button size="icon" variant="ghost" onClick={logout} data-testid="founding-logout">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {/* Scrolls on a phone rather than wrapping into two ragged rows. */}
        <nav className="mt-3 -mb-1 flex items-center gap-1 overflow-x-auto pb-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              data-testid={`founding-tab-${t.key}`}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                tab === t.key ? "bg-surface-2 text-foreground" : "text-ash hover:bg-surface-1"
              }`}
            >
              <t.icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="p-6 max-w-3xl mx-auto">
        {tab === "chat" && <CommunityChat />}
        {tab === "projects" && <Projects />}
        {tab === "directory" && <Directory />}
        {tab === "refer" && <Referrals />}
        {tab === "profile" && <Profile />}
        {tab === "guidelines" && <Guidelines />}
        {tab === "help" && <Help />}
        {tab === "assistant" && <Assistant />}
      </main>
    </div>
  );
}

/* -------------------------------------------------------------- community */

function CommunityChat() {
  const [messages, setMessages] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/founding/chat");
    setMessages(data);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async () => {
    if (!text.trim()) return;
    setSending(true);
    try {
      await api.post("/founding/chat", { body: text });
      setText("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setSending(false); }
  };

  if (!messages) return <Skeleton className="h-96 bg-surface-1" />;

  return (
    <Card className="bg-surface-1 border-white/10 flex flex-col h-[70vh]" data-testid="founding-chat">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="text-sm text-graphite text-center py-12">
            Nothing here yet. One room — say something.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className="rounded-lg bg-surface-2 border border-white/10 p-3">
            <p className="text-[11px] text-graphite">
              {m.author_name}
              {m.author_company ? ` · ${m.author_company}` : ""}
            </p>
            <p className="mt-1 text-sm whitespace-pre-line break-words">{m.body}</p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-white/10 p-3 flex items-center gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Message the circle…"
          className="bg-surface-2 border-white/10"
          data-testid="founding-chat-input"
        />
        <Button onClick={send} disabled={sending} data-testid="founding-chat-send">
          {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </Card>
  );
}

/* --------------------------------------------------------------- projects */

function Projects() {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    api.get("/founding/projects").then(({ data }) => setRows(data)).catch(() => setRows([]));
  }, []);

  if (!rows) return <Skeleton className="h-64 bg-surface-1" />;

  if (rows.length === 0) {
    return (
      <Card className="p-8 bg-surface-1 border-white/10 text-center" data-testid="founding-projects">
        <FolderKanban className="h-5 w-5 text-graphite mx-auto" />
        <p className="mt-2 text-sm text-graphite">Nothing listed yet.</p>
        <p className="mt-1 text-xs text-carbon">
          Add what you&apos;re building under Profile and it shows up here.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-3" data-testid="founding-projects">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
        What the circle is building
      </p>
      {rows.map((p, i) => (
        <Card key={`${p.owner_id}-${i}`} className="p-4 bg-surface-1 border-white/10">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">{p.title}</p>
              {p.summary && <p className="mt-1 text-sm text-ash">{p.summary}</p>}
            </div>
            {p.status && (
              <span className="shrink-0 rounded-full border border-white/10 px-2 py-0.5 font-mono text-[10px] uppercase text-graphite">
                {p.status}
              </span>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2 text-[11px] text-graphite">
            <span>{p.owner}</span>
            {p.owner_company && <span className="text-carbon">· {p.owner_company}</span>}
            {p.link && (
              <a href={p.link} target="_blank" rel="noopener noreferrer"
                 className="ml-auto text-accent hover:underline">
                Open
              </a>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- directory */

function Directory() {
  const [people, setPeople] = useState(null);

  useEffect(() => {
    api.get("/founding/directory").then(({ data }) => setPeople(data)).catch(() => setPeople([]));
  }, []);

  if (!people) return <Skeleton className="h-64 bg-surface-1" />;

  return (
    <div className="space-y-3" data-testid="founding-directory">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
        The circle · {people.length}
      </p>
      {people.map((p) => {
        const links = [
          ["LinkedIn", p.linkedin], ["Instagram", p.instagram],
          ["X", p.twitter], ["Email", p.email && `mailto:${p.email}`],
          ["Phone", p.phone && `tel:${p.phone}`],
        ].filter(([, v]) => v);
        return (
          <Card key={p.id} className="p-4 bg-surface-1 border-white/10">
            <div className="flex items-baseline gap-2">
              <p className="font-medium">{p.name}</p>
              {p.company && <p className="text-sm text-graphite">· {p.company}</p>}
            </div>
            {p.headline && <p className="mt-1 text-sm text-ash">{p.headline}</p>}
            {p.bio && <p className="mt-2 text-sm text-graphite whitespace-pre-line">{p.bio}</p>}

            {p.projects?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {p.projects.map((pr, i) => (
                  <span key={i} className="rounded-full bg-surface-2 border border-white/10 px-2 py-0.5 text-[11px]">
                    {pr.title}
                  </span>
                ))}
              </div>
            )}

            {links.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-3 text-[11px]">
                {links.map(([label, href]) => (
                  <a key={label} href={href} target="_blank" rel="noopener noreferrer"
                     className="text-accent hover:underline">{label}</a>
                ))}
              </div>
            ) : (
              // Said plainly rather than left blank, so nobody wonders whether
              // the page is broken.
              <p className="mt-3 text-[11px] text-carbon">
                Shares no contact details. Reach them in the community room.
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------- referrals */

function Referrals() {
  const [rows, setRows] = useState(null);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(null);

  const load = async () => {
    const { data } = await api.get("/founding/referrals");
    setRows(data);
  };
  useEffect(() => { load(); }, []);

  // The site the link points at, not this one. A referral is something you send
  // to someone outside, so it has to be the public application URL.
  const APPLY_ORIGIN = "https://obrinex.space";
  const linkFor = (code) => `${APPLY_ORIGIN}/join?ref=${code}`;

  const create = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/founding/referrals", { label, note });
      await navigator.clipboard?.writeText(linkFor(data.code)).catch(() => {});
      toast.success("Invitation ready — link copied.");
      setLabel(""); setNote("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  const revoke = async (id) => {
    try {
      await api.delete(`/founding/referrals/${id}`);
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const copy = async (code) => {
    await navigator.clipboard?.writeText(linkFor(code)).catch(() => {});
    setCopied(code);
    setTimeout(() => setCopied(null), 1500);
  };

  if (!rows) return <Skeleton className="h-64 bg-surface-1" />;

  return (
    <div className="space-y-5" data-testid="founding-referrals">
      <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
        <div>
          <p className="font-medium">Invite someone</p>
          <p className="mt-1 text-sm text-graphite">
            You get a link to send them yourself. They answer the same eleven
            questions and are scored the same way — a referral is read sooner,
            not accepted sooner.
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <Label className="text-xs text-graphite">Who is it for?</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)}
                   placeholder="For your list only"
                   className="mt-1 bg-surface-2 border-white/10"
                   data-testid="founding-referral-label" />
          </div>
          <div>
            <Label className="text-xs text-graphite">Why them?</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="We read this with their application"
                   className="mt-1 bg-surface-2 border-white/10"
                   data-testid="founding-referral-note" />
          </div>
        </div>
        <Button size="sm" onClick={create} disabled={busy}
                className="gap-1.5" data-testid="founding-referral-create">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          Create invitation
        </Button>
        <p className="text-xs text-carbon">
          We never email the person — the introduction is yours to make.
        </p>
      </Card>

      {rows.length > 0 && (
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
            Your invitations
          </p>
          {rows.map((r) => (
            <Card key={r.id} className="p-3 bg-surface-1 border-white/10 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm truncate">{r.label || "Unlabelled invitation"}</p>
                <p className="mt-0.5 text-[11px] text-graphite">
                  {r.used_at
                    ? `Used${r.applicant_name ? ` by ${r.applicant_name}` : ""}${r.status ? ` · ${r.status}` : ""}`
                    : "Not used yet"}
                </p>
              </div>
              {!r.used_at && (
                <>
                  <Button size="icon" variant="ghost" onClick={() => copy(r.code)}
                          title="Copy link" className="text-carbon hover:text-foreground">
                    {copied === r.code ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => revoke(r.id)}
                          title="Withdraw" className="text-carbon hover:text-danger">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- profile */

const SHARE_FIELDS = [
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "instagram", label: "Instagram" },
  { key: "twitter", label: "X / Twitter" },
];

function Profile() {
  const [p, setP] = useState(null);
  const [busy, setBusy] = useState(false);

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
      toast.success("Saved.");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setBusy(false); }
  };

  if (p === null) return <Skeleton className="h-96 bg-surface-1" />;
  if (p === false) return <Card className="p-6 bg-surface-1 border-white/10 text-sm text-graphite">Profile unavailable.</Card>;

  const set = (patch) => setP({ ...p, ...patch });
  const setProject = (i, patch) => {
    const projects = [...(p.projects || [])];
    projects[i] = { ...projects[i], ...patch };
    set({ projects });
  };

  return (
    <div className="space-y-5" data-testid="founding-profile">
      <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
        <p className="font-medium">You</p>
        <div>
          <Label className="text-xs text-graphite">One line about what you do</Label>
          <Input value={p.headline || ""} onChange={(e) => set({ headline: e.target.value })}
                 className="mt-1 bg-surface-2 border-white/10" data-testid="founding-profile-headline" />
        </div>
        <div>
          <Label className="text-xs text-graphite">Anything else worth knowing</Label>
          <Textarea rows={3} value={p.bio || ""} onChange={(e) => set({ bio: e.target.value })}
                    className="mt-1 bg-surface-2 border-white/10" />
        </div>
      </Card>

      <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
        <div className="flex items-baseline justify-between">
          <p className="font-medium">What you&apos;re building</p>
          <Button size="sm" variant="outline" className="border-white/10 gap-1.5"
                  onClick={() => set({ projects: [...(p.projects || []), { title: "", summary: "", status: "", link: "" }] })}
                  data-testid="founding-profile-add-project">
            <Plus className="h-3.5 w-3.5" /> Add
          </Button>
        </div>
        {(p.projects || []).length === 0 && (
          <p className="text-sm text-graphite">
            Nothing yet. What you add here is what the circle sees on Projects.
          </p>
        )}
        {(p.projects || []).map((pr, i) => (
          <div key={i} className="rounded-lg bg-surface-2 border border-white/10 p-3 space-y-2">
            <div className="flex gap-2">
              <Input value={pr.title || ""} placeholder="Project"
                     onChange={(e) => setProject(i, { title: e.target.value })}
                     className="bg-surface-1 border-white/10" />
              <Input value={pr.status || ""} placeholder="Status"
                     onChange={(e) => setProject(i, { status: e.target.value })}
                     className="w-32 bg-surface-1 border-white/10" />
              <Button size="icon" variant="ghost" className="text-carbon hover:text-danger shrink-0"
                      onClick={() => set({ projects: p.projects.filter((_, n) => n !== i) })}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            <Input value={pr.summary || ""} placeholder="One line"
                   onChange={(e) => setProject(i, { summary: e.target.value })}
                   className="bg-surface-1 border-white/10" />
            <Input value={pr.link || ""} placeholder="Link (optional)"
                   onChange={(e) => setProject(i, { link: e.target.value })}
                   className="bg-surface-1 border-white/10" />
          </div>
        ))}
      </Card>

      <Card className="p-4 bg-surface-1 border-white/10 space-y-3">
        <div>
          <p className="font-medium">Contact details</p>
          <p className="mt-1 text-sm text-graphite">
            Each of these is hidden from other members until you switch it on.
            Your name, company and projects are always visible.
          </p>
        </div>
        {SHARE_FIELDS.map((f) => (
          <div key={f.key} className="flex items-center gap-3">
            <Label className="w-24 shrink-0 text-xs text-graphite">{f.label}</Label>
            <Input value={p[f.key] || ""} onChange={(e) => set({ [f.key]: e.target.value })}
                   className="bg-surface-2 border-white/10" />
            <label className="flex shrink-0 items-center gap-1.5 text-[11px] text-graphite">
              <input
                type="checkbox"
                checked={!!p.visibility?.[f.key]}
                onChange={(e) => set({ visibility: { ...p.visibility, [f.key]: e.target.checked } })}
                data-testid={`founding-share-${f.key}`}
              />
              Share
            </label>
          </div>
        ))}
        <label className="flex items-center gap-2 pt-1 text-sm">
          <input type="checkbox" checked={p.listed !== false}
                 onChange={(e) => set({ listed: e.target.checked })}
                 data-testid="founding-listed" />
          List me in the directory
        </label>
      </Card>

      <Button onClick={save} disabled={busy} data-testid="founding-profile-save">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
      </Button>
    </div>
  );
}

/* ------------------------------------------------------- guidelines & help */

function Guidelines() {
  return (
    <div className="space-y-3" data-testid="founding-guidelines">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
        How this room works
      </p>
      {GUIDELINES.map((g) => (
        <Card key={g.title} className="p-4 bg-surface-1 border-white/10">
          <p className="font-medium">{g.title}</p>
          <p className="mt-1.5 text-sm text-ash leading-relaxed">{g.body}</p>
        </Card>
      ))}
    </div>
  );
}

function Help() {
  return (
    <div className="space-y-3" data-testid="founding-help">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-graphite">
        Questions people actually ask
      </p>
      {FAQ.map((f) => (
        <details key={f.q} className="group rounded-lg border border-white/10 bg-surface-1 p-4">
          <summary className="cursor-pointer list-none text-sm font-medium marker:hidden">
            {f.q}
          </summary>
          <p className="mt-2 text-sm text-ash leading-relaxed">{f.a}</p>
        </details>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- assistant */

function Assistant() {
  const [thread, setThread] = useState(null);
  const [text, setText] = useState("");
  const [asking, setAsking] = useState(false);
  const endRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/founding/assistant");
    setThread(data);
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [thread]);

  const ask = async () => {
    if (!text.trim()) return;
    setAsking(true);
    try {
      await api.post("/founding/assistant", { message: text });
      setText("");
      await load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally { setAsking(false); }
  };

  if (!thread) return <Skeleton className="h-96 bg-surface-1" />;

  return (
    <Card className="bg-surface-1 border-white/10 flex flex-col h-[70vh]" data-testid="founding-assistant">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {thread.length === 0 && (
          <div className="text-center py-12 space-y-2">
            <Sparkles className="h-5 w-5 text-graphite mx-auto" />
            <p className="text-sm text-graphite">Your assistant. Ask it anything general.</p>
            <p className="text-xs text-carbon">
              It can&apos;t see the agency&apos;s client data or anyone else&apos;s information.
            </p>
          </div>
        )}
        {thread.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[80%] rounded-lg p-3 text-sm whitespace-pre-line break-words ${
              m.role === "user" ? "bg-surface-2 border border-white/10" : "bg-accent/5 border border-accent/20"
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-white/10 p-3 flex items-center gap-2">
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
          placeholder="Ask your assistant…"
          className="bg-surface-2 border-white/10"
          data-testid="founding-assistant-input"
        />
        <Button onClick={ask} disabled={asking} data-testid="founding-assistant-send">
          {asking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </Card>
  );
}
