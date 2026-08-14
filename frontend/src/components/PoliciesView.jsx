import { useState, useEffect, useCallback } from "react";
import { FileText } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

// Shared policy viewer for the admin dashboard and the client portal.
function renderInline(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**")
      ? <strong key={i}>{p.slice(2, -2)}</strong>
      : <span key={i}>{p}</span>);
}

function Markdown({ text }) {
  const lines = (text || "").split("\n");
  const out = [];
  let list = [];
  const flush = () => {
    if (list.length) {
      out.push(<ul key={"ul" + out.length} className="list-disc pl-5 space-y-1 my-2 text-sm">{list}</ul>);
      list = [];
    }
  };
  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    if (line.startsWith("### ")) { flush(); out.push(<h4 key={i} className="font-semibold mt-4 mb-1">{renderInline(line.slice(4))}</h4>); }
    else if (line.startsWith("## ")) { flush(); out.push(<h3 key={i} className="font-display text-base font-semibold mt-5 mb-1">{renderInline(line.slice(3))}</h3>); }
    else if (line.startsWith("# ")) { flush(); out.push(<h2 key={i} className="font-display text-lg font-bold mb-2">{renderInline(line.slice(2))}</h2>); }
    else if (line.startsWith("- ")) { list.push(<li key={i}>{renderInline(line.slice(2))}</li>); }
    else if (line === "") { flush(); }
    else if (line === "---") { flush(); out.push(<hr key={i} className="my-3 border-white/10" />); }
    else { flush(); out.push(<p key={i} className="text-sm leading-relaxed my-1.5">{renderInline(line)}</p>); }
  });
  flush();
  return <div>{out}</div>;
}

export default function PoliciesView() {
  const [list, setList] = useState(null);
  const [active, setActive] = useState(null);
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(false);

  const select = useCallback(async (slug) => {
    setActive(slug); setLoading(true); setDoc(null);
    try { const { data } = await api.get(`/policies/${slug}`); setDoc(data); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    api.get("/policies").then(({ data }) => {
      setList(data || []);
      if (data?.length) select(data[0].slug);
    }).catch((err) => { toast.error(formatApiError(err.response?.data?.detail)); setList([]); });
  }, [select]);

  return (
    <div className="grid md:grid-cols-[240px_1fr] gap-4" data-testid="policies-view">
      <Card className="p-2 bg-surface-1 border-white/10 h-max">
        {!list ? <Skeleton className="h-40 w-full" /> : list.map((p) => (
          <button key={p.slug} onClick={() => select(p.slug)} data-testid="policy-item"
            className={`w-full text-left rounded-lg px-3 py-2 text-sm flex items-center gap-2 transition-colors ${active === p.slug ? "bg-surface-2 text-foreground" : "text-graphite hover:bg-surface-2/50"}`}>
            <FileText className="h-3.5 w-3.5 shrink-0" />{p.title}
          </button>
        ))}
      </Card>
      <Card className="p-5 bg-surface-1 border-white/10 min-h-[50vh]">
        {loading || !doc ? <Skeleton className="h-64 w-full" /> : <Markdown text={doc.content} />}
      </Card>
    </div>
  );
}
