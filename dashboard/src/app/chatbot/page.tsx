"use client";

import { useEffect, useState } from "react";
import { MessageSquare, Save, Plus, Trash2, Layers, ShieldAlert, Shield } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useGuild } from "../../context/GuildContext";
import { apiFetch } from "../../lib/api";

const extractImages = (text: string | null): string[] => {
  if (!text) return [];
  const imageRegex = /(https?:\/\/\S+\.(?:png|jpe?g|gif|webp|bmp)(?:\?\S*)?|https?:\/\/media\.tenor\.com\/\S+|https?:\/\/\S+\.giphy\.com\/\S+)/gi;
  const matches = text.match(imageRegex);
  return matches ? Array.from(new Set(matches)) : [];
};

function DiscordMarkdown({ content, channels = [], roles = [] }: { content: string | null; channels?: any[]; roles?: any[] }) {
  if (!content) return null;
  
  let processed = content
    .replace(/<@!?(\d+)>/g, "[mention-user:$1](https://discord.com)")
    .replace(/<@&(\d+)>/g, "[mention-role:$1](https://discord.com)")
    .replace(/<#(\d+)>/g, "[mention-channel:$1](https://discord.com)");

  const components: any = {
    a: ({ href, children }: any) => {
      const text = children?.[0];
      if (typeof text === "string") {
        if (text.startsWith("mention-user:")) {
          const userId = text.split(":")[1];
          return (
            <span className="bg-[#5865f2]/30 text-[#dee0fc] hover:bg-[#5865f2]/40 px-1 py-0.5 rounded font-medium cursor-pointer transition-colors text-[13px] select-none">
              @{userId}
            </span>
          );
        }
        if (text.startsWith("mention-role:")) {
          const roleId = text.split(":")[1];
          const roleName = roles.find(r => r.id === roleId)?.name || roleId;
          return (
            <span className="bg-[#5865f2]/30 text-[#dee0fc] hover:bg-[#5865f2]/40 px-1 py-0.5 rounded font-medium cursor-pointer transition-colors text-[13px] select-none">
              @{roleName}
            </span>
          );
        }
        if (text.startsWith("mention-channel:")) {
          const channelId = text.split(":")[1];
          const channelName = channels.find(c => c.id === channelId)?.name.replace(/^#/, "") || channelId;
          return (
            <span className="bg-[#5865f2]/30 text-[#dee0fc] hover:bg-[#5865f2]/40 px-1 py-0.5 rounded font-medium cursor-pointer transition-colors text-[13px] select-none">
              #{channelName}
            </span>
          );
        }
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-[#00a8fc] hover:underline">
          {children}
        </a>
      );
    },
    p: ({ children }: any) => <p className="whitespace-pre-wrap leading-relaxed mb-2 break-words text-[14px]">{children}</p>,
    code: ({ inline, className, children }: any) => {
      if (inline) {
        return <code className="bg-[#2b2d31] text-[#dbdee1] px-1 py-0.5 rounded font-mono text-[13px]">{children}</code>;
      }
      return (
        <pre className="bg-[#1e1f22] border border-black/30 p-2.5 rounded font-mono text-xs text-[#dbdee1] overflow-x-auto whitespace-pre-wrap my-2.5">
          <code>{children}</code>
        </pre>
      );
    }
  };

  return <ReactMarkdown components={components}>{processed}</ReactMarkdown>;
}

type ChatbotButton = {
  label: string;
  emoji: string | null;
  action: "message" | "menu";
  target: string | null; // Used for action == "menu"
  text: string | null;   // Used for action == "message"
};

type ChatbotMenu = {
  text: string;
  buttons: ChatbotButton[];
};

type ChatbotConfig = {
  main_menu: ChatbotMenu;
  menus: { [key: string]: ChatbotMenu };
  dm_prompt_button?: boolean;
};

export default function ChatbotPage() {
  const { guilds, selectedGuildId } = useGuild();
  const currentGuild = guilds.find((g) => g.id === selectedGuildId);
  const isViewOnly = currentGuild?.access_level === "view";
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<ChatbotConfig | null>(null);
  
  // Selected submenu to edit (null means main menu)
  const [activeMenuId, setActiveMenuId] = useState<string>("main_menu");
  const [newMenuIdInput, setNewMenuIdInput] = useState("");
  
  // Local notification for button test actions in preview
  const [previewNotification, setPreviewNotification] = useState<string | null>(null);
  const [botMessageReply, setBotMessageReply] = useState<string | null>(null);

  useEffect(() => {
    setBotMessageReply(null);
  }, [activeMenuId, selectedGuildId]);

  useEffect(() => {
    if (!selectedGuildId || selectedGuildId === "0") {
      setLoading(false);
      return;
    }

    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/chatbot`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.menus) data.menus = {};
        setConfig(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching chatbot config:", err);
        setLoading(false);
      });
  }, [selectedGuildId]);

  const saveChatbotConfig = async () => {
    if (!config || isViewOnly) return;
    setSaving(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      const res = await apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/chatbot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });

      if (!res.ok) throw new Error("Save failed");
      alert("Chatbot configuration saved successfully!");
    } catch (err) {
      console.error("Error saving chatbot config:", err);
      alert("Failed to save chatbot configuration.");
    } finally {
      setSaving(false);
    }
  };

  const getActiveMenu = (): ChatbotMenu | null => {
    if (!config) return null;
    if (activeMenuId === "main_menu") return config.main_menu;
    return config.menus[activeMenuId] || null;
  };

  const updateActiveMenuText = (text: string) => {
    if (!config) return;
    if (activeMenuId === "main_menu") {
      setConfig({
        ...config,
        main_menu: { ...config.main_menu, text },
      });
    } else {
      setConfig({
        ...config,
        menus: {
          ...config.menus,
          [activeMenuId]: { ...config.menus[activeMenuId], text },
        },
      });
    }
  };

  const addSubmenu = () => {
    if (!config) return;
    const cleanId = newMenuIdInput.trim().toLowerCase().replace(/\s+/g, "-");
    if (!cleanId) return;
    if (cleanId === "main_menu" || config.menus[cleanId]) {
      alert("Menu ID already exists!");
      return;
    }

    setConfig({
      ...config,
      menus: {
        ...config.menus,
        [cleanId]: {
          text: "Edit this menu response text...",
          buttons: [],
        },
      },
    });
    setNewMenuIdInput("");
    setActiveMenuId(cleanId);
  };

  const deleteSubmenu = (menuId: string) => {
    if (!config) return;
    if (!confirm(`Are you sure you want to delete the submenu "${menuId}"?`)) return;

    const newMenus = { ...config.menus };
    delete newMenus[menuId];

    setConfig({
      ...config,
      menus: newMenus,
    });

    if (activeMenuId === menuId) {
      setActiveMenuId("main_menu");
    }
  };

  const addButton = () => {
    const activeMenu = getActiveMenu();
    if (!config || !activeMenu) return;

    const newButton: ChatbotButton = {
      label: "New Button",
      emoji: null,
      action: "message",
      target: null,
      text: "This is a response message.",
    };

    const updatedMenu = {
      ...activeMenu,
      buttons: [...activeMenu.buttons, newButton],
    };

    if (activeMenuId === "main_menu") {
      setConfig({ ...config, main_menu: updatedMenu });
    } else {
      setConfig({
        ...config,
        menus: { ...config.menus, [activeMenuId]: updatedMenu },
      });
    }
  };

  const removeButton = (btnIndex: number) => {
    const activeMenu = getActiveMenu();
    if (!config || !activeMenu) return;

    const updatedMenu = {
      ...activeMenu,
      buttons: activeMenu.buttons.filter((_, idx) => idx !== btnIndex),
    };

    if (activeMenuId === "main_menu") {
      setConfig({ ...config, main_menu: updatedMenu });
    } else {
      setConfig({
        ...config,
        menus: { ...config.menus, [activeMenuId]: updatedMenu },
      });
    }
  };

  const updateButtonField = (btnIndex: number, field: keyof ChatbotButton, value: any) => {
    const activeMenu = getActiveMenu();
    if (!config || !activeMenu) return;

    const updatedButtons = [...activeMenu.buttons];
    updatedButtons[btnIndex] = {
      ...updatedButtons[btnIndex],
      [field]: value,
    };

    // Auto-initialize text/target when action toggles
    if (field === "action") {
      if (value === "menu") {
        updatedButtons[btnIndex].target = "main_menu";
        updatedButtons[btnIndex].text = null;
      } else {
        updatedButtons[btnIndex].target = null;
        updatedButtons[btnIndex].text = "Placeholder message response.";
      }
    }

    const updatedMenu = {
      ...activeMenu,
      buttons: updatedButtons,
    };

    if (activeMenuId === "main_menu") {
      setConfig({ ...config, main_menu: updatedMenu });
    } else {
      setConfig({
        ...config,
        menus: { ...config.menus, [activeMenuId]: updatedMenu },
      });
    }
  };

  // Preview click simulations
  const handlePreviewButtonClick = (btn: ChatbotButton) => {
    if (btn.action === "menu" && btn.target) {
      if (btn.target === "main_menu" || (config && config.menus[btn.target])) {
        setActiveMenuId(btn.target);
        triggerNotification(`Navigated preview to: ${btn.target}`);
      } else {
        triggerNotification(`❌ Target menu "${btn.target}" does not exist!`);
      }
    } else if (btn.action === "message" && btn.text) {
      setBotMessageReply(btn.text);
    }
  };

  const triggerNotification = (text: string) => {
    setPreviewNotification(text);
    setTimeout(() => {
      setPreviewNotification((prev) => (prev === text ? null : prev));
    }, 3000);
  };

  if (!selectedGuildId || selectedGuildId === "0") {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-gray-400">
        <MessageSquare className="w-16 h-16 text-teal-600/30 mb-4" />
        <p className="text-lg font-medium">Please select a Discord Server from the sidebar to configure the Chatbot.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-teal-400">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-teal-500"></div>
      </div>
    );
  }

  const activeMenu = getActiveMenu();

  return (
    <div className="space-y-6 max-w-[90rem] mx-auto pb-12 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-teal-950/40 pb-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-wide">Interactive Chatbot Config</h2>
          <p className="text-sm text-gray-400 mt-1">Design the interactive DMs users receive when clicking "Start Chat".</p>
        </div>
        
        <button
          onClick={saveChatbotConfig}
          disabled={saving || isViewOnly}
          className="bg-teal-500 hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold px-4 py-2 rounded-lg flex items-center gap-2 shadow-lg shadow-teal-500/10 hover:shadow-teal-400/20 transition-all duration-200"
        >
          <Save className="w-4 h-4" />
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>

      {isViewOnly && (
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-4 flex gap-3 text-sm text-yellow-200">
          <ShieldAlert className="w-5 h-5 text-yellow-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-yellow-300">View-Only Mode</span>
            <p className="mt-1 opacity-90">You have moderator access. Changing the chatbot requires server administrator or team leader role.</p>
          </div>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Navigation Sidebar */}
        <div className="lg:col-span-2 bg-surface-dark border border-teal-950/40 rounded-xl p-4 space-y-4">
          <div className="text-xs font-semibold text-teal-500 uppercase tracking-wider">Menus Structure</div>
          
          <div className="space-y-1">
            <button
              onClick={() => setActiveMenuId("main_menu")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all ${
                activeMenuId === "main_menu"
                  ? "bg-teal-500/10 text-teal-400 font-semibold border border-teal-500/20"
                  : "text-gray-400 hover:text-white hover:bg-teal-950/10"
              }`}
            >
              <span className="flex items-center gap-2">
                <Layers className="w-4 h-4 shrink-0" />
                Main Menu
              </span>
            </button>

            {config &&
              Object.keys(config.menus).map((menuId) => (
                <div key={menuId} className="group flex items-center justify-between w-full">
                  <button
                    onClick={() => setActiveMenuId(menuId)}
                    className={`flex-1 text-left px-3 py-2 rounded-lg text-sm transition-all overflow-hidden text-ellipsis ${
                      activeMenuId === menuId
                        ? "bg-teal-500/10 text-teal-400 font-semibold border border-teal-500/20"
                        : "text-gray-400 hover:text-white hover:bg-teal-950/10"
                    }`}
                  >
                    {menuId}
                  </button>
                  {!isViewOnly && (
                    <button
                      onClick={() => deleteSubmenu(menuId)}
                      className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-400 p-1.5 transition-all"
                      title="Delete Menu"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              ))}
          </div>

          {!isViewOnly && (
            <div className="border-t border-teal-950/40 pt-4 space-y-2">
              <label className="text-xs text-gray-400 font-medium uppercase tracking-wider block">Add Sub-menu</label>
              <div className="flex gap-1.5">
                <input
                  type="text"
                  placeholder="e.g. roles"
                  value={newMenuIdInput}
                  onChange={(e) => setNewMenuIdInput(e.target.value)}
                  className="bg-surface-darker border border-teal-950/60 rounded-lg px-2 py-1 text-xs text-white placeholder-gray-500 w-full focus:outline-none focus:border-teal-500/40"
                />
                <button
                  onClick={addSubmenu}
                  className="bg-teal-950/30 hover:bg-teal-950/60 text-teal-400 border border-teal-500/20 rounded-lg p-1.5 transition-all shrink-0"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Content Editor Pane */}
        <div className="lg:col-span-6 space-y-6">
          {activeMenu && (
            <div className="bg-surface-dark border border-teal-950/40 rounded-xl p-5 space-y-6">
              
              {/* Menu Details */}
              <div className="flex items-center justify-between border-b border-teal-950/40 pb-3">
                <h3 className="font-bold text-lg text-teal-400 uppercase tracking-wide">
                  {activeMenuId === "main_menu" ? "Main Menu Editor" : `Sub-menu: ${activeMenuId}`}
                </h3>
              </div>

              {/* General Settings for Chatbot */}
              {activeMenuId === "main_menu" && (
                <div className="bg-teal-950/10 border border-teal-500/10 rounded-lg p-4 mb-2 flex items-center justify-between gap-4">
                  <div className="space-y-0.5">
                    <span className="text-sm text-gray-200 font-medium block">DM Prompt Button</span>
                    <span className="text-xs text-gray-400">When users DM Carrot, reply with an interactive button to start the chatbot</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer shrink-0">
                    <input
                      type="checkbox"
                      disabled={isViewOnly}
                      checked={config?.dm_prompt_button || false}
                      onChange={(e) => {
                        if (!config) return;
                        setConfig({
                          ...config,
                          dm_prompt_button: e.target.checked
                        });
                      }}
                      className="sr-only peer disabled:opacity-50"
                    />
                    <div className="w-11 h-6 bg-surface-darker peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-gray-500 after:border-gray-600 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-teal-500 peer-checked:after:bg-white border border-teal-900/40"></div>
                  </label>
                </div>
              )}

              {/* Response Text area */}
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400 font-semibold uppercase tracking-wider block">Bot Response Embed Text (Markdown allowed)</label>
                <textarea
                  disabled={isViewOnly}
                  rows={4}
                  value={activeMenu.text}
                  onChange={(e) => updateActiveMenuText(e.target.value)}
                  className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2.5 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all font-sans leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
                  placeholder="Type the bot's response message embed text..."
                />
              </div>

              {/* Buttons configuration */}
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">Button Options (Max 24)</span>
                  {!isViewOnly && (
                    <button
                      onClick={addButton}
                      disabled={activeMenu.buttons.length >= 24}
                      className="text-teal-400 hover:text-teal-300 font-medium text-xs flex items-center gap-1 bg-teal-500/5 hover:bg-teal-500/10 px-2.5 py-1.5 border border-teal-500/10 hover:border-teal-500/20 rounded-lg transition-all"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Button
                    </button>
                  )}
                </div>

                <div className="space-y-3.5 max-h-[50vh] overflow-y-auto pr-1">
                  {activeMenu.buttons.length === 0 ? (
                    <div className="text-center py-6 text-xs text-gray-500 bg-surface-darker/35 border border-dashed border-teal-950/40 rounded-lg">
                      No buttons configured for this menu yet. Click "Add Button" to add one.
                    </div>
                  ) : (
                    activeMenu.buttons.map((btn, idx) => (
                      <div key={idx} className="bg-surface-darker/60 border border-teal-950/40 rounded-lg p-4 space-y-4">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <span className="bg-teal-500/10 text-teal-400 text-xs font-bold font-mono px-2 py-0.5 rounded border border-teal-500/10">#{idx + 1}</span>
                            <span className="text-xs text-gray-400 font-medium">Button settings</span>
                          </div>
                          {!isViewOnly && (
                            <button
                              onClick={() => removeButton(idx)}
                              className="text-red-500 hover:text-red-400 p-1"
                              title="Delete Button"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                          <div className="space-y-1">
                            <label className="text-xs text-gray-500 font-semibold uppercase">Label</label>
                            <input
                              type="text"
                              disabled={isViewOnly}
                              value={btn.label}
                              onChange={(e) => updateButtonField(idx, "label", e.target.value)}
                              className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2.5 py-1.5 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                          </div>
                          
                          <div className="space-y-1">
                            <label className="text-xs text-gray-500 font-semibold uppercase">Emoji (Optional)</label>
                            <input
                              type="text"
                              disabled={isViewOnly}
                              placeholder="e.g. 📜"
                              value={btn.emoji || ""}
                              onChange={(e) => updateButtonField(idx, "emoji", e.target.value || null)}
                              className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2.5 py-1.5 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                          </div>

                          <div className="space-y-1">
                            <label className="text-xs text-gray-500 font-semibold uppercase">Action</label>
                            <select
                              disabled={isViewOnly}
                              value={btn.action}
                              onChange={(e) => updateButtonField(idx, "action", e.target.value)}
                              className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2 py-1.5 focus:outline-none focus:border-teal-500/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <option value="message">Send Text Message</option>
                              <option value="menu">Open Sub-menu</option>
                            </select>
                          </div>
                        </div>

                        {btn.action === "menu" ? (
                          <div className="space-y-1">
                            <label className="text-xs text-teal-400/80 font-semibold uppercase tracking-wider">Submenu ID Target</label>
                            {config ? (
                              <select
                                disabled={isViewOnly}
                                value={btn.target || "main_menu"}
                                onChange={(e) => updateButtonField(idx, "target", e.target.value)}
                                className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-3 py-1.5 focus:outline-none focus:border-teal-500/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                <option value="main_menu">main_menu (Main Menu)</option>
                                {Object.keys(config.menus).map((menuId) => (
                                  <option key={menuId} value={menuId}>
                                    {menuId}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                type="text"
                                disabled={isViewOnly}
                                value={btn.target || ""}
                                onChange={(e) => updateButtonField(idx, "target", e.target.value)}
                                className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2.5 py-1.5 focus:outline-none focus:border-teal-500/40 disabled:opacity-50 disabled:cursor-not-allowed"
                              />
                            )}
                          </div>
                        ) : (
                          <div className="space-y-1">
                            <label className="text-xs text-teal-400/80 font-semibold uppercase tracking-wider">Response Message Content (Markdown allowed)</label>
                            <textarea
                              disabled={isViewOnly}
                              rows={3}
                              value={btn.text || ""}
                              onChange={(e) => updateButtonField(idx, "text", e.target.value)}
                              className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-3 py-2.5 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                              placeholder="Type response text sent only to the user..."
                            />
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Live Client Preview Pane */}
        <div className="lg:col-span-4 space-y-4">
          <div className="text-xs font-semibold text-teal-500 uppercase tracking-wider">Live Chatbot Preview (Interactive)</div>

          {/* Discord client Mock container */}
          <div className="bg-[#313338] text-[#dbdee1] font-sans text-sm rounded-xl p-4 border border-[#1e1f22] shadow-2xl flex flex-col gap-4 min-h-[400px] relative">
            
            {/* Main Message Block */}
            <div className="flex gap-3.5">
              {/* Avatar thumbnail */}
              <div className="w-10 h-10 rounded-full bg-[#e85a29] text-white flex items-center justify-center font-bold text-sm shrink-0 select-none">
                C
              </div>

              {/* Message block */}
              <div className="flex-1 space-y-2 min-w-0">
                <div className="flex items-center gap-1.5 select-none">
                  <span className="font-semibold text-white text-[15px] hover:underline cursor-pointer">Carrot</span>
                  <span className="bg-[#5865F2] text-white text-[10px] font-bold px-1 py-0.5 rounded tracking-wide uppercase">Bot</span>
                  <span className="text-xs text-[#949ba4]">Today at {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>

                {/* Rich Embed container */}
                {activeMenu && (
                  <div className="border-l-4 border-[#e85a29] rounded bg-[#2b2d31] p-3.5 max-w-[480px] shadow-sm animate-in zoom-in-95 duration-200 flex flex-col justify-between">
                    <div>
                      <h4 className="font-bold text-white text-[15px] mb-2">🥕 Carrot Assistant</h4>
                      {activeMenu.text ? (
                      <div className="whitespace-pre-wrap text-[14px] text-[#dbdee1] leading-relaxed break-words">
                        <DiscordMarkdown content={activeMenu.text} />
                        {extractImages(activeMenu.text).map((url, i) => (
                          <div key={i} className="mt-2 rounded-lg overflow-hidden max-w-full max-h-64 border border-white/5">
                            <img src={url} alt="attachment preview" className="max-w-full max-h-64 object-contain" />
                          </div>
                        ))}
                      </div>
                    ) : (
                        <p className="text-xs text-[#949ba4] italic">Response embed description is empty...</p>
                      )}
                    </div>

                    <div className="text-[11px] text-[#949ba4] font-medium mt-4 border-t border-[#3f4248]/20 pt-2 flex justify-between items-center">
                      <span>Made by @moriluna</span>
                    </div>
                  </div>
                )}

                {/* Interactive buttons */}
                {activeMenu && activeMenu.buttons.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-3 max-w-[480px]">
                    {activeMenu.buttons.map((btn, idx) => (
                      <button
                        key={idx}
                        onClick={() => handlePreviewButtonClick(btn)}
                        className="flex items-center justify-center gap-1.5 bg-[#4e5058] hover:bg-[#6d6f78] text-white rounded px-3 py-1.5 text-xs font-semibold select-none cursor-pointer transition-all active:scale-[0.98]"
                      >
                        {btn.emoji && <span>{btn.emoji}</span>}
                        <span>{btn.label || `Button #${idx + 1}`}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Ephemeral Message Block */}
            {botMessageReply && (
              <div className="flex gap-3.5 border-t border-[#2b2d31] pt-4 animate-in fade-in slide-in-from-bottom-2 duration-200">
                {/* Avatar thumbnail */}
                <div className="w-10 h-10 rounded-full bg-[#e85a29] text-white flex items-center justify-center font-bold text-sm shrink-0 select-none">
                  C
                </div>

                {/* Message block */}
                <div className="flex-1 space-y-2 min-w-0">
                  <div className="flex items-center gap-1.5 select-none">
                    <span className="font-semibold text-white text-[15px] hover:underline cursor-pointer">Carrot</span>
                    <span className="bg-[#5865F2] text-white text-[10px] font-bold px-1 py-0.5 rounded tracking-wide uppercase">Bot</span>
                    <span className="text-xs text-[#949ba4]">Today at {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>

                  <div className="bg-[#2b2d31] p-3 rounded-lg border border-[#e85a29]/10 max-w-[480px] break-words whitespace-pre-wrap text-[14px]">
                    <DiscordMarkdown content={botMessageReply} />
                    {extractImages(botMessageReply).map((url, i) => (
                      <div key={i} className="mt-2 rounded-lg overflow-hidden max-w-full max-h-64 border border-white/5">
                        <img src={url} alt="GIF preview" className="max-w-full max-h-64 object-contain" />
                      </div>
                    ))}
                  </div>

                  <div className="text-[12px] text-[#949ba4] font-medium flex items-center gap-1.5 select-none">
                    <Shield className="w-3.5 h-3.5 text-[#248046] shrink-0" />
                    <span>Only you can see this • </span>
                    <button onClick={() => setBotMessageReply(null)} className="text-[#00a8fc] hover:underline cursor-pointer">Dismiss message</button>
                  </div>
                </div>
              </div>
            )}

            {/* Bottom floating notification toast */}
            {previewNotification && (
              <div className="absolute bottom-4 left-4 right-4 bg-teal-950/90 text-teal-400 border border-teal-500/20 text-xs font-medium py-2 px-3 rounded-lg flex items-center justify-center text-center shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200">
                {previewNotification}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
