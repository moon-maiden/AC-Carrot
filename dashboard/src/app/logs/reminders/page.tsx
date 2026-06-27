"use client";

import { useEffect, useState, useMemo } from "react";
import { Bell, Search, Trash2, RefreshCw, Calendar, MessageSquare, Clock, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { useGuild } from "../../../context/GuildContext";

type Reminder = {
  id: number;
  user_id: number;
  user_name: string;
  user_avatar: string | null;
  about: string;
  remind_at: string;
  channel_id: number;
  created_at: string;
};

export default function RemindersPage() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedReminder, setSelectedReminder] = useState<Reminder | null>(null);
  const { selectedGuildId } = useGuild();

  // Pagination & Sorting State
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [sortConfig, setSortConfig] = useState<{ key: keyof Reminder; direction: 'asc' | 'desc' }>({ key: 'remind_at', direction: 'asc' });

  const fetchReminders = () => {
    if (!selectedGuildId || selectedGuildId === "0") return;
    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${apiUrl}/api/guilds/${selectedGuildId}/reminders`)
      .then((res) => res.json())
      .then((data) => {
        setReminders(data.reminders || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching reminders:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    if (selectedGuildId && selectedGuildId !== "0") {
      fetchReminders();
    }
  }, [selectedGuildId]);

  const deleteReminder = async (id: number) => {
    if (!confirm("Are you sure you want to delete this reminder?")) return;
    
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    try {
      const res = await fetch(`${apiUrl}/api/reminders/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Delete failed");
      
      setReminders(reminders.filter(r => r.id !== id));
      if (selectedReminder?.id === id) setSelectedReminder(null);
    } catch (err) {
      console.error(err);
      alert("Failed to delete reminder.");
    }
  };

  const processedReminders = useMemo(() => {
    // 1. Filter
    let filtered = reminders.filter((r) => {
      if (!searchQuery) return true;
      const query = searchQuery.toLowerCase();
      return (
        (r.user_name && r.user_name.toLowerCase().includes(query)) ||
        (r.about && r.about.toLowerCase().includes(query))
      );
    });

    // 2. Sort
    filtered.sort((a, b) => {
      let aValue = a[sortConfig.key];
      let bValue = b[sortConfig.key];
      
      if (aValue === null) aValue = "";
      if (bValue === null) bValue = "";
      
      if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });

    return filtered;
  }, [reminders, searchQuery, sortConfig]);

  // Pagination boundaries
  const totalPages = Math.ceil(processedReminders.length / itemsPerPage) || 1;
  const currentReminders = processedReminders.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, itemsPerPage]);

  const handleSort = (key: keyof Reminder) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const SortIcon = ({ columnKey }: { columnKey: keyof Reminder }) => {
    if (sortConfig.key !== columnKey) return <div className="w-4 h-4 opacity-0 group-hover:opacity-30 transition-opacity"><ChevronDown className="w-4 h-4" /></div>;
    return sortConfig.direction === 'asc' ? <ChevronUp className="w-4 h-4 text-teal-400" /> : <ChevronDown className="w-4 h-4 text-teal-400" />;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <Bell className="text-teal-400 w-8 h-8" />
            Active Reminders
          </h1>
          <p className="text-gray-400 mt-1">Manage scheduled system and user reminders.</p>
        </div>
        
        <div className="flex items-center gap-3 relative">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <Search className="w-4 h-4" />
          </div>
          <input 
            type="text" 
            placeholder="Search reminders..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 pr-4 py-2 bg-surface-dark border border-teal-900/40 rounded-lg text-sm text-white focus:outline-none focus:border-teal-500/50 focus:ring-1 focus:ring-teal-500/50 w-full md:w-64 transition-all"
          />
          <button 
            onClick={fetchReminders}
            disabled={loading}
            className="bg-surface-dark border border-teal-900/40 p-2 rounded-lg text-gray-400 hover:text-white hover:border-teal-500/50 transition-colors disabled:opacity-50"
            title="Refresh logs"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-teal-500' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex justify-end items-center bg-surface-dark/50 p-3 rounded-lg border border-teal-900/30">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">Show:</span>
          <select 
            value={itemsPerPage} 
            onChange={(e) => setItemsPerPage(Number(e.target.value))}
            className="bg-surface-dark border border-teal-900/40 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-teal-500"
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
          <span className="text-sm text-gray-400">entries</span>
        </div>
      </div>

      <div className="glass-panel rounded-xl border border-teal-900/30 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-dark/50 border-b border-teal-900/30">
                <th className="px-6 py-4 text-xs font-semibold text-teal-600/70 uppercase tracking-wider cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('user_name')}>
                  <div className="flex items-center gap-1">User <SortIcon columnKey="user_name" /></div>
                </th>
                <th className="px-6 py-4 text-xs font-semibold text-teal-600/70 uppercase tracking-wider cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('about')}>
                  <div className="flex items-center gap-1">About <SortIcon columnKey="about" /></div>
                </th>
                <th className="px-6 py-4 text-xs font-semibold text-teal-600/70 uppercase tracking-wider cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('remind_at')}>
                  <div className="flex items-center gap-1">Remind At <SortIcon columnKey="remind_at" /></div>
                </th>
                <th className="px-6 py-4 text-xs font-semibold text-teal-600/70 uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-teal-900/10">
              {loading && reminders.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-gray-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-teal-500/50" />
                    Loading reminders...
                  </td>
                </tr>
              ) : currentReminders.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-gray-500">
                    No reminders found matching your criteria.
                  </td>
                </tr>
              ) : (
                currentReminders.map((r) => (
                  <tr 
                    key={r.id} 
                    className="hover:bg-white/[0.02] transition-colors cursor-pointer"
                    onClick={() => setSelectedReminder(r)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        {r.user_avatar ? (
                          <img src={r.user_avatar} alt="" className="w-8 h-8 rounded-full" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center font-bold text-xs">
                            {r.user_name.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-medium text-white text-sm">{r.user_name}</div>
                          <div className="text-gray-500 font-mono text-xs">{r.user_id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-gray-300 text-sm truncate max-w-xs md:max-w-md">{r.about}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-teal-300 text-sm font-medium">{new Date(r.remind_at).toLocaleString()}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      <button 
                        onClick={(e) => { e.stopPropagation(); deleteReminder(r.id); }}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                        title="Delete Reminder"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          
          {!loading && processedReminders.length > 0 && (
            <div className="px-6 py-4 border-t border-teal-900/30 bg-surface-dark/40 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
              <div className="text-gray-400">
                Showing <span className="text-white font-medium">{(currentPage - 1) * itemsPerPage + 1}</span> to <span className="text-white font-medium">{Math.min(currentPage * itemsPerPage, processedReminders.length)}</span> of <span className="text-white font-medium">{processedReminders.length}</span> entries
              </div>
              
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-1 rounded-md text-gray-400 hover:text-white hover:bg-teal-900/30 disabled:opacity-50 disabled:hover:bg-transparent transition-colors"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pageNum = currentPage;
                    if (totalPages <= 5) pageNum = i + 1;
                    else if (currentPage <= 3) pageNum = i + 1;
                    else if (currentPage >= totalPages - 2) pageNum = totalPages - 4 + i;
                    else pageNum = currentPage - 2 + i;
                    
                    if (pageNum < 1 || pageNum > totalPages) return null;
                    
                    return (
                      <button
                        key={pageNum}
                        onClick={() => setCurrentPage(pageNum)}
                        className={`w-8 h-8 rounded-md flex items-center justify-center transition-colors ${
                          currentPage === pageNum 
                            ? 'bg-teal-500 text-white font-medium shadow-md shadow-teal-900/20' 
                            : 'text-gray-400 hover:text-white hover:bg-teal-900/30'
                        }`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                </div>
                
                <button 
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="p-1 rounded-md text-gray-400 hover:text-white hover:bg-teal-900/30 disabled:opacity-50 disabled:hover:bg-transparent transition-colors"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Reminder Details Modal */}
      {selectedReminder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm" 
            onClick={() => setSelectedReminder(null)}
          />
          <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col bg-surface-card border border-teal-900/40 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between bg-surface-dark/50 shrink-0">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <Bell className="w-5 h-5 text-teal-400" />
                Reminder Details <span className="text-gray-500 font-mono text-sm ml-2">#{selectedReminder.id}</span>
              </h2>
              <button 
                onClick={() => setSelectedReminder(null)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>
            
            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 text-sm">
              <div className="grid grid-cols-1 gap-6">
                <div className="space-y-1">
                  <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2">User</div>
                  <div className="flex items-center gap-3 bg-surface-darker p-3 rounded-lg border border-white/5">
                    {selectedReminder.user_avatar ? (
                      <img src={selectedReminder.user_avatar} alt="" className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-gray-800 flex items-center justify-center font-bold">
                        {selectedReminder.user_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium text-white">{selectedReminder.user_name}</div>
                      <div className="text-gray-500 font-mono text-xs">{selectedReminder.user_id}</div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Created At</div>
                  <div className="text-gray-300">{new Date(selectedReminder.created_at).toLocaleString()}</div>
                </div>
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Remind At</div>
                  <div className="text-teal-300 font-medium">{new Date(selectedReminder.remind_at).toLocaleString()}</div>
                </div>
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> Channel ID</div>
                  <div className="text-gray-300 font-mono text-xs mt-1">{selectedReminder.channel_id}</div>
                </div>
              </div>

              <div>
                <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2 flex justify-between">Reminder Note</div>
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 text-gray-300 whitespace-pre-wrap font-mono text-sm shadow-inner overflow-x-auto">
                  {selectedReminder.about}
                </div>
              </div>
            </div>
            
            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-white/5 bg-surface-dark/30 flex justify-end gap-3">
              <button 
                onClick={() => setSelectedReminder(null)}
                className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition-colors"
              >
                Close
              </button>
              <button 
                onClick={() => deleteReminder(selectedReminder.id)}
                className="px-4 py-2 text-sm font-medium bg-red-500/10 text-red-400 border border-red-500/20 rounded-lg hover:bg-red-500/20 transition-colors flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" /> Delete Reminder
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
