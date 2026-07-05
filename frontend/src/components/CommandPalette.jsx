import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem, CommandShortcut,
} from "@/components/ui/command";
import {
  LayoutDashboard, KanbanSquare, Building2, FolderKanban, Receipt, Plus, User as UserIcon, FileText, Search as SearchIcon,
} from "lucide-react";
import api from "@/lib/api";

const QUICK_ACTIONS = [
  { label: "Go to Dashboard", to: "/dashboard", icon: LayoutDashboard },
  { label: "Go to Pipeline", to: "/crm", icon: KanbanSquare },
  { label: "Go to Clients", to: "/clients", icon: Building2 },
  { label: "Go to Projects", to: "/projects", icon: FolderKanban },
  { label: "Go to Invoices", to: "/invoices", icon: Receipt },
  { label: "Create New Lead", to: "/crm?new=1", icon: Plus },
  { label: "Create New Task", to: "/tasks?new=1", icon: Plus },
  { label: "Create New Invoice", to: "/invoices?new=1", icon: Plus },
];

export default function CommandPalette({ open, onOpenChange }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const navigate = useNavigate();

  const runSearch = useCallback(async (q) => {
    if (!q) {
      setResults(null);
      return;
    }
    try {
      const { data } = await api.get(`/search?q=${encodeURIComponent(q)}`);
      setResults(data);
    } catch (e) {
      setResults(null);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => runSearch(query), 250);
    return () => clearTimeout(t);
  }, [query, runSearch]);

  const go = (path) => {
    onOpenChange(false);
    setQuery("");
    navigate(path);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} shouldFilter={false} data-testid="command-palette">
      <CommandInput
        data-testid="command-palette-input"
        placeholder="Search clients, projects, tasks, invoices..."
        value={query}
        onValueChange={setQuery}
      />
      <CommandList data-testid="command-palette-list">
        <CommandEmpty>No results found.</CommandEmpty>

        {!results && (
          <CommandGroup heading="Quick Actions">
            {QUICK_ACTIONS.map((a) => (
              <CommandItem key={a.label} data-testid={`command-action-${a.label.replace(/\s+/g, "-").toLowerCase()}`} onSelect={() => go(a.to)}>
                <a.icon className="h-4 w-4" />
                <span>{a.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {results?.leads?.length > 0 && (
          <CommandGroup heading="Leads">
            {results.leads.map((l) => (
              <CommandItem key={l.id} onSelect={() => go(`/crm/${l.id}`)}>
                <KanbanSquare className="h-4 w-4" /> {l.company}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {results?.clients?.length > 0 && (
          <CommandGroup heading="Clients">
            {results.clients.map((c) => (
              <CommandItem key={c.id} onSelect={() => go(`/clients/${c.id}`)}>
                <Building2 className="h-4 w-4" /> {c.company_name}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {results?.projects?.length > 0 && (
          <CommandGroup heading="Projects">
            {results.projects.map((p) => (
              <CommandItem key={p.id} onSelect={() => go(`/projects/${p.id}`)}>
                <FolderKanban className="h-4 w-4" /> {p.name}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {results?.invoices?.length > 0 && (
          <CommandGroup heading="Invoices">
            {results.invoices.map((i) => (
              <CommandItem key={i.id} onSelect={() => go(`/invoices/${i.id}`)}>
                <Receipt className="h-4 w-4" /> {i.invoice_number}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {results?.contacts?.length > 0 && (
          <CommandGroup heading="Contacts">
            {results.contacts.map((c) => (
              <CommandItem key={c.id} onSelect={() => go(`/contacts`)}>
                <UserIcon className="h-4 w-4" /> {c.name}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {results?.kb_articles?.length > 0 && (
          <CommandGroup heading="Knowledge Base">
            {results.kb_articles.map((k) => (
              <CommandItem key={k.id} onSelect={() => go(`/knowledge-base`)}>
                <FileText className="h-4 w-4" /> {k.title}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
