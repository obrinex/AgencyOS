import { useState, useEffect } from "react";
import {
  Search, Bell, Sparkles, LogOut, Settings as SettingsIcon, Menu,
  Volume2, VolumeX,
} from "lucide-react";
import { loadSoundPref, setSoundEnabled } from "@/lib/sound";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "date-fns";

export default function Topbar({ onOpenCommandPalette, onOpenAssistant, onOpenMobileNav }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  // Read once on mount rather than kept in a context: it is one boolean, it
  // lives in localStorage, and nothing else in the app needs to react to it.
  const [sound, setSound] = useState(false);
  useEffect(() => setSound(loadSoundPref()), []);

  const loadNotifications = async () => {
    try {
      const { data } = await api.get("/notifications");
      setNotifications(data);
      setUnreadCount(data.filter((n) => !n.read).length);
    } catch (e) {}
  };

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 30000);
    return () => clearInterval(interval);
  }, []);

  const markAllRead = async () => {
    await api.patch("/notifications/read-all");
    loadNotifications();
  };

  const initials = (user?.name || user?.email || "?").slice(0, 2).toUpperCase();

  return (
    <header
      data-testid="topbar"
      className="sticky top-0 z-40 flex h-16 items-center justify-between gap-3 border-b border-white/[0.10] bg-gradient-to-b from-white/[0.07] to-white/[0.02] px-4 backdrop-blur-2xl md:px-6"
    >
      <button
        type="button"
        data-testid="mobile-menu-trigger"
        onClick={onOpenMobileNav}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/[0.14] bg-white/[0.07] transition-colors hover:bg-white/[0.12] md:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      <button
        data-testid="global-search-trigger"
        onClick={onOpenCommandPalette}
        className="group flex w-full max-w-sm items-center gap-2.5 rounded-xl border border-white/[0.14] bg-white/[0.07] px-3.5 py-2.5 text-sm text-ash shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] transition-all duration-200 hover:border-primary/40 hover:bg-white/[0.11] hover:text-foreground"
      >
        <Search className="h-4 w-4 text-graphite transition-colors group-hover:text-primary" />
        <span className="flex-1 text-left">Search anything...</span>
        <kbd className="rounded-md border border-white/[0.14] bg-white/[0.10] px-1.5 py-0.5 font-mono text-[10px] text-ash">⌘K</kbd>
      </button>

      <div className="flex items-center gap-2">
        <Button
          data-testid="ai-assistant-trigger"
          onClick={onOpenAssistant}
          variant="outline"
          size="sm"
          className="gap-2 border-primary/30 bg-primary/[0.10] text-foreground hover:border-primary/60 hover:bg-primary/[0.18]"
        >
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="hidden sm:inline">AI Assistant</span>
        </Button>

        <DropdownMenu onOpenChange={(open) => open && loadNotifications()}>
          <DropdownMenuTrigger asChild>
            <button data-testid="notifications-trigger" className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.14] bg-white/[0.07] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] transition-colors hover:border-white/30 hover:bg-white/[0.12]">
              <Bell className="h-4 w-4" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-[10px] font-bold text-white">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80" data-testid="notifications-dropdown">
            <div className="flex items-center justify-between px-2 py-1.5">
              <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
              {unreadCount > 0 && (
                <button data-testid="mark-all-read-btn" onClick={markAllRead} className="text-xs text-info hover:underline">
                  Mark all read
                </button>
              )}
            </div>
            <DropdownMenuSeparator />
            <div className="max-h-80 overflow-y-auto scrollbar-thin">
              {notifications.length === 0 ? (
                <p className="px-2 py-6 text-center text-sm text-graphite">No notifications yet</p>
              ) : (
                notifications.map((n) => (
                  <DropdownMenuItem key={n.id} data-testid={`notification-item-${n.id}`} className="flex flex-col items-start gap-0.5 py-2">
                    <div className="flex items-center gap-2 w-full">
                      {!n.read && <span className="h-1.5 w-1.5 rounded-full bg-info shrink-0" />}
                      <span className="text-sm font-medium truncate">{n.title}</span>
                    </div>
                    <span className="text-xs text-graphite line-clamp-2">{n.message}</span>
                    <span className="text-[10px] font-mono text-carbon">{formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}</span>
                  </DropdownMenuItem>
                ))
              )}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button data-testid="user-menu-trigger" className="flex items-center gap-2 rounded-xl border border-transparent py-1 pl-1 pr-2 transition-colors hover:border-white/[0.14] hover:bg-white/[0.08]">
              <Avatar className="h-7 w-7">
                <AvatarFallback className="bg-primary/20 font-mono text-xs font-semibold text-primary ring-1 ring-primary/30">{initials}</AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" data-testid="user-menu-dropdown">
            <DropdownMenuLabel>
              <p className="text-sm font-medium">{user?.name}</p>
              <p className="text-xs text-graphite font-normal">{user?.email}</p>
              <Badge variant="outline" className="mt-1 font-mono text-[10px] uppercase">{user?.role}</Badge>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {/* A personal preference, not a company one — so it lives here
                rather than in Settings, which is org-level. `onSelect` is
                prevented so switching it does not close the menu: the whole
                point is hearing the click it turns on. */}
            <DropdownMenuItem
              data-testid="user-menu-sound"
              onSelect={(e) => {
                e.preventDefault();
                setSound(setSoundEnabled(!sound));
              }}
            >
              {sound ? <Volume2 className="h-4 w-4 mr-2" /> : <VolumeX className="h-4 w-4 mr-2" />}
              Interface sound
              <span className="ml-auto font-mono text-[10px] uppercase text-graphite">
                {sound ? "On" : "Off"}
              </span>
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="user-menu-settings" onClick={() => navigate("/settings")}>
              <SettingsIcon className="h-4 w-4 mr-2" /> Settings
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="user-menu-logout" onClick={logout}>
              <LogOut className="h-4 w-4 mr-2" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
