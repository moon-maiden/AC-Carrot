"use client";

import { useEffect, useState } from "react";
import { Settings, Save, AlertTriangle, Plus, X, Info, HelpCircle } from "lucide-react";
import { useGuild } from "../../context/GuildContext";
import { apiFetch } from "../../lib/api";

type GuildConfig = {
  staff_notice_channel_id: string | null;
  staff_commands_channel_id: string | null;
  staff_log_channel_id: string | null;
  team_leader_role_id: string | null;
  moderator_role_id: string | null;
  trial_moderator_role_id: string | null;
  submit_channel_id: string | null;
  review_channel_id: string | null;
  approved_channel_id: string | null;
  approval_log_channel_id: string | null;
  active_limit: number;
  reminder_threshold: number;
  accepted_currencies: string;
  accepted_payments: string;
  banned_terms_regex: string;
  dm_on_warning: boolean;
};

type VerbalReason = {
  id: string;
  label: string;
  text: string;
};

type GuildInfo = {
  id: string;
  name: string;
  icon: string | null;
};

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"verbal" | "paid">("verbal");
  const [verbalSubTab, setVerbalSubTab] = useState<"channels" | "reasons">("channels");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<GuildConfig | null>(null);
  const [reasons, setReasons] = useState<VerbalReason[]>([]);
  const [expandedReasons, setExpandedReasons] = useState<number[]>([]);

  const { guilds, selectedGuildId } = useGuild();
  const currentGuild = guilds.find(g => g.id === selectedGuildId);
  const isViewOnly = currentGuild?.access_level === "view";

  useEffect(() => {
    if (!selectedGuildId || selectedGuildId === "0") {
      setLoading(false);
      return;
    }

    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    Promise.all([
      apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/config`).then(res => res.json()),
      apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/warning-reasons`).then(res => res.json())
    ])
      .then(([configData, reasonsData]) => {
        setConfig(configData);
        setReasons(reasonsData);
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching settings:", err);
        setLoading(false);
      });
  }, [selectedGuildId]);

  const handleConfigChange = (field: keyof GuildConfig, value: any) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const handleIdChange = (field: keyof GuildConfig, value: string) => {
    if (!config) return;
    const val = value.trim();
    setConfig({ ...config, [field]: val === "" ? null : val });
  };

  const handleReasonChange = (index: number, field: keyof VerbalReason, value: string) => {
    const newReasons = [...reasons];
    newReasons[index][field] = value;
    setReasons(newReasons);
  };

  const addReason = () => {
    setReasons([...reasons, { id: "", label: "", text: "" }]);
    setExpandedReasons(prev => [...prev, reasons.length]);
  };

  const removeReason = (index: number) => {
    if (confirm("Are you sure you want to delete this reason?")) {
      setReasons(reasons.filter((_, i) => i !== index));
      setExpandedReasons(prev => prev.filter(i => i !== index).map(i => i > index ? i - 1 : i));
    }
  };

  const toggleReason = (index: number) => {
    setExpandedReasons(prev => prev.includes(index) ? prev.filter(i => i !== index) : [...prev, index]);
  };

  const saveSettings = async () => {
    if (!config) return;
    setSaving(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      // Save Config
      const configRes = await apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
      });
      if (!configRes.ok) throw new Error("Config save failed");

      // Save Reasons
      const reasonsRes = await apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/warning-reasons`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reasons })
      });
      if (!reasonsRes.ok) throw new Error("Reasons save failed");

      alert("Settings saved successfully!");
    } catch (err) {
      console.error("Error saving settings:", err);
      alert("Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const handlePurge = async () => {
    if (confirm("WARNING: This will permanently delete ALL paid requests from the database. Are you absolutely sure?")) {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      await apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/paid-requests/purge`, { method: "POST" });
      alert("Paid requests have been purged.");
    }
  };

  if (!selectedGuildId || selectedGuildId === "0") {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 flex-col gap-3">
        <Settings className="w-10 h-10 text-teal-700/50" />
        <p className="text-sm">Select a server from the top bar to view its settings.</p>
      </div>
    );
  }

  if (loading || !config) {
    return (
      <div className="flex items-center justify-center h-64 text-teal-400">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-400"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight flex items-center gap-3">
            <Settings className="text-teal-400 w-8 h-8" />
            Server Settings
          </h1>
          <p className="text-gray-400 mt-1">Configure bot channels, roles, and automated systems.</p>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-6">
        <aside className="w-full md:w-64 shrink-0 glass-panel border border-teal-900/30 rounded-xl p-4 h-fit">
          <h2 className="text-sm font-semibold text-teal-600/70 uppercase tracking-wider mb-4 px-2">Settings</h2>
          <nav className="flex flex-col gap-1">
            <button
              onClick={() => setActiveTab("verbal")}
              className={`text-left px-3 py-2 rounded-lg transition-colors ${activeTab === 'verbal' ? 'bg-teal-500/10 text-teal-400 font-medium' : 'text-gray-400 hover:text-white hover:bg-teal-500/10'}`}
            >
              Verbal Warnings
            </button>
            <button
              onClick={() => setActiveTab("paid")}
              className={`text-left px-3 py-2 rounded-lg transition-colors ${activeTab === 'paid' ? 'bg-teal-500/10 text-teal-400 font-medium' : 'text-gray-400 hover:text-white hover:bg-teal-500/10'}`}
            >
              Paid Requests
            </button>
          </nav>
        </aside>

        <div className="flex-1 min-w-0 glass-panel border border-teal-900/30 rounded-xl p-6">
                  <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Settings className="w-6 h-6 text-teal-400" />
            Server Configuration
          </h2>
          <button 
            onClick={saveSettings} 
            disabled={saving || isViewOnly}
            className="bg-teal-500 hover:bg-teal-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg font-medium flex items-center gap-2 transition-colors"
          >
            <Save className="w-4 h-4" />
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
        
        {isViewOnly && (
          <div className="bg-yellow-900/20 border border-yellow-500/30 text-yellow-200 p-4 rounded-lg mb-6 flex gap-3">
            <AlertTriangle className="w-5 h-5 text-yellow-400 shrink-0" />
            <div>
              <h3 className="font-semibold text-yellow-400">View-Only Mode</h3>
              <p className="text-sm">You have moderator access to view settings, but Administrator permissions are required to make changes.</p>
            </div>
          </div>
        )}

          {activeTab === 'verbal' && (
            <div className="flex border-b border-teal-900/20 pb-0.5 mb-6 gap-6">
              <button
                onClick={() => setVerbalSubTab("channels")}
                className={`text-sm font-medium transition-all relative pb-3 -mb-[2px] ${
                  verbalSubTab === "channels" 
                    ? "text-teal-400 border-b-2 border-teal-400 font-semibold" 
                    : "text-gray-400 hover:text-white"
                }`}
              >
                Channels & Roles
              </button>
              <button
                onClick={() => setVerbalSubTab("reasons")}
                className={`text-sm font-medium transition-all relative pb-3 -mb-[2px] ${
                  verbalSubTab === "reasons" 
                    ? "text-teal-400 border-b-2 border-teal-400 font-semibold" 
                    : "text-gray-400 hover:text-white"
                }`}
              >
                Warning Reasons
              </button>
            </div>
          )}

          {activeTab === 'verbal' && verbalSubTab === 'channels' && (
            <div className="space-y-8 animate-in fade-in duration-250">
              <div>
                <h3 className="text-sm font-semibold text-teal-600/70 uppercase tracking-wider border-b border-teal-900/30 pb-2 mb-4">Channel & Roles Configuration</h3>

                <div className="bg-teal-900/10 border border-teal-500/20 rounded-lg p-4 mb-6 flex gap-3 text-sm text-teal-100/80">
                  <Info className="w-5 h-5 text-teal-400 shrink-0 mt-0.5" />
                  <div className="space-y-2">
                    <p><strong className="text-teal-300">Staff Roles:</strong> Users with the Team Leader, Moderator, or Trial Moderator roles are granted permission to issue verbal warnings and review pending paid requests.</p>
                    <p><strong className="text-teal-300">Channels:</strong></p>
                    <ul className="list-disc pl-4 space-y-1">
                      <li><strong>Notice Channel:</strong> Where verbal warnings are sent.</li>
                      <li><strong>Commands Channel:</strong> Restrict where Carrot commands can be used.</li>
                      <li><strong>Log Channel:</strong> Receives logs for issued warnings and deleted messages.</li>
                    </ul>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Staff Notice Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Channel where all verbal warning notices are sent.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.staff_notice_channel_id || ""} onChange={e => handleIdChange("staff_notice_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Staff Commands Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">If set, staff commands like !warn are restricted to this channel.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.staff_commands_channel_id || ""} onChange={e => handleIdChange("staff_commands_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Staff Log Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Channel where issued warnings and deleted messages are logged.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.staff_log_channel_id || ""} onChange={e => handleIdChange("staff_log_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Team Leader Role ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Role ID for Team Leaders (can issue warnings and review requests).</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.team_leader_role_id || ""} onChange={e => handleIdChange("team_leader_role_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Moderator Role ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Role ID for Moderators (can issue warnings and review requests).</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.moderator_role_id || ""} onChange={e => handleIdChange("moderator_role_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Trial Moderator Role ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Role ID for Trial Moderators (can issue warnings and review requests).</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.trial_moderator_role_id || ""} onChange={e => handleIdChange("trial_moderator_role_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  
                  <div className="md:col-span-2 mt-4 border-t border-teal-900/20 pt-4 flex items-center justify-between">
                    <div className="space-y-0.5">
                      <label className="text-sm font-medium text-white">
                        DM Users on Verbal Warning
                      </label>
                      <p className="text-xs text-gray-400">
                        When enabled, the bot will automatically direct message (DM) warned users with warning details.
                      </p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={config.dm_on_warning ?? true}
                        onChange={e => handleConfigChange("dm_on_warning", e.target.checked)}
                        className="sr-only peer" 
                      />
                      <div className="w-11 h-6 bg-surface-dark peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-gray-400 after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-500 peer-checked:after:bg-white border border-teal-900/40"></div>
                    </label>
                  </div>
                </div>
              </div>

              <div className="pt-8 border-t border-red-900/30">
                <h3 className="text-sm font-semibold text-red-500/80 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" /> Danger Zone
                </h3>
                <div className="bg-red-900/10 border border-red-500/20 rounded-lg p-4 mb-4 flex gap-3 text-sm text-red-100/80">
                  <Info className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p><strong className="text-red-300">Authorized Personnel Only:</strong> This section is strictly reserved for Server Administrators or Developers.</p>
                    <p>Wiping verbal warnings is an irreversible action that permanently deletes all stored infractions.</p>
                  </div>
                </div>
                <button
                  onClick={async () => {
                    if (confirm("WARNING: This will permanently delete ALL verbal warnings from the database. Are you absolutely sure?")) {
                      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                      await apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/warnings/purge`, { method: "POST" });
                      alert("Verbal warnings have been purged.");
                    }
                  }}
                  className="bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed" disabled={isViewOnly}
                >
                  Purge All Verbal Warnings
                </button>
              </div>

            </div>
          )}

          {activeTab === 'verbal' && verbalSubTab === 'reasons' && (
            <div className="space-y-8 animate-in fade-in duration-250">
              <div>
                <h3 className="text-sm font-semibold text-teal-600/70 uppercase tracking-wider border-b border-teal-900/30 pb-2 mb-5">Verbal Warning Reasons</h3>
                <div className="space-y-4">
                  {reasons.map((reason, idx) => {
                    const isExpanded = expandedReasons.includes(idx);
                    return (
                      <div 
                        key={idx} 
                        className={`bg-surface-dark/40 border rounded-xl overflow-hidden transition-all duration-300 ${
                          isExpanded 
                            ? 'border-teal-500/35 shadow-lg shadow-teal-950/20 bg-surface-darker/60' 
                            : 'border-white/5 hover:border-white/10 hover:bg-surface-dark/60'
                        }`}
                      >
                        {/* Header Row */}
                        <div 
                          className="flex justify-between items-center px-5 py-4 cursor-pointer select-none" 
                          onClick={() => toggleReason(idx)}
                        >
                          <div className="flex items-center gap-4">
                            <div className="flex flex-col">
                              <span className="font-semibold text-gray-100 text-sm tracking-wide">
                                {reason.label || <span className="text-gray-500 italic">Unnamed Reason</span>}
                              </span>
                              <span className="text-xs text-teal-500/70 font-mono mt-0.5">
                                ID: {reason.id || "no_id_set"}
                              </span>
                            </div>
                          </div>
                          
                          <div className="flex items-center gap-3">
                            <button
                              type="button"
                              className={`px-3 py-1.5 rounded-lg text-xs font-semibold tracking-wider transition-all duration-200 ${
                                isExpanded 
                                  ? 'bg-teal-500/20 text-teal-300 border border-teal-500/30' 
                                  : 'bg-surface-darker text-gray-400 hover:text-white border border-white/5 hover:border-white/10'
                              }`}
                            >
                              {isExpanded ? "CLOSE" : "EDIT"}
                            </button>
                            <button 
                              type="button"
                              onClick={(e) => { e.stopPropagation(); removeReason(idx); }} 
                              className="text-red-400 hover:text-red-300 p-2 bg-red-500/5 hover:bg-red-500/15 border border-red-500/10 hover:border-red-500/20 rounded-lg transition-all duration-200" 
                              title="Delete Reason"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        {/* Collapsible Content */}
                        {isExpanded && (
                          <div className="px-5 pb-5 pt-4 border-t border-white/5 bg-surface-darker/30 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div className="space-y-1.5">
                                <label className="text-xs text-gray-400 font-medium tracking-wide uppercase">Reason Key / ID</label>
                                <input 
                                  type="text" 
                                  value={reason.id} 
                                  onChange={e => handleReasonChange(idx, "id", e.target.value)} 
                                  placeholder="e.g. underpricing"
                                  className="w-full bg-surface-dark border border-white/5 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all font-mono" 
                                />
                              </div>
                              <div className="space-y-1.5">
                                <label className="text-xs text-gray-400 font-medium tracking-wide uppercase">Dropdown Label</label>
                                <input 
                                  type="text" 
                                  value={reason.label} 
                                  onChange={e => handleReasonChange(idx, "label", e.target.value)} 
                                  placeholder="e.g. Underpricing"
                                  className="w-full bg-surface-dark border border-white/5 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all" 
                                />
                              </div>
                            </div>

                            <div className="space-y-2">
                              <label className="text-xs text-gray-400 font-medium tracking-wide uppercase">DM Notice Embed Content (Markdown)</label>
                              
                              {/* Explanation Banner */}
                              <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-3 text-xs text-amber-200/90 leading-relaxed space-y-1 flex gap-2.5 items-start">
                                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                                <div>
                                  <span className="font-semibold text-amber-300">Format Notice:</span> Do not start this field with <code className="bg-amber-950/40 px-1 py-0.5 rounded text-amber-400">"due to"</code> or <code className="bg-amber-950/40 px-1 py-0.5 rounded text-amber-400">"for"</code>. The bot automatically prefix-joins this text.
                                  <div className="text-gray-400 mt-1">
                                    Adding them causes redundant phrasing like: <em>"You have received a verbal warning for: <strong>due to</strong> underpricing."</em>
                                  </div>
                                  <div className="text-teal-400/90 mt-1.5">
                                    💡 <strong>Recommended Start:</strong> Write <code className="bg-teal-950/40 px-1 py-0.5 rounded text-teal-300 font-mono">"pricing below minimum..."</code> instead.
                                  </div>
                                </div>
                              </div>

                              <textarea 
                                value={reason.text} 
                                onChange={e => handleReasonChange(idx, "text", e.target.value)} 
                                placeholder="Details sent to the user when warned..."
                                className="w-full bg-surface-dark border border-white/5 rounded-lg text-sm text-white px-3 py-2 min-h-[110px] focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all font-sans leading-relaxed" 
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
                
                <button 
                  onClick={addReason} 
                  className="mt-4 text-teal-400 hover:text-teal-300 bg-teal-500/5 hover:bg-teal-500/10 border border-teal-500/10 hover:border-teal-500/25 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 flex items-center gap-2"
                >
                  <Plus className="w-4 h-4" /> Add New Reason
                </button>
              </div>

            </div>
          )}

          {activeTab === 'paid' && (
            <div className="space-y-8">
              <div>
                <h3 className="text-sm font-semibold text-teal-600/70 uppercase tracking-wider border-b border-teal-900/30 pb-2 mb-4">Channel Configurations</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Submit Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Channel where users submit new paid requests via the button.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.submit_channel_id || ""} onChange={e => handleIdChange("submit_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Review Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Private channel where staff review and approve/reject pending requests.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.review_channel_id || ""} onChange={e => handleIdChange("review_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Approved Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Public channel where approved paid requests are displayed.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.approved_channel_id || ""} onChange={e => handleIdChange("approved_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Approval Log Channel ID
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Channel for audit logs of who approved or rejected requests.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.approval_log_channel_id || ""} onChange={e => handleIdChange("approval_log_channel_id", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-teal-600/70 uppercase tracking-wider border-b border-teal-900/30 pb-2 mb-4">Request Parameters</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Active Limits per User
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Max concurrent active/pending paid requests a user can have.</div></div>
                    </label>
                    <input type="number" disabled={isViewOnly} value={config.active_limit} onChange={e => handleConfigChange("active_limit", parseInt(e.target.value))} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Reminder Threshold (Days)
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Number of days before an active request is considered old/inactive.</div></div>
                    </label>
                    <input type="number" disabled={isViewOnly} value={config.reminder_threshold} onChange={e => handleConfigChange("reminder_threshold", parseInt(e.target.value))} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Accepted Currencies (Regex)
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Regex pattern of currencies allowed. If violated, request form triggers an error.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.accepted_currencies} onChange={e => handleConfigChange("accepted_currencies", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                      Accepted Payments (Comma separated)
                      <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Comma-separated list of payment platforms to display in the form placeholder.</div></div>
                    </label>
                    <input type="text" disabled={isViewOnly} value={config.accepted_payments} onChange={e => handleConfigChange("accepted_payments", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50" />
                  </div>
                </div>
                <div className="mt-4 space-y-1">
                  <label className="text-xs text-gray-400 font-medium uppercase flex items-center gap-1">
                    Banned Terms Regex
                    <div className="group relative flex items-center"><HelpCircle className="w-3.5 h-3.5 text-gray-500 cursor-help" /><div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block w-64 p-2 bg-gray-800 border border-teal-900/50 text-xs text-gray-200 rounded shadow-xl z-50 text-center pointer-events-none whitespace-normal normal-case">Regex pattern of banned items (like robux or crypto). Reject form automatically if found.</div></div>
                  </label>
                  <input type="text" disabled={isViewOnly} value={config.banned_terms_regex} onChange={e => handleConfigChange("banned_terms_regex", e.target.value)} className="w-full bg-surface-dark border border-teal-900/40 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-teal-500/50 font-mono" placeholder="e.g. robux|crypto|btc" />
                </div>
              </div>

              <div className="pt-8 border-t border-red-900/30">
                <h3 className="text-sm font-semibold text-red-500/80 uppercase tracking-wider mb-4 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" /> Danger Zone
                </h3>
                <div className="bg-red-900/10 border border-red-500/20 rounded-lg p-4 mb-4 flex gap-3 text-sm text-red-100/80">
                  <Info className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p><strong className="text-red-300">Authorized Personnel Only:</strong> This section is strictly reserved for Server Administrators or Developers.</p>
                    <p>Purging paid requests is an irreversible action that permanently deletes all history and pending commissions.</p>
                  </div>
                </div>
                <button
                  onClick={() => {
                    const pwd = prompt("Enter Administrator Passcode to unlock this action:");
                    if (pwd !== "admin123") return alert("Unauthorized.");
                    handlePurge();
                  }}
                  className="bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed" disabled={isViewOnly}
                >
                  Purge All Paid Requests
                </button>
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}
