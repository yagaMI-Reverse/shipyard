import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Send, Bot, User, ThumbsUp, ThumbsDown, FileText, Plus, MessageSquare,
  LayoutDashboard, RefreshCw, Loader2, ShieldCheck, CircleHelp, Flame,
} from "lucide-react";
import {
  streamChat, listDocs, addDoc, uploadDoc, sendFeedback, getStats, getQuestions, warmup,
  type Source, type DocMeta, type Stats, type QuestionLog,
} from "./lib/api";

type Msg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  grounded?: boolean;
  streaming?: boolean;
  vote?: "up" | "down";
};

const rid = () => Math.random().toString(36).slice(2, 9);

const SUGGESTIONS = [
  "How long does shipping take, and is it free?",
  "What's your return policy?",
  "How do I reset my password?",
];

export default function App() {
  const [tab, setTab] = useState<"chat" | "admin">("chat");
  useEffect(() => {
    warmup(); // wake a sleeping free-tier backend as early as possible
  }, []);
  return (
    <>
      <div className="embers" aria-hidden="true">
        <div
          className="ember-blob"
          style={{
            width: 480,
            height: 480,
            top: "-14%",
            right: "-8%",
            background: "radial-gradient(circle, rgba(255,106,90,.6), transparent 65%)",
          }}
        />
        <div
          className="ember-blob"
          style={{
            width: 420,
            height: 420,
            bottom: "-18%",
            left: "-10%",
            background: "radial-gradient(circle, rgba(255,180,84,.42), transparent 65%)",
            animationDelay: "-12s",
          }}
        />
      </div>

      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 sm:px-6">
        <header className="flex items-center justify-between py-5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-ember to-ember-2 text-white shadow-ember">
              <Flame className="h-5 w-5" />
            </span>
            <div>
              <div className="font-semibold leading-tight text-white">
                Docu<span className="ember-text">Chat</span>
              </div>
              <div className="text-xs text-ink-faint">Document-grounded support AI · RAG + streaming</div>
            </div>
          </div>
          <div className="flex rounded-xl border border-line bg-panel p-1 backdrop-blur-xl">
            <button onClick={() => setTab("chat")} className={tabCls(tab === "chat")}>
              <MessageSquare className="h-4 w-4" /> Chat
            </button>
            <button onClick={() => setTab("admin")} className={tabCls(tab === "admin")}>
              <LayoutDashboard className="h-4 w-4" /> Admin
            </button>
          </div>
        </header>

        <main className="flex-1 pb-8">{tab === "chat" ? <Chat /> : <Admin />}</main>
      </div>
    </>
  );
}

const tabCls = (active: boolean) =>
  `flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-200 ${
    active
      ? "bg-gradient-to-r from-ember to-ember-2 text-white shadow-ember"
      : "text-ink-dim hover:text-white"
  }`;

