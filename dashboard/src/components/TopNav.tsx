"use client";

import { useGuild } from "../context/GuildContext";
import { Server } from "lucide-react";

export function TopNav() {
  const { guilds, selectedGuildId, setSelectedGuildId } = useGuild();

  return (
    <header className="h-16 flex items-center justify-between px-8 border-b border-white/5 z-10 glass-panel bg-surface-dark/80 backdrop-blur-md">
      <div className="flex items-center gap-3 bg-surface-darker/80 px-3 py-1.5 rounded-lg border border-teal-900/30 shadow-inner">
        <Server className="w-4 h-4 text-teal-500/70" />
        <span className="text-xs font-semibold text-teal-600/70 uppercase tracking-wider">Server:</span>
        {guilds.length > 0 ? (
          <select 
            value={selectedGuildId} 
            onChange={e => setSelectedGuildId(e.target.value)}
            className="bg-transparent border-none text-teal-300 font-medium text-sm focus:outline-none cursor-pointer hover:text-teal-200 transition-colors appearance-none pr-4 min-w-[120px]"
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
    </header>
  );
}
