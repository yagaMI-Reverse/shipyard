const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export type Source = { title: string; score: number };
export type DocMeta = { id: string; title: string; chars: number };
export type QuestionLog = { id: string; q: string; answer: string; grounded: boolean; ts: number };
export type Stats = {
  documents: number;
  questions_asked: number;
  grounded: number;
  unanswered: number;
  feedback: { up: number; down: number };
  satisfaction: number | null;
};

/**
 * Stream a chat answer via Server-Sent Events. Calls onDelta for each token
 * chunk and onDone with the sources + grounded flag when finished.
 */
export async function streamChat(
  message: string,
  onDelta: (text: string) => void,
  onDone: (meta: { sources: Source[]; grounded: boolean }) => void,
): Promise<void> {
  const res = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) throw new Error(`Chat failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const evt of events) {
      const line = evt.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const data = JSON.parse(line.slice(5).trim());
      if (data.delta) onDelta(data.delta as string);
      if (data.done) onDone({ sources: data.sources ?? [], grounded: !!data.grounded });
    }
  }
}

/**
 * Wake the API on page load. Free hosts (e.g. Render) spin the service down
 * after inactivity; pinging /health early means it's usually awake by the time
 * the visitor sends their first question.
 */
export const warmup = () => fetch(`${API}/health`).catch(() => {});

export const listDocs = () => fetch(`${API}/docs`).then((r) => r.json() as Promise<DocMeta[]>);

export const addDoc = (title: string, text: string) =>
  fetch(`${API}/docs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, text }),
  }).then((r) => r.json());

/** Upload a .pdf/.txt/.md file into the knowledge base. */
export const uploadDoc = async (file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/docs/upload`, { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
  return data as { id: string; title: string; chars: number };
};

export const sendFeedback = (vote: "up" | "down") =>
  fetch(`${API}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ vote }),
  }).then((r) => r.json());

export const getStats = () => fetch(`${API}/stats`).then((r) => r.json() as Promise<Stats>);

export const getQuestions = () =>
  fetch(`${API}/questions`).then((r) => r.json() as Promise<QuestionLog[]>);
