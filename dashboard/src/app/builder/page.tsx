"use client";

import { useEffect, useState, Children } from "react";
import { Send, Plus, Trash2, ShieldAlert, Sparkles, MessageSquare, AlertTriangle, Layers } from "lucide-react";
import { useGuild } from "../../context/GuildContext";
import { apiFetch } from "../../lib/api";
import ReactMarkdown from "react-markdown";

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
    .replace(/<#(\d+)>/g, "[mention-channel:$1](https://discord.com)")
    .replace(/<:([\w_]+):(\d+)>/g, "[emoji-static:$1:$2](https://discord.com)")
    .replace(/<a:([\w_]+):(\d+)>/g, "[emoji-animated:$1:$2](https://discord.com)");

  const components: any = {
    a: ({ href, children }: any) => {
      const text = children?.[0];
      if (typeof text === "string") {
        if (text.startsWith("emoji-static:")) {
          const parts = text.split(":");
          const name = parts[1];
          const id = parts[2];
          return (
            <img
              src={`https://cdn.discordapp.com/emojis/${id}.png`}
              alt={`:${name}:`}
              title={`:${name}:`}
              className="inline-block h-[22px] w-[22px] align-bottom select-all mx-0.5"
            />
          );
        }
        if (text.startsWith("emoji-animated:")) {
          const parts = text.split(":");
          const name = parts[1];
          const id = parts[2];
          return (
            <img
              src={`https://cdn.discordapp.com/emojis/${id}.gif`}
              alt={`:${name}:`}
              title={`:${name}:`}
              className="inline-block h-[22px] w-[22px] align-bottom select-all mx-0.5"
            />
          );
        }
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
    p: ({ children }: any) => <div className="whitespace-pre-wrap leading-relaxed mb-2 last:mb-0 break-words text-[14px]">{children}</div>,
    blockquote: ({ children }: any) => {
      const validChildren = Children.toArray(children).filter((child: any) => {
        if (!child) return false;
        if (typeof child === "string" && !child.trim()) return false;
        if (child.props && child.props.children) {
          const inner = child.props.children;
          if (typeof inner === "string" && !inner.trim()) return false;
          if (Array.isArray(inner) && inner.every(item => typeof item === "string" && !item.trim())) return false;
        }
        return true;
      });
      return (
        <blockquote className="border-l-[4px] border-[#4e5058] pl-4 my-1.5 text-[#dbdee1] space-y-1 [&_p]:mb-0 [&_div]:mb-0">
          {validChildren}
        </blockquote>
      );
    },
    ul: ({ children }: any) => <ul className="list-disc list-outside pl-6 space-y-1 my-1.5">{children}</ul>,
    ol: ({ children }: any) => <ol className="list-decimal list-outside pl-6 space-y-1 my-1.5">{children}</ol>,
    li: ({ children }: any) => (
      <li className="text-[14px] text-[#dbdee1] leading-relaxed break-words pl-1 [&_p]:!mb-0 [&_div]:!mb-0">
        {children}
      </li>
    ),
    h1: ({ children }: any) => <h1 className="font-extrabold text-white text-[20px] mt-4 mb-2">{children}</h1>,
    h2: ({ children }: any) => <h2 className="font-bold text-white text-[17px] mt-3.5 mb-1.5">{children}</h2>,
    h3: ({ children }: any) => <h3 className="font-semibold text-white text-[15px] mt-3 mb-1">{children}</h3>,
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

type Channel = {
  id: string;
  name: string;
};

type Role = {
  id: string;
  name: string;
};

type EmbedField = {
  name: string;
  value: string;
  inline: boolean;
};

type EmbedData = {
  title: string;
  description: string;
  color: string;
  image: string;
  footer: string;
  fields: EmbedField[];
};

type ReactionRole = {
  emoji: string;
  role_id: string;
};

export default function MessageBuilderPage() {
  const { guilds, selectedGuildId } = useGuild();
  const currentGuild = guilds.find((g) => g.id === selectedGuildId);
  const isAdmin = currentGuild?.access_level === "admin";

  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  // Form states
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [messageId, setMessageId] = useState("");
  const [messageText, setMessageText] = useState("");
  const [threadName, setThreadName] = useState("");
  const [reactionRoles, setReactionRoles] = useState<ReactionRole[]>([]);
  
  // List of embeds (max 10)
  const [embeds, setEmbeds] = useState<EmbedData[]>([]);
  const [activeEmbedIdx, setActiveEmbedIdx] = useState<number | null>(null);
  
  const [suppressNotifications, setSuppressNotifications] = useState(false);
  const [singleChoice, setSingleChoice] = useState(false);
  
  const [customChannelId, setCustomChannelId] = useState("");
  const [isCustomChannel, setIsCustomChannel] = useState(false);

  // Auto-fetch message content on ID paste
  useEffect(() => {
    if (!messageId || !selectedGuildId || selectedGuildId === "0") return;
    
    const cleanId = messageId.trim();
    if (!/^\d{17,20}$/.test(cleanId)) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const params = new URLSearchParams();
    const activeChan = isCustomChannel ? customChannelId : selectedChannelId;
    if (activeChan && activeChan !== "0") {
      params.set("channel_id", activeChan);
    }

    apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/messages/${cleanId}?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error("Message not found or inaccessible.");
        return res.json();
      })
      .then((data) => {
        if (data.channel_id) {
          const exists = channels.some((c) => c.id === data.channel_id);
          if (exists) {
            setIsCustomChannel(false);
            setSelectedChannelId(data.channel_id);
          } else {
            setIsCustomChannel(true);
            setCustomChannelId(data.channel_id);
          }
        }
        if (data.message_text !== undefined) setMessageText(data.message_text);
        if (data.embeds) {
          setEmbeds(data.embeds);
          if (data.embeds.length > 0) {
            setActiveEmbedIdx(0);
          }
        }
        if (data.reaction_roles) setReactionRoles(data.reaction_roles);
        if (data.thread_name) setThreadName(data.thread_name);
        if (data.single_choice !== undefined) setSingleChoice(data.single_choice);
      })
      .catch((err) => {
        console.error("Failed to auto-retrieve message info:", err);
      });
  }, [messageId, selectedGuildId, channels]);

  useEffect(() => {
    if (!selectedGuildId || selectedGuildId === "0" || !isAdmin) {
      setLoading(false);
      return;
    }

    setLoading(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    Promise.all([
      apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/channels`).then((res) => res.json()),
      apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/roles`).then((res) => res.json()),
    ])
      .then(([channelsData, rolesData]) => {
        const textChannels = channelsData.channels || [];
        setChannels(textChannels);
        if (textChannels.length > 0) {
          setSelectedChannelId(textChannels[0].id);
        }
        setRoles(rolesData.roles || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error loading builder data:", err);
        setLoading(false);
      });
  }, [selectedGuildId, isAdmin]);

  // Embed methods
  const handleAddEmbed = () => {
    if (embeds.length >= 10) return;
    const newEmbed: EmbedData = {
      title: "",
      description: "",
      color: "#5865F2",
      image: "",
      footer: "",
      fields: [],
    };
    setEmbeds([...embeds, newEmbed]);
    setActiveEmbedIdx(embeds.length);
  };

  const handleRemoveEmbed = (idx: number) => {
    const updated = embeds.filter((_, i) => i !== idx);
    setEmbeds(updated);
    if (updated.length === 0) {
      setActiveEmbedIdx(null);
    } else {
      setActiveEmbedIdx(Math.max(0, idx - 1));
    }
  };

  const handleUpdateEmbedField = (key: keyof EmbedData, value: any) => {
    if (activeEmbedIdx === null) return;
    const updated = [...embeds];
    updated[activeEmbedIdx] = { ...updated[activeEmbedIdx], [key]: value };
    setEmbeds(updated);
  };

  // Embed child fields methods
  const handleAddField = () => {
    if (activeEmbedIdx === null) return;
    const activeEmbed = embeds[activeEmbedIdx];
    if (activeEmbed.fields.length >= 25) return;

    const updatedFields = [
      ...activeEmbed.fields,
      { name: "Field Title", value: "Field Value", inline: true },
    ];
    handleUpdateEmbedField("fields", updatedFields);
  };

  const handleUpdateField = (fieldIdx: number, key: keyof EmbedField, value: any) => {
    if (activeEmbedIdx === null) return;
    const activeEmbed = embeds[activeEmbedIdx];
    const updatedFields = [...activeEmbed.fields];
    updatedFields[fieldIdx] = { ...updatedFields[fieldIdx], [key]: value };
    handleUpdateEmbedField("fields", updatedFields);
  };

  const handleRemoveField = (fieldIdx: number) => {
    if (activeEmbedIdx === null) return;
    const activeEmbed = embeds[activeEmbedIdx];
    const updatedFields = activeEmbed.fields.filter((_, i) => i !== fieldIdx);
    handleUpdateEmbedField("fields", updatedFields);
  };

  // Reaction Roles methods
  const handleAddReactionRole = () => {
    if (roles.length === 0) return;
    setReactionRoles([...reactionRoles, { emoji: "⭐", role_id: roles[0].id }]);
  };

  const handleUpdateReactionRole = (index: number, key: keyof ReactionRole, value: string) => {
    const updated = [...reactionRoles];
    updated[index] = { ...updated[index], [key]: value };
    setReactionRoles(updated);
  };

  const handleRemoveReactionRole = (index: number) => {
    setReactionRoles(reactionRoles.filter((_, idx) => idx !== index));
  };

  const handleSendMessage = async () => {
    if (sending) return;
    const targetChannel = isCustomChannel ? customChannelId : selectedChannelId;
    if (!targetChannel) {
      alert("Please select or enter a target channel!");
      return;
    }
    
    // Filter out completely empty embeds
    const nonOptionEmbeds = embeds.filter(e => {
      return e.title || e.description || e.image || e.footer || e.fields.length > 0;
    });

    if (!messageText && nonOptionEmbeds.length === 0) {
      alert("Please enter either message text or design at least one embed!");
      return;
    }

    setSending(true);
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    const payload = {
      channel_id: targetChannel,
      message_id: messageId || null,
      message_text: messageText || null,
      embeds: nonOptionEmbeds.length > 0 ? nonOptionEmbeds : null,
      thread_name: threadName || null,
      reaction_roles: reactionRoles.length > 0 ? reactionRoles : null,
      suppress_notifications: suppressNotifications,
      single_choice: singleChoice,
    };

    try {
      const res = await apiFetch(`${apiUrl}/api/guilds/${selectedGuildId}/builder/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to send");
      }

      alert(messageId ? "Message updated successfully!" : "Message successfully sent to Discord!");
      setMessageText("");
      setThreadName("");
      setReactionRoles([]);
      setEmbeds([]);
      setActiveEmbedIdx(null);
      setMessageId("");
      setSuppressNotifications(false);
      setCustomChannelId("");
      setIsCustomChannel(false);
    } catch (err: any) {
      console.error(err);
      alert(`Error sending message: ${err.message}`);
    } finally {
      setSending(false);
    }
  };

  if (!selectedGuildId || selectedGuildId === "0") {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-gray-400">
        <Send className="w-16 h-16 text-teal-600/30 mb-4" />
        <p className="text-lg font-medium">Please select a Discord Server from the sidebar to use the Message Builder.</p>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="max-w-md mx-auto mt-[10vh] text-center space-y-4">
        <ShieldAlert className="w-16 h-16 text-red-500 mx-auto animate-bounce" />
        <h2 className="text-xl font-bold text-white">Access Denied</h2>
        <p className="text-sm text-gray-400">
          The Message Builder tool is highly restricted. Only Server Administrators and Team Leaders have permissions to draft and send broadcasts.
        </p>
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

  const activeEmbed = activeEmbedIdx !== null ? embeds[activeEmbedIdx] : null;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-teal-950/40 pb-4">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-wide">Message Builder</h2>
          <p className="text-sm text-gray-400 mt-1">Draft and publish styled messages, multiple embeds, threads, and reaction roles, or edit existing posts.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Builder Form Column */}
        <div className="lg:col-span-7 space-y-6">
          
          {/* Target Channel Selector */}
          <div className="bg-surface-dark border border-teal-950/40 rounded-xl p-5 space-y-4">
            <div className="flex items-center gap-2 text-teal-400 font-semibold text-sm uppercase tracking-wider">
              <MessageSquare className="w-4 h-4" />
              1. Delivery Settings
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs text-gray-400 font-medium">Broadcast Channel</label>
                <select
                  value={isCustomChannel ? "custom" : selectedChannelId}
                  onChange={(e) => {
                    if (e.target.value === "custom") {
                      setIsCustomChannel(true);
                    } else {
                      setIsCustomChannel(false);
                      setSelectedChannelId(e.target.value);
                    }
                  }}
                  className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500/40 animate-none"
                >
                  <option value="custom">⚙️ Custom Channel/Thread ID...</option>
                  {channels.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs text-gray-400 font-medium">Edit Message ID (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. 112233445566778899"
                  value={messageId}
                  onChange={(e) => setMessageId(e.target.value)}
                  className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 placeholder-gray-600 focus:outline-none focus:border-teal-500/40"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs text-gray-400 font-medium">Create Public Thread (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Chat here"
                  value={threadName}
                  onChange={(e) => setThreadName(e.target.value)}
                  disabled={!!messageId}
                  className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 placeholder-gray-600 focus:outline-none focus:border-teal-500/40 disabled:opacity-50"
                />
              </div>
            </div>

            {isCustomChannel && (
              <div className="space-y-1.5 pt-2 border-t border-teal-950/20 animate-in fade-in duration-200">
                <label className="text-xs text-teal-400 font-semibold uppercase tracking-wider">Custom Target Channel/Thread ID</label>
                <input
                  type="text"
                  placeholder="Paste exact 17-20 digit channel or thread ID..."
                  value={customChannelId}
                  onChange={(e) => setCustomChannelId(e.target.value.trim())}
                  className="w-full bg-surface-darker border border-teal-500/30 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500"
                />
              </div>
            )}

            <div className="flex items-center justify-between pt-2 border-t border-teal-950/20">
              <div className="flex flex-col">
                <span className="text-xs text-gray-200 font-medium">Suppress Notifications</span>
                <span className="text-[11px] text-gray-500">Silent Message — Users won't receive a ping or push notification</span>
              </div>
              <button
                type="button"
                onClick={() => setSuppressNotifications(!suppressNotifications)}
                disabled={!!messageId}
                className={`${
                  suppressNotifications ? "bg-teal-500" : "bg-teal-950/40 border border-teal-900/30"
                } relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none items-center disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                <span
                  className={`${
                    suppressNotifications ? "translate-x-[22px] bg-white" : "translate-x-[4px] bg-gray-400"
                  } pointer-events-none inline-block h-4 w-4 transform rounded-full shadow transition duration-200 ease-in-out`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-teal-950/20">
              <div className="flex flex-col">
                <span className="text-xs text-gray-200 font-medium">Exclusive Roles</span>
                <span className="text-[11px] text-gray-500">Single Choice — Users can only select one role at a time</span>
              </div>
              <button
                type="button"
                onClick={() => setSingleChoice(!singleChoice)}
                className={`${
                  singleChoice ? "bg-teal-500" : "bg-teal-950/40 border border-teal-900/30"
                } relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ease-in-out focus:outline-none items-center`}
              >
                <span
                  className={`${
                    singleChoice ? "translate-x-[22px] bg-white" : "translate-x-[4px] bg-gray-400"
                  } pointer-events-none inline-block h-4 w-4 transform rounded-full shadow transition duration-200 ease-in-out`}
                />
              </button>
            </div>
          </div>

          {/* Message Text Area */}
          <div className="bg-surface-dark border border-teal-950/40 rounded-xl p-5 space-y-4">
            <div className="flex justify-between items-center text-teal-400 font-semibold text-sm uppercase tracking-wider">
              <span className="flex items-center gap-2">
                <Sparkles className="w-4 h-4" />
                2. Message Content
              </span>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-gray-400 font-medium">Plain Text Message (Markdown & Mentions allowed)</label>
              <textarea
                rows={4}
                placeholder="Write your message text here..."
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500/40 focus:ring-1 focus:ring-teal-500/40 transition-all"
              />
            </div>
          </div>

          {/* Embeds Configuration Panel */}
          <div className="bg-surface-dark border border-teal-950/40 rounded-xl p-5 space-y-4">
            <div className="flex justify-between items-center">
              <div className="text-teal-400 font-semibold text-sm uppercase tracking-wider flex items-center gap-2">
                <Layers className="w-4 h-4" />
                3. Rich Embed Layouts ({embeds.length}/10)
              </div>
              <button
                onClick={handleAddEmbed}
                disabled={embeds.length >= 10}
                className="text-teal-400 hover:text-teal-300 font-semibold text-xs flex items-center gap-1 border border-teal-500/10 hover:border-teal-500/20 bg-teal-500/5 hover:bg-teal-500/10 px-2.5 py-1.5 rounded-lg transition-all disabled:opacity-50"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Embed
              </button>
            </div>

            {/* Embed Selector Tabs */}
            {embeds.length > 0 && (
              <div className="flex flex-wrap gap-1.5 border-b border-teal-950/30 pb-3">
                {embeds.map((_, idx) => (
                  <div key={idx} className="flex items-center">
                    <button
                      onClick={() => setActiveEmbedIdx(idx)}
                      className={`px-3 py-1.5 rounded-l-lg text-xs font-semibold border-y border-l transition-all ${
                        activeEmbedIdx === idx
                          ? "bg-teal-500/10 text-teal-400 border-teal-500/20"
                          : "bg-surface-darker/60 text-gray-400 hover:text-white border-teal-950/40 hover:bg-teal-950/10"
                      }`}
                    >
                      Embed #{idx + 1}
                    </button>
                    <button
                      onClick={() => handleRemoveEmbed(idx)}
                      className={`px-2 py-1.5 rounded-r-lg border-y border-r transition-all text-red-500 hover:text-red-400 ${
                        activeEmbedIdx === idx
                          ? "bg-teal-500/10 border-teal-500/20"
                          : "bg-surface-darker/60 border-teal-950/40 hover:bg-teal-950/10"
                      }`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Active Embed Editor */}
            {activeEmbedIdx !== null && activeEmbed && (
              <div className="space-y-5 pt-2 animate-in fade-in duration-200">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs text-gray-400 font-medium">Embed #{activeEmbedIdx + 1} Title</label>
                    <input
                      type="text"
                      value={activeEmbed.title}
                      onChange={(e) => handleUpdateEmbedField("title", e.target.value)}
                      className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500/40"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs text-gray-400 font-medium">Color Theme</label>
                    <div className="flex gap-2">
                      <input
                        type="color"
                        value={activeEmbed.color}
                        onChange={(e) => handleUpdateEmbedField("color", e.target.value)}
                        className="bg-transparent border-0 cursor-pointer w-10 h-9"
                      />
                      <input
                        type="text"
                        placeholder="#5865F2"
                        value={activeEmbed.color}
                        onChange={(e) => handleUpdateEmbedField("color", e.target.value)}
                        className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 uppercase focus:outline-none focus:border-teal-500/40"
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs text-gray-400 font-medium">Main Embed Description</label>
                  <textarea
                    rows={4}
                    value={activeEmbed.description}
                    onChange={(e) => handleUpdateEmbedField("description", e.target.value)}
                    className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:ring-1 focus:ring-teal-500/40 focus:border-teal-500/40"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs text-gray-400 font-medium">Image URL Attachment</label>
                    <input
                      type="text"
                      placeholder="https://example.com/image.png"
                      value={activeEmbed.image}
                      onChange={(e) => handleUpdateEmbedField("image", e.target.value)}
                      className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 placeholder-gray-600 focus:outline-none focus:border-teal-500/40"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs text-gray-400 font-medium">Footer Text</label>
                    <input
                      type="text"
                      value={activeEmbed.footer}
                      onChange={(e) => handleUpdateEmbedField("footer", e.target.value)}
                      className="w-full bg-surface-darker border border-teal-950/60 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:border-teal-500/40"
                    />
                  </div>
                </div>

                {/* Fields Editor */}
                <div className="space-y-4 pt-3 border-t border-teal-950/40">
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">Embed Fields ({activeEmbed.fields.length}/25)</span>
                    <button
                      onClick={handleAddField}
                      disabled={activeEmbed.fields.length >= 25}
                      className="text-teal-400 hover:text-teal-300 font-semibold text-xs flex items-center gap-1 border border-teal-500/10 hover:border-teal-500/20 bg-teal-500/5 hover:bg-teal-500/10 px-2.5 py-1.5 rounded-lg transition-all"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Embed Field
                    </button>
                  </div>

                  <div className="space-y-3">
                    {activeEmbed.fields.map((field, idx) => (
                      <div key={idx} className="bg-surface-darker/60 border border-teal-950/40 rounded-lg p-3 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-teal-400 font-semibold uppercase">Field #{idx + 1}</span>
                          <button onClick={() => handleRemoveField(idx)} className="text-red-500 hover:text-red-400 p-0.5">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                          <div className="md:col-span-5 space-y-1">
                            <label className="text-[10px] text-gray-500 uppercase font-semibold">Title</label>
                            <input
                              type="text"
                              value={field.name}
                              onChange={(e) => handleUpdateField(idx, "name", e.target.value)}
                              className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2.5 py-1.5 focus:outline-none"
                            />
                          </div>

                          <div className="md:col-span-5 space-y-1">
                            <label className="text-[10px] text-gray-500 uppercase font-semibold">Value</label>
                            <input
                              type="text"
                              value={field.value}
                              onChange={(e) => handleUpdateField(idx, "value", e.target.value)}
                              className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2.5 py-1.5 focus:outline-none"
                            />
                          </div>

                          <div className="md:col-span-2 flex flex-col justify-end items-center pb-2 space-y-1 select-none">
                            <label className="text-[10px] text-gray-500 uppercase font-semibold">Inline</label>
                            <input
                              type="checkbox"
                              checked={field.inline}
                              onChange={(e) => handleUpdateField(idx, "inline", e.target.checked)}
                              className="rounded border-teal-950/60 text-teal-500 focus:ring-teal-500/40 bg-surface-dark"
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Reaction Roles Panel */}
          <div className="bg-surface-dark border border-teal-950/40 rounded-xl p-5 space-y-4">
            <div className="flex justify-between items-center">
              <div className="text-teal-400 font-semibold text-sm uppercase tracking-wider">
                4. Reaction Role Triggers
              </div>
              <button
                onClick={handleAddReactionRole}
                className="text-teal-400 hover:text-teal-300 font-semibold text-xs flex items-center gap-1 border border-teal-500/10 hover:border-teal-500/20 bg-teal-500/5 hover:bg-teal-500/10 px-2.5 py-1.5 rounded-lg transition-all"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Reaction Role
              </button>
            </div>

            <div className="space-y-2.5">
              {reactionRoles.length === 0 ? (
                <div className="text-center py-4 text-xs text-gray-500 bg-surface-darker/35 border border-dashed border-teal-950/40 rounded-lg">
                  No reaction roles configured. Users will not get roles on react.
                </div>
              ) : (
                reactionRoles.map((rr, idx) => (
                  <div key={idx} className="flex gap-3 items-center bg-surface-darker/60 border border-teal-950/40 rounded-lg p-3">
                    <div className="space-y-1 shrink-0 w-16">
                      <label className="text-[10px] text-gray-500 uppercase block font-semibold">Emoji</label>
                      <input
                        type="text"
                        placeholder="⭐"
                        value={rr.emoji}
                        onChange={(e) => handleUpdateReactionRole(idx, "emoji", e.target.value)}
                        className="w-full text-center bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2 py-1.5 focus:outline-none"
                      />
                    </div>

                    <div className="space-y-1 flex-1">
                      <label className="text-[10px] text-gray-500 uppercase block font-semibold">Assigned Role</label>
                      <select
                        value={rr.role_id}
                        onChange={(e) => handleUpdateReactionRole(idx, "role_id", e.target.value)}
                        className="w-full bg-surface-dark border border-teal-950/60 rounded-lg text-xs text-white px-2.5 py-1.5 focus:outline-none"
                      >
                        {roles.map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <button onClick={() => handleRemoveReactionRole(idx)} className="text-red-500 hover:text-red-400 mt-5 p-1 shrink-0">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Discord Preview Column */}
        <div className="lg:col-span-5 space-y-6">
          <div className="sticky top-6 space-y-4">
            <div className="text-xs font-semibold text-teal-500 uppercase tracking-wider">Live Discord Client Preview</div>

            {/* Discord Mockup Container */}
            <div className="bg-[#313338] text-[#dbdee1] font-['gg_sans','Noto_Sans',sans-serif] text-[16px] rounded-xl p-4 border border-[#1e1f22] shadow-2xl flex gap-4 hover:bg-[#2e3035]/30 transition-colors">
              
              {/* Bot Avatar */}
              <div className="w-10 h-10 rounded-full bg-[#e85a29] text-white flex items-center justify-center font-bold text-[15px] shrink-0 select-none">
                C
              </div>

              {/* Message Block */}
              <div className="flex-1 space-y-1 min-w-0">
                <div className="flex items-center gap-1.5 select-none mb-0.5">
                  <span className="font-medium text-[#f2f3f5] text-[16px] hover:underline cursor-pointer">Carrot</span>
                  <span className="bg-[#5865F2] text-white text-[10px] font-medium px-1 py-[1px] rounded-[3px] uppercase self-center h-fit">Bot</span>
                  <span className="text-[12px] text-[#949ba4] ml-1">Today at {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>

                {/* Text Content */}
                {messageText ? (
                  <div className="whitespace-pre-wrap text-[16px] leading-[1.375rem] text-[#dbdee1] break-words">
                    <DiscordMarkdown content={messageText} channels={channels} roles={roles} />
                    {extractImages(messageText).map((url, i) => (
                      <div key={i} className="mt-2 rounded-lg overflow-hidden max-w-full max-h-64 border border-white/5">
                        <img src={url} alt="GIF preview" className="max-w-full max-h-64 object-contain" />
                      </div>
                    ))}
                  </div>
                ) : (
                  embeds.length === 0 && <p className="text-xs text-[#949ba4] italic">Message content is empty...</p>
                )}

                {/* Embeds List */}
                {embeds.map((emb, idx) => {
                  const hasTitle = bool(emb.title);
                  const hasDesc = bool(emb.description);
                  const hasImage = bool(emb.image);
                  const hasFooter = bool(emb.footer);
                  const hasFields = emb.fields.length > 0;
                  
                  if (!hasTitle && !hasDesc && !hasImage && !hasFooter && !hasFields) {
                    return null;
                  }

                  return (
                    <div 
                      key={idx}
                      className="border-l-[4px] rounded-[4px] bg-[#2b2d31] p-3.5 max-w-[520px] shadow-sm mb-2 animate-in zoom-in-95 duration-200"
                      style={{ borderColor: emb.color || "#202225" }}
                    >
                      {emb.title && (
                        <h4 className="font-semibold text-white text-[16px] mb-1 hover:underline cursor-pointer break-words leading-[1.25rem]">{emb.title}</h4>
                      )}
                      {emb.description && (
                        <div className="whitespace-pre-wrap text-[14px] text-[#dbdee1] leading-[1.375rem] break-words">
                          <DiscordMarkdown content={emb.description} channels={channels} roles={roles} />
                        </div>
                      )}

                      {/* Fields Grid */}
                      {emb.fields.length > 0 && (
                        <div className="grid grid-cols-12 gap-x-2 gap-y-3 mt-3">
                          {emb.fields.map((f, i) => (
                            <div 
                              key={i} 
                              className={`break-words ${
                                f.inline ? "col-span-4" : "col-span-12"
                              }`}
                            >
                              <div className="font-semibold text-[13px] text-[#949ba4]">{f.name}</div>
                              <div className="text-[13px] text-[#dbdee1] mt-0.5 leading-[1.125rem]">{f.value}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Image */}
                      {emb.image && (
                        <img 
                          src={emb.image} 
                          alt="Embed Attachment" 
                          onError={(e) => { e.currentTarget.style.display = "none"; }} 
                          className="rounded max-h-80 object-cover mt-3 w-full border border-[#1e1f22]" 
                        />
                      )}

                      {/* Footer */}
                      {emb.footer && (
                        <div className="text-[11px] text-[#949ba4] font-medium mt-3 border-t border-[#3f4248]/20 pt-2 break-words">
                          {emb.footer}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Reactions list */}
                {reactionRoles.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2.5 select-none">
                    {reactionRoles.map((rr, idx) => (
                      <div key={idx} className="flex items-center gap-1.5 bg-[#2b2d31] hover:bg-[#35373c] border border-[#232428] hover:border-[#4e5058] rounded px-2 py-0.5 text-[#b5bac1] hover:text-[#dbdee1] cursor-pointer text-xs transition-all font-semibold shadow-sm">
                        <span>{rr.emoji || "⭐"}</span>
                        <span className="text-[#949ba4] font-bold">1</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Thread preview box */}
                {threadName && (
                  <div className="flex items-center gap-2 bg-[#2b2d31] border border-[#232428] rounded-md p-2 mt-3 max-w-[520px] select-none shadow-sm">
                    <span className="text-[#5865f2] text-lg font-bold">#</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-white text-xs leading-none break-all">{threadName}</div>
                      <div className="text-[10px] text-[#949ba4] leading-none mt-1">Spawns a public thread under this message</div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Warning block if both empty */}
            {!messageText && embeds.length === 0 && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 flex gap-2 text-xs text-red-200">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
                <span>The message cannot be sent because both plain text and embeds are empty.</span>
              </div>
            )}

            {/* Broadcast action button */}
            <button
              onClick={handleSendMessage}
              disabled={sending || (!messageText && embeds.length === 0)}
              className="w-full bg-teal-500 hover:bg-teal-400 disabled:opacity-50 disabled:cursor-not-allowed text-black font-bold py-3.5 rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-teal-500/10 hover:shadow-teal-400/20 active:scale-[0.99] transition-all duration-200 uppercase tracking-wider text-xs"
            >
              <Send className="w-4 h-4" />
              {sending ? (
                messageId ? "Updating..." : "Sending..."
              ) : (
                messageId ? "Update Message" : "Send Message"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Inline helper for boolean checking
function bool(val: any): boolean {
  return !!val;
}
