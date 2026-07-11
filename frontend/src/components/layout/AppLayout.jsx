import { useState, useEffect } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import CommandPalette from "@/components/CommandPalette";
import AIAssistant from "@/components/AIAssistant";

export default function AppLayout() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantMode, setAssistantMode] = useState("general");
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantPromptKey, setAssistantPromptKey] = useState(0);
  const [assistantSuggestions, setAssistantSuggestions] = useState(undefined);

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
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar onOpenCommandPalette={() => setPaletteOpen(true)} onOpenAssistant={() => openAssistant()} />
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <Outlet context={{ openAssistant }} />
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
