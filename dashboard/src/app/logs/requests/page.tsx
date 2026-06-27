"use client";

import { useEffect, useState, useMemo } from "react";
import { CreditCard, Search, RefreshCw, X, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { useGuild } from "../../../context/GuildContext";

type PaidRequest = {
  request_id: number;
  user_id: number;
  user_name: string;
  user_avatar: string | null;
  budget: string;
  sfw_nsfw: string;
  payment_method: string;
  use_case: string;
  content: string;
  status: string;
  created_at: string;
};

export default function RequestsPage() {
  const [requests, setRequests] = useState<PaidRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRequest, setSelectedRequest] = useState<PaidRequest | null>(null);
  const { selectedGuildId } = useGuild();
  // Pagination & sorting
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [sortConfig, setSortConfig] = useState<{ key: keyof PaidRequest; direction: 'asc' | 'desc' }>({ key: 'request_id', direction: 'desc' });
  const [statusFilter, setStatusFilter] = useState<string>("All");
  const [totalCount, setTotalCount] = useState(0);

  const fetchRequests = () => {
    if (!selectedGuildId) return; // allow "0"
    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const params = new URLSearchParams({
      page: currentPage.toString(),
      limit: itemsPerPage.toString(),
      sort_key: sortConfig.key,
      sort_dir: sortConfig.direction,
      search: searchQuery,
      status: statusFilter === "All" ? "" : statusFilter
    });
    fetch(`${apiUrl}/api/guilds/${selectedGuildId}/paid-requests?${params}`)
      .then((res) => res.json())
      .then((data) => {
        setRequests(data.requests || []);
        setTotalCount(data.total || 0);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching paid requests:", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    if (selectedGuildId && selectedGuildId !== "0") {
      fetchRequests();
    }
  }, [selectedGuildId, currentPage, itemsPerPage, sortConfig, searchQuery, statusFilter]);

  const processedRequests = useMemo(() => {
    // 1. Filter
    let filtered = requests.filter((r) => {
      const query = searchQuery.toLowerCase();
      const matchesSearch = (r.user_name || "").toLowerCase().includes(query) ||
        (r.user_id || "").toString().includes(query) ||
        (r.payment_method || "").toLowerCase().includes(query) ||
        (r.status || "").toLowerCase().includes(query);
      
      const matchesStatus = statusFilter === "All" || r.status.toLowerCase() === statusFilter.toLowerCase();
      return matchesSearch && matchesStatus;
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
  }, [requests, searchQuery, statusFilter, sortConfig]);

  // Pagination boundaries
  const totalPages = Math.ceil(totalCount / itemsPerPage) || 1;
  const currentRequests = requests; // already paginated from backend

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, statusFilter, itemsPerPage]);

  const handleSort = (key: keyof PaidRequest) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const SortIcon = ({ columnKey }: { columnKey: keyof PaidRequest }) => {
    if (sortConfig.key !== columnKey) return <div className="w-4 h-4 opacity-0 group-hover:opacity-30 transition-opacity"><ChevronDown className="w-4 h-4" /></div>;
    return sortConfig.direction === 'asc' ? <ChevronUp className="w-4 h-4 text-teal-400" /> : <ChevronDown className="w-4 h-4 text-teal-400" />;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <CreditCard className="text-teal-400 w-8 h-8" />
            Paid Requests
          </h1>
          <p className="text-gray-400 mt-1">Review user submissions for paid requests and commissions.</p>
        </div>
        
        <div className="flex items-center gap-3 relative">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <Search className="w-4 h-4" />
          </div>
          <input 
            type="text" 
            placeholder="Search user or payment method..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 pr-4 py-2 bg-surface-dark border border-teal-900/40 rounded-lg text-sm text-white focus:outline-none focus:border-teal-500/50 focus:ring-1 focus:ring-teal-500/50 w-full md:w-64 transition-all"
          />
          <button 
            onClick={fetchRequests}
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
          <span className="text-sm text-gray-400">Status:</span>
          <select 
            value={statusFilter} 
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-surface-dark border border-teal-900/40 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-teal-500 w-full sm:w-auto min-w-[120px]"
          >
            <option value="All">All Requests</option>
            <option value="Pending">Pending</option>
            <option value="Approved">Approved</option>
            <option value="Rejected">Rejected</option>
            <option value="Closed">Closed</option>
            <option value="Fulfilled">Fulfilled</option>
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
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('request_id')}>
                  <div className="flex items-center gap-1">Request ID <SortIcon columnKey="request_id" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('user_name')}>
                  <div className="flex items-center gap-1">User <SortIcon columnKey="user_name" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('budget')}>
                  <div className="flex items-center gap-1">Budget <SortIcon columnKey="budget" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('payment_method')}>
                  <div className="flex items-center gap-1">Payment Method <SortIcon columnKey="payment_method" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('status')}>
                  <div className="flex items-center gap-1">Status <SortIcon columnKey="status" /></div>
                </th>
                <th className="px-6 py-4 cursor-pointer hover:bg-teal-900/20 group select-none transition-colors" onClick={() => handleSort('created_at')}>
                  <div className="flex items-center gap-1">Date <SortIcon columnKey="created_at" /></div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-teal-900/20 bg-surface-dark/40">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                    <div className="animate-pulse flex flex-col items-center gap-2">
                      <div className="w-8 h-8 border-2 border-teal-500/30 border-t-teal-500 rounded-full animate-spin" />
                      Loading requests...
                    </div>
                  </td>
                </tr>
              ) : currentRequests.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-400">
                    No paid requests found matching your filters.
                  </td>
                </tr>
              ) : (
                currentRequests.map((r) => (
                  <tr 
                    key={r.request_id} 
                    className="hover:bg-white/[0.02] transition-colors cursor-pointer"
                    onClick={() => setSelectedRequest(r)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap text-gray-400 font-mono">#{r.request_id}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        {r.user_avatar ? (
                          <img src={r.user_avatar} alt="" className="w-8 h-8 rounded-full bg-gray-800" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center text-gray-400 text-xs font-bold">
                            {r.user_name.charAt(0).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <div className="font-medium text-gray-200">{r.user_name}</div>
                          <div className="text-xs text-gray-500 font-mono">{r.user_id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-gray-300 font-mono">
                        {r.budget}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-gray-300">
                      {r.payment_method}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        r.status === 'pending' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' : 
                        r.status === 'approved' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' : 
                        'bg-red-500/10 text-red-400 border border-red-500/20'
                      }`}>
                        {r.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-400 whitespace-nowrap">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          
          {!loading && totalCount > 0 && (
            <div className="px-6 py-4 border-t border-teal-900/30 bg-surface-dark/40 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm">
                <div className="text-gray-400">
                  Showing <span className="text-white font-medium">{(currentPage - 1) * itemsPerPage + 1}</span> to <span className="text-white font-medium">{Math.min(currentPage * itemsPerPage, totalCount)}</span> of <span className="text-white font-medium">{totalCount}</span> entries
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

      {/* Request Details Modal */}
      {selectedRequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm" 
            onClick={() => setSelectedRequest(null)}
          />
          <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col bg-surface-card border border-teal-900/40 rounded-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between bg-surface-dark/50 shrink-0">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <CreditCard className="w-5 h-5 text-teal-400" />
                Paid Request Details <span className="text-gray-500 font-mono text-sm ml-2">#{selectedRequest.request_id}</span>
              </h2>
              <button 
                onClick={() => setSelectedRequest(null)}
                className="text-gray-400 hover:text-white transition-colors"
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
                    {selectedRequest.user_avatar ? (
                      <img src={selectedRequest.user_avatar} alt="" className="w-10 h-10 rounded-full" />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-gray-800 flex items-center justify-center font-bold">
                        {selectedRequest.user_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium text-white">{selectedRequest.user_name}</div>
                      <div className="text-gray-500 font-mono text-xs">{selectedRequest.user_id}</div>
                    </div>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2">Status</div>
                  <div className="flex items-center h-[66px] px-4 bg-surface-darker rounded-lg border border-white/5">
                    <span className={`px-3 py-1 rounded-md text-sm font-medium ${
                      selectedRequest.status === 'pending' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' : 
                      selectedRequest.status === 'approved' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' : 
                      'bg-red-500/10 text-red-400 border border-red-500/20'
                    }`}>
                      {selectedRequest.status.toUpperCase()}
                    </span>
                  </div>
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5">Budget</div>
                  <div className="text-teal-300 font-mono text-sm">{selectedRequest.budget}</div>
                </div>
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5">Payment Method</div>
                  <div className="text-gray-300">{selectedRequest.payment_method}</div>
                </div>
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5">Created At</div>
                  <div className="text-gray-400">{new Date(selectedRequest.created_at).toLocaleString()}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5">SFW / NSFW</div>
                  <div className="text-gray-300">{selectedRequest.sfw_nsfw}</div>
                </div>
                <div className="bg-surface-darker p-4 rounded-lg border border-white/5 space-y-1">
                  <div className="text-gray-500 text-xs flex items-center gap-1.5">Use Case</div>
                  <div className="text-gray-300">{selectedRequest.use_case}</div>
                </div>
              </div>

              <div>
                <div className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-2">Request Content</div>
                <div className="bg-surface-darker p-4 rounded-lg border border-teal-900/40 text-gray-300 whitespace-pre-wrap leading-relaxed shadow-inner">
                  {selectedRequest.content}
                </div>
              </div>
            </div>
            
            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-white/5 bg-surface-dark/30 flex justify-end gap-3">
              <button 
                onClick={() => setSelectedRequest(null)}
                className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
