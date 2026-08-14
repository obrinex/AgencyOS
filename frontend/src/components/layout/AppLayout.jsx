import { useState, useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import ErrorBoundary from "@/components/ErrorBoundary";
import Sidebar, { MobileNav } from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import CommandPalette from "@/components/CommandPalette";
import AIAssistant from "@/components/AIAssistant";

export default function AppLayout() {
  const { pathname } = useLocation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantMode, setAssistantMode] = useState("general");
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantPromptKey, setAssistantPromptKey] = useState(0);
  const [assistantSuggestions, setAssistantSuggestions] = useState(undefined);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const openAssistant = ({ mode = "general", prompt = "", suggestions } = {}) => {
    setAssistantMode(mode);
    setAssistantSuggestions(suggestions);
    setAssistantPrompt(prompt);
    setAssistantPromptKey(Date.now());
    setAssistantOpen(true);
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background" data-testid="app-layout">
      <Sidebar />
      <MobileNav open={mobileNavOpen} onOpenChange={setMobileNavOpen} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar
          onOpenCommandPalette={() => setPaletteOpen(true)}
          onOpenAssistant={() => openAssistant()}
          onOpenMobileNav={() => setMobileNavOpen(true)}
        />
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          {/* Inside <main>, so a crashing page leaves the sidebar and topbar
              usable. Keyed by pathname: an error boundary holds its error
              state forever otherwise, so navigating away from a broken page
              would carry the error with you. */}
          <ErrorBoundary key={pathname}>
            <Outlet context={{ openAssistant }} />
          </ErrorBoundary>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <AIAssistant
        open={assistantOpen}
        onOpenChange={setAssistantOpen}
        initialPrompt={assistantPrompt}
        initialPromptKey={assistantPromptKey}
        mode={assistantMode}
        suggestions={assistantSuggestions}
      />
    </div>
  );
}
