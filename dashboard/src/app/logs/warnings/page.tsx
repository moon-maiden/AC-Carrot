"use client";

import { useEffect, useState, useMemo } from "react";
import { ShieldAlert, Search, Trash2, RefreshCw, Clock, MessageSquare, ExternalLink, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { useGuild } from "../../../context/GuildContext";

type Warning = {
  id: number;
  user_id: number;
  user_name: string;
  user_avatar: string | null;
  warned_at: string;
  channel_id: number;
  message_id: number;
  message_content: string | null;
  staff_id: number;
  staff_name: string;
  staff_avatar: string | null;
  reason: string | null;
  post_created_at: string | null;
};

export default function WarningsPage() {
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedWarning, setSelectedWarning] = useState<Warning | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const { selectedGuildId } = useGuild();

  // Pagination & Sorting State
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [sortConfig, setSortConfig] = useState<{ key: keyof Warning; direction: 'asc' | 'desc' }>({ key: 'id', direction: 'desc' });
  const [staffFilter, setStaffFilter] = useState<string>("All");

  const fetchWarnings = () => {
    if (!selectedGuildId || selectedGuildId === "0") return;
    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${apiUrl}/api/guilds/${selectedGuildId}/warnings`)
      .then((res) => res.json())
      .then((data) => {
        setWarnings(data.warnings || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching warnings:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    if (selectedGuildId && selectedGuildId !== "0") {
      fetchWarnings();
    }
  }, [selectedGuildId]);

  const processedWarnings = useMemo(() => {
    // 1. Filter
    let filtered = warnings.filter((w) => {
      const query = searchQuery.toLowerCase();
      const matchesSearch = (w.user_name || "").toLowerCase().includes(query) ||
        (w.user_id || "").toString().includes(query) ||
        (w.reason || "").toLowerCase().includes(query) ||
        (w.staff_name || "").toLowerCase().includes(query);
      
      const matchesStaff = staffFilter === "All" || w.staff_name === staffFilter;
      return matchesSearch && matchesStaff;
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
  }, [warnings, searchQuery, staffFilter, sortConfig]);

  // Pagination boundaries
  const totalPages = Math.ceil(processedWarnings.length / itemsPerPage) || 1;
  const currentWarnings = processedWarnings.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, staffFilter, itemsPerPage]);

  const uniqueStaff = Array.from(new Set(warnings.map(w => w.staff_name))).sort();

  const handleSort = (key: keyof Warning) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const SortIcon = ({ columnKey }: { columnKey: keyof Warning }) => {
    if (sortConfig.key !== columnKey) return <div className="w-4 h-4 opacity-0 group-hover:opacity-30 transition-opacity"><ChevronDown className="w-4 h-4" /></div>;
    return sortConfig.direction === 'asc' ? <ChevronUp className="w-4 h-4 text-teal-400" /> : <ChevronDown className="w-4 h-4 text-teal-400" />;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <ShieldAlert className="text-teal-400 w-8 h-8" />
            Warning Logs
          </h1>
          <p className="text-gray-400 mt-1">Review and manage verbal warnings issued by staff.</p>
        </div>
        
        <div className="flex items-center gap-3 relative">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <Search className="w-4 h-4" />
          </div>
          <input 
            type="text" 
            placeholder="Search users or reasons..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 pr-4 py-2 bg-surface-dark border border-teal-900/40 rounded-lg text-sm text-white focus:outline-none focus:border-teal-500/50 focus:ring-1 focus:ring-teal-500/50 w-full md:w-64 transition-all"
          />
          <button 
            onClick={fetchWarnings}
            disabled={loading}
            className="bg-surface-dark border border-teal-900/40 p-2 rounded-lg text-gray-400 hover:text-white hover:border-teal-500/50 transition-colors disabled:opacity-50"
            title="Refresh logs"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-teal-500' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row justify-between items-center gap-4 bg-surface-dark/50 p-3 rounded-lg border border-teal-900/30">
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-4 h-4 text-teal-500" />
          <span className="text-sm text-gray-400">Staff:</span>
          <select 
            value={staffFilter} 
            onChange={(e) => setStaffFilter(e.target.value)}
            className="bg-surface-dark border border-teal-900/40 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-teal-500 w-full sm:w-auto min-w-[120px]"
          >
            <option value="All">All Staff</option>
            {uniqueStaff.map(staff => (
              <option key={staff} value={staff}>{staff}</option>
            ))}
          </select>
        </div>
        
        <div className="flex items-center gap-2 w-full sm:w-auto">
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

      <div className="glass-panel rounded-xl overflow-hidden shadow-2xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="bg-surface-dark/80 border-b border-teal-900/30 text-teal-400/80 font-medium">
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('id')}>
                  <div className="flex items-center gap-1">ID <SortIcon columnKey="id" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('user_name')}>
                  <div className="flex items-center gap-1">User <SortIcon columnKey="user_name" /></div>
                </th>
                <th className="px-6 py-4">Reason</th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('staff_name')}>
                  <div className="flex items-center gap-1">Issued By <SortIcon columnKey="staff_name" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('warned_at')}>
                  <div className="flex items-center gap-1">Date <SortIcon columnKey="warned_at" /></div>
                </th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-teal-900/20 bg-surface-dark/40">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                    <div className="animate-pulse flex flex-col items-center gap-2">
                      <div className="w-8 h-8 border-2 border-teal-500/30 border-t-teal-500 rounded-full animate-spin" />
                      Loading logs...
                    </div>
                  </td>
                </tr>
              ) : currentWarnings.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                    No warnings found matching your filters.
                  </td>
                </tr>
              ) : (
                currentWarnings.map((w) => (
                  <tr key={w.id} className="hover:bg-teal-900/10 transition-colors group">
                    <td className="px-6 py-4 text-gray-400 font-mono">#{w.id}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        {w.user_avatar ? (
                          <img src={w.user_avatar} alt="" className="w-8 h-8 rounded-full bg-gray-800" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center text-gray-400 text-xs font-bold">
                            {w.user_name.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-medium text-gray-200">{w.user_name}</div>
                          <div className="text-xs text-gray-500 font-mono">{w.user_id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="max-w-xs truncate text-gray-300">
                        {w.reason || "No reason provided"}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {w.staff_avatar ? (
                          <img src={w.staff_avatar} alt="" className="w-6 h-6 rounded-full bg-gray-800" />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-gray-800 flex items-center justify-center text-gray-400 text-xs font-bold">
                            {w.staff_name.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <span className="text-gray-300 text-sm">{w.staff_name}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-gray-400 whitespace-nowrap">
                      {new Date(w.warned_at + "Z").toLocaleString()}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button 
                        onClick={() => setSelectedWarning(w)}
                        className="text-teal-400 hover:text-teal-300 bg-teal-500/10 hover:bg-teal-500/20 px-3 py-1.5 rounded text-xs font-medium transition-colors"
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          
          {!loading && processedWarnings.length > 0 && (
            <div className="px-6 py-4 border-t border-teal-900/30 bg-surface-dark/40 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
              <div className="text-gray-400">
                Showing <span className="text-white font-medium">{(currentPage - 1) * itemsPerPage + 1}</span> to <span className="text-white font-medium">{Math.min(currentPage * itemsPerPage, processedWarnings.length)}</span> of <span className="text-white font-medium">{processedWarnings.length}</span> entries
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

      {/* Detail Modal */}
      {selectedWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm" 
            onClick={() => setSelectedWarning(null)}
          />
          <div className="relative w-full max-w-2xl max-h-[85vh] flex flex-col bg-surface-card border border-teal-900/40 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between bg-surface-darker/50">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-teal-400" />
                Warning Details <span className="text-gray-500 font-mono text-sm ml-2">#{selectedWarning.id}</span>
              </h2>
              <button 
                onClick={() => setSelectedWarning(null)}
                className="text-gray-400 hover:text-white p-1 rounded-md hover:bg-white/10 transition-colors"
              >
                ✕
              </button>
            </div>
            
            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 text-sm">
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-1">
                  <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2">Original Author</div>
                  <div className="flex items-center gap-3 bg-surface-darker p-3 rounded-lg border border-white/5">
                    {selectedWarning.user_avatar ? (
                      <img src={selectedWarning.user_avatar} alt="" className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-gray-800 flex items-center justify-center font-bold">
                        {selectedWarning.user_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium text-white">{selectedWarning.user_name}</div>
                      <div className="text-gray-500 font-mono text-xs">{selectedWarning.user_id}</div>
                    </div>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2">Issued By Staff</div>
                  <div className="flex items-center gap-3 bg-surface-darker p-3 rounded-lg border border-white/5">
                    {selectedWarning.staff_avatar ? (
                      <img src={selectedWarning.staff_avatar} alt="" className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-gray-800 flex items-center justify-center font-bold">
                        {selectedWarning.staff_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium text-white">{selectedWarning.staff_name}</div>
                      <div className="text-gray-500 font-mono text-xs">{selectedWarning.staff_id}</div>
                    </div>
                  </div>
                </div>
              </div>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                    <div className="text-gray-500 text-xs flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Post Created At</div>
                    <div className="text-gray-300">{selectedWarning.post_created_at ? new Date(selectedWarning.post_created_at).toLocaleString() : "Unknown"}</div>
                  </div>
                  <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                    <div className="text-gray-500 text-xs flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /> Warning Issued</div>
                    <div className="text-teal-300 font-medium">{new Date(selectedWarning.warned_at + "Z").toLocaleString()}</div>
                  </div>
                  <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                    <div className="text-gray-500 text-xs flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5" /> Channel ID</div>
                    <div className="text-gray-300 font-mono text-xs mt-1">{selectedWarning.channel_id}</div>
                  </div>
                </div>

              <div>
                <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2">Rejection Reason</div>
                <div className="bg-surface-darker p-4 rounded-lg border border-teal-900/40 text-gray-300 whitespace-pre-wrap leading-relaxed shadow-inner">
                  {selectedWarning.reason || "No reason recorded."}
                </div>
              </div>

              <div>
                <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2 flex justify-between items-center">
                  <span>Original Post Content</span>
                  <a href={`https://discord.com/channels/0/${selectedWarning.channel_id}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-teal-400 hover:text-teal-300 transition-colors">
                    <ExternalLink className="w-3 h-3" /> Go to channel
                  </a>
                </div>
                <div className="bg-black/50 p-4 rounded-lg border border-white/10 font-mono text-xs text-gray-400 whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {selectedWarning.message_content || "No original content available."}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-white/5 bg-surface-darker/80 flex justify-end gap-3">
              <button 
                onClick={() => setSelectedWarning(null)}
                className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition-colors"
              >
                Close
              </button>
              <button 
                className="px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 text-sm font-medium rounded-lg flex items-center gap-2 border border-red-500/20 transition-colors"
              >
                <Trash2 className="w-4 h-4" /> Revoke Warning
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
