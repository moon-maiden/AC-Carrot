"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, Server, LayoutDashboard, ShieldAlert, PenTool, Bot, Settings } from "lucide-react";
import { useGuild } from "../context/GuildContext";

import { LoginButton } from "./LoginButton";

export function DashboardWrapper({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);
  const pathname = usePathname();
  const { guilds, selectedGuildId, setSelectedGuildId } = useGuild();
  const currentGuild = guilds.find((g) => g.id === selectedGuildId);
  const isAdmin = currentGuild?.access_level === "admin";

  const toggleSidebar = () => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setSidebarOpen(!sidebarOpen);
    } else {
      setDesktopSidebarOpen(!desktopSidebarOpen);
    }
  };

  const navLinks = [
    { href: "/overview", label: "Overview", icon: LayoutDashboard },
    { href: "/logs/warnings", label: "Logs", icon: ShieldAlert },
    ...(isAdmin ? [
      { href: "/builder", label: "Message Builder", icon: PenTool },
      { href: "/chatbot", label: "Chatbot", icon: Bot },
    ] : []),
    { href: "/settings", label: "Guild Settings", icon: Settings },
  ];

  return (
    <div className="flex h-screen overflow-hidden relative">
      {/* Mobile Backdrop */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar (Mobile drawer and Desktop sidebar) */}
      <aside className={`
        fixed inset-y-0 left-0 w-64 glass-panel border-r border-teal-900/30 flex flex-col z-50 transition-all duration-300 transform 
        md:static md:z-10
        ${sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
        ${desktopSidebarOpen ? "md:w-64 md:opacity-100" : "md:w-0 md:opacity-0 md:border-r-0 overflow-hidden"}
      `}>
        <div className="h-16 flex items-center justify-between px-6 border-b border-teal-900/30">
          <h1 className="font-black text-xl tracking-tighter bg-gradient-to-br from-teal-400 to-emerald-600 bg-clip-text text-transparent">
            CARROT<span className="font-bold text-white/80 text-sm tracking-widest ml-2">DASHBOARD</span>
          </h1>
          <button 
            onClick={() => setSidebarOpen(false)} 
            className="md:hidden text-gray-400 hover:text-white p-1 hover:bg-white/5 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto py-6 px-4 space-y-2">
          <div className="text-xs font-semibold text-teal-600/70 uppercase tracking-wider mb-4 px-2">Navigation</div>
          {navLinks.map((link) => {
            const Icon = link.icon;
            const isActive = pathname === link.href || (link.href !== "/overview" && pathname.startsWith(link.href));
            return (
              <Link 
                key={link.href}
                href={link.href} 
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                  isActive 
                    ? "bg-teal-500/10 text-teal-400 font-medium border border-teal-500/20" 
                    : "text-gray-400 hover:text-white hover:bg-teal-500/10"
                }`}
              >
                <Icon className="w-[18px] h-[18px]" />
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-teal-900/30">
          <LoginButton />
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden relative">
        <div className="absolute top-0 left-0 w-full h-96 bg-teal-500/5 blur-3xl -z-10 rounded-full mix-blend-screen opacity-50 transform -translate-y-1/2 pointer-events-none"></div>
        
        {/* Header */}
        <header className="h-16 flex items-center justify-between px-4 md:px-8 border-b border-white/5 z-10 glass-panel bg-surface-dark/80 backdrop-blur-md">
          <div className="flex items-center gap-3">
            {/* Hamburger button */}
            <button 
              onClick={toggleSidebar}
              className="p-2 -ml-2 text-gray-400 hover:text-white hover:bg-white/5 rounded-lg"
            >
              <Menu className="w-6 h-6" />
            </button>
            
            <div className="flex items-center gap-3 bg-surface-darker/80 px-3 py-1.5 rounded-lg border border-teal-900/30 shadow-inner">
              <Server className="w-4 h-4 text-teal-500/70" />
              <span className="text-xs font-semibold text-teal-600/70 uppercase tracking-wider hidden sm:inline">Server:</span>
              {guilds.length > 0 ? (
                <select 
                  value={selectedGuildId} 
                  onChange={e => setSelectedGuildId(e.target.value)}
                  className="bg-transparent border-none text-teal-300 font-medium text-sm focus:outline-none cursor-pointer hover:text-teal-200 transition-colors appearance-none pr-4 min-w-[100px] sm:min-w-[120px]"
                  style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2314b8a6'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E\")", backgroundRepeat: "no-repeat", backgroundPosition: "right center", backgroundSize: "14px" }}
                >
                  <option value="0">All Servers</option>
                  {guilds.map(g => (
                    <option key={g.id} value={g.id} className="bg-surface-darker text-white py-2">
                      {g.name}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="font-mono text-teal-300 text-sm">Loading...</span>
              )}
            </div>
          </div>
        </header>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 z-10">
          {children}
        </div>
      </main>
    </div>
  );
}