/* ------------------------------- Chat ------------------------------------ */
function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [msgs]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const aId = rid();
    setMsgs((m) => [
      ...m,
      { id: rid(), role: "user", content: q },
      { id: aId, role: "assistant", content: "", streaming: true },
    ]);
    try {
      await streamChat(
        q,
        (delta) =>
          setMsgs((m) => m.map((x) => (x.id === aId ? { ...x, content: x.content + delta } : x))),
        (meta) =>
          setMsgs((m) =>
            m.map((x) =>
              x.id === aId ? { ...x, streaming: false, sources: meta.sources, grounded: meta.grounded } : x,
            ),
          ),
      );
    } catch (e) {
      setError("Couldn't reach the chatbot backend. Is the API running?");
      setMsgs((m) => m.map((x) => (x.id === aId ? { ...x, streaming: false } : x)));
    } finally {
      setBusy(false);
    }
  }

  async function vote(id: string, v: "up" | "down") {
    setMsgs((m) => m.map((x) => (x.id === id ? { ...x, vote: v } : x)));
    try { await sendFeedback(v); } catch { /* ignore in demo */ }
  }

  return (
    <div className="panel flex h-[68vh] min-h-[460px] flex-col overflow-hidden">
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {msgs.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <span className="flex h-14 w-14 animate-glow-pulse items-center justify-center rounded-2xl bg-gradient-to-br from-ember to-ember-2 text-white">
              <Bot className="h-7 w-7" />
            </span>
            <h2 className="mt-5 text-xl font-semibold text-white">
              Ask about <span className="ember-text">our store</span>
            </h2>
            <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-dim">
              I answer only from the store's documents and show my sources. If it's not in the docs, I'll tell you.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="cursor-pointer rounded-full border border-line bg-panel px-3.5 py-2 text-xs text-ink-dim backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 hover:border-ember/50 hover:text-white hover:shadow-ember"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m) => (
          <div key={m.id} className={`flex animate-msg-in gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                m.role === "user"
                  ? "border border-line bg-raised text-ink-dim"
                  : `bg-gradient-to-br from-ember to-ember-2 text-white ${m.streaming ? "animate-glow-pulse" : ""}`
              }`}
            >
              {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
            </span>
            <div className={`max-w-[78%] ${m.role === "user" ? "text-right" : ""}`}>
              <div
                className={`inline-block rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-gradient-to-r from-ember to-ember-2 text-white shadow-ember"
                    : "border border-line bg-raised text-ink backdrop-blur-xl"
                }`}
              >
                {m.content}
                {m.streaming && m.content && (
                  <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-blink bg-ember-2" />
                )}
                {m.streaming && !m.content && (
                  <span className="inline-flex items-center gap-1 py-0.5" aria-label="Assistant is typing">
                    <span className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-ember" />
                    <span className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-ember-2" style={{ animationDelay: "0.15s" }} />
                    <span className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-ember" style={{ animationDelay: "0.3s" }} />
                  </span>
                )}
              </div>

              {m.role === "assistant" && !m.streaming && (
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {m.grounded && m.sources && m.sources.length > 0 && (
                    <>
                      <span className="inline-flex items-center gap-1 text-xs text-ink-faint">
                        <ShieldCheck className="h-3.5 w-3.5 text-ember-2" /> Sources:
                      </span>
                      {m.sources.map((s) => (
                        <span
                          key={s.title}
                          className="rounded-full border border-line bg-panel px-2.5 py-0.5 text-xs text-ink-dim backdrop-blur-xl transition-colors duration-200 hover:border-ember/40"
                        >
                          <FileText className="mr-1 inline h-3 w-3" />
                          {s.title}
                        </span>
                      ))}
                    </>
                  )}
                  {!m.grounded && (
                    <span className="inline-flex items-center gap-1 text-xs text-ink-faint">
                      <CircleHelp className="h-3.5 w-3.5" /> not found in documents
                    </span>
                  )}
                  {m.content && (
                    <span className="ml-auto flex items-center gap-1">
                      <button
                        onClick={() => vote(m.id, "up")}
                        aria-label="Good answer"
                        className={`cursor-pointer rounded-md p-1 transition-all duration-200 hover:scale-110 ${
                          m.vote === "up" ? "text-emerald-400" : "text-ink-faint hover:text-emerald-400"
                        }`}
                      >
                        <ThumbsUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => vote(m.id, "down")}
                        aria-label="Bad answer"
                        className={`cursor-pointer rounded-md p-1 transition-all duration-200 hover:scale-110 ${
                          m.vote === "down" ? "text-rose-400" : "text-ink-faint hover:text-rose-400"
                        }`}
                      >
                        <ThumbsDown className="h-3.5 w-3.5" />
                      </button>
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {error && <div className="border-t border-line px-5 py-2 text-xs text-rose-400">{error}</div>}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          ask(input);
        }}
        className="flex gap-2 border-t border-line p-3"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about shipping, returns, your account…"
          className="input"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()} className="btn-brand shrink-0">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </form>
    </div>
  );
}

/* ------------------------------- Admin ----------------------------------- */
function Admin() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [qs, setQs] = useState<QuestionLog[]>([]);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [fileBusy, setFileBusy] = useState(false);
  const [fileMsg, setFileMsg] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    const [s, d, q] = await Promise.all([getStats(), listDocs(), getQuestions()]);
    setStats(s); setDocs(d); setQs(q);
  };
  useEffect(() => { refresh().catch(() => {}); }, []);

  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !text.trim()) return;
    setSaving(true);
    try { await addDoc(title, text); setTitle(""); setText(""); await refresh(); }
    finally { setSaving(false); }
  };

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setFileBusy(true);
    setFileMsg(null);
    try {
      const res = await uploadDoc(f);
      setFileMsg(`Added "${res.title}" (${res.chars.toLocaleString()} chars)`);
      await refresh();
    } catch (err) {
      setFileMsg(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setFileBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-4">
        <Kpi label="Documents" value={stats?.documents ?? "—"} />
        <Kpi label="Questions asked" value={stats?.questions_asked ?? "—"} />
        <Kpi label="Answered from docs" value={stats ? `${stats.grounded}/${stats.questions_asked || 0}` : "—"} />
        <Kpi
          label="Satisfaction"
          value={stats?.satisfaction != null ? `${stats.satisfaction}%` : "—"}
          hint={stats ? `+${stats.feedback.up} / -${stats.feedback.down}` : ""}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <form onSubmit={upload} className="panel p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
            <Plus className="h-4 w-4 text-ember" /> Add a document
          </h3>
          <p className="mt-1 text-xs text-ink-dim">The bot will answer new questions from this content immediately.</p>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title (e.g. Warranty Policy)" className="input mt-4" />
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the document text…" rows={5} className="input mt-3 resize-none" />
          <button type="submit" disabled={saving} className="btn-brand mt-3 w-full">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add document
          </button>

          <div className="mt-4 border-t border-line pt-4">
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.txt,.md"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0])}
            />
            <button
              type="button"
              disabled={fileBusy}
              onClick={() => fileInput.current?.click()}
              className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-black/20 px-3 py-2.5 text-sm text-ink-dim transition-all duration-200 hover:border-ember hover:text-white"
            >
              {fileBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4 text-ember" />}
              {fileBusy ? "Reading file…" : "…or upload a file (.pdf, .txt, .md)"}
            </button>
            {fileMsg && <p className="mt-2 text-xs text-ink-faint">{fileMsg}</p>}
          </div>
        </form>

        <div className="panel p-5">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
              <FileText className="h-4 w-4 text-ember" /> Knowledge base
            </h3>
            <button onClick={refresh} className="cursor-pointer text-ink-faint transition-colors hover:text-white" aria-label="Refresh">
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
          <ul className="mt-4 space-y-2">
            {docs.map((d) => (
              <li
                key={d.id}
                className="flex items-center justify-between rounded-lg border border-line bg-black/20 px-3 py-2 text-sm transition-colors duration-200 hover:border-ember/40"
              >
                <span className="text-ink">{d.title}</span>
                <span className="text-xs tabular-nums text-ink-faint">{d.chars.toLocaleString()} chars</span>
              </li>
            ))}
            {docs.length === 0 && <li className="text-sm text-ink-faint">No documents yet.</li>}
          </ul>
        </div>
      </div>

      <div className="panel p-5">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <MessageSquare className="h-4 w-4 text-ember" /> Recent questions
        </h3>
        <div className="mt-4 space-y-2">
          {qs.map((q) => (
            <div
              key={q.id}
              className="rounded-lg border border-line bg-black/20 px-3 py-2 transition-colors duration-200 hover:border-ember/40"
            >
              <div className="flex items-center gap-2 text-sm text-white">
                {q.grounded ? (
                  <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
                ) : (
                  <CircleHelp className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                )}
                {q.q}
              </div>
              <div className="mt-0.5 truncate text-xs text-ink-faint">{q.answer}</div>
            </div>
          ))}
          {qs.length === 0 && <p className="text-sm text-ink-faint">No questions yet — try the Chat tab.</p>}
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="panel p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-ember/40 hover:shadow-ember">
      <div className="text-2xl font-bold tabular-nums text-white">{value}</div>
      <div className="text-xs text-ink-dim">{label}</div>
      {hint && <div className="mt-0.5 text-xs tabular-nums text-ink-faint">{hint}</div>}
    </div>
  );
}
