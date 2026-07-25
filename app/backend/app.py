"""
DocuChat API — a document-grounded support chatbot (RAG) with streaming answers.

Design goals (mirrors a real production support bot):
  * Answers ONLY from the uploaded documents, and cites where each answer came from.
  * Never invents facts: if nothing relevant is found, it says so.
  * Streams the answer token-by-token (SSE) for a "typing like ChatGPT" feel.
  * Collects 👍 / 👎 feedback and exposes simple admin stats.

Retrieval is a dependency-light TF-IDF cosine search, so the demo runs for free
with no API keys. If OPENAI_API_KEY is set, the same retrieved context is handed
to an LLM for a nicer, generated answer — otherwise we return an extractive answer
built from the best-matching sentences. Either path streams and cites sources.
"""

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Kubernetes runtime concerns (JSON logs, probes, metrics, persistence).
# See k8s_runtime.py — kept separate so the demo logic stays untouched.
from k8s_runtime import DocumentStore, configure_logging, install, startup_log

configure_logging()
STORE = DocumentStore()

# Swagger UI moved to /api-docs so our own GET /docs (list documents) isn't
# shadowed by FastAPI's built-in interactive docs route.
app = FastAPI(title="DocuChat API", version="1.0.0", docs_url="/api-docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo; lock to your frontend origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# In-memory store (a demo; swap for Postgres/pgvector in production)
# --------------------------------------------------------------------------- #
DOCS: List[dict] = []            # {id, title, text}
CHUNKS: List[dict] = []          # {doc_id, title, text}
QUESTIONS: List[dict] = []       # {id, q, answer, sources, grounded, ts}
FEEDBACK = {"up": 0, "down": 0}

_vectorizer: Optional[TfidfVectorizer] = None
_matrix = None
MIN_SCORE = 0.06                 # below this we treat retrieval as "no answer"

# --- Vector search (pgvector + Supabase gte-small embeddings) --------------- #
# When SUPABASE_URL + SUPABASE_SECRET_KEY are set, retrieval uses real vector
# embeddings stored in Postgres/pgvector; TF-IDF stays as an automatic fallback
# so the demo still runs with zero configuration.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
VECTOR_ON = bool(SUPABASE_URL and SUPABASE_KEY)
MIN_VEC_SIM = 0.79               # gte-small runs "hot": unrelated ~0.75, related 0.8+
_vector_ready = False


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _embed(texts: List[str]) -> List[List[float]]:
    import httpx

    r = httpx.post(
        f"{SUPABASE_URL}/functions/v1/embed",
        json={"texts": texts},
        headers=_sb_headers(),
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


def _vector_sync() -> None:
    """Re-embed all chunks into pgvector. On any failure we fall back to TF-IDF."""
    global _vector_ready
    if not VECTOR_ON:
        return
    try:
        import httpx

        vecs: List[List[float]] = []
        for i in range(0, len(CHUNKS), 32):
            vecs.extend(_embed([c["text"] for c in CHUNKS[i : i + 32]]))
        rows = [
            {"doc_id": c["doc_id"], "title": c["title"], "content": c["text"], "embedding": json.dumps(v)}
            for c, v in zip(CHUNKS, vecs)
        ]
        httpx.delete(f"{SUPABASE_URL}/rest/v1/docuchat_chunks?id=gt.0", headers=_sb_headers(), timeout=30)
        if rows:
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/docuchat_chunks",
                json=rows,
                headers={**_sb_headers(), "Prefer": "return=minimal"},
                timeout=60,
            )
            r.raise_for_status()
        _vector_ready = True
    except Exception:
        _vector_ready = False


def _chunk(text: str, size: int = 90, overlap: int = 20) -> List[str]:
    words = text.split()
    if len(words) <= size:
        return [text.strip()]
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i : i + size]))
        i += size - overlap
    return out


def _reindex() -> None:
    global _vectorizer, _matrix, CHUNKS
    CHUNKS = [
        {"doc_id": d["id"], "title": d["title"], "text": c}
        for d in DOCS
        for c in _chunk(d["text"])
    ]
    if CHUNKS:
        _vectorizer = TfidfVectorizer(stop_words="english")
        _matrix = _vectorizer.fit_transform([c["text"] for c in CHUNKS])
    else:
        _vectorizer, _matrix = None, None
    _vector_sync()


def _retrieve(query: str, k: int = 3):
    # Preferred path: semantic vector search over pgvector.
    if _vector_ready:
        try:
            import httpx

            qv = _embed([query])[0]
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_docuchat_chunks",
                json={"query_embedding": json.dumps(qv), "match_count": k},
                headers=_sb_headers(),
                timeout=30,
            )
            r.raise_for_status()
            return [
                ({"doc_id": row["doc_id"], "title": row["title"], "text": row["content"]}, float(row["similarity"]))
                for row in r.json()
                if row["similarity"] >= MIN_VEC_SIM
            ]
        except Exception:
            pass  # network hiccup → fall back to TF-IDF below

    if not CHUNKS or _vectorizer is None:
        return []
    q = _vectorizer.transform([query])
    sims = cosine_similarity(q, _matrix)[0]
    order = np.argsort(sims)[::-1][:k]
    return [(CHUNKS[i], float(sims[i])) for i in order if sims[i] >= MIN_SCORE]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _extractive_answer(query: str, hits) -> str:
    """Build an answer from the most query-relevant sentences of the top hits."""
    q_terms = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    scored = []
    for chunk, _ in hits:
        for s in _sentences(chunk["text"]):
            overlap = len(q_terms & {w for w in re.findall(r"[a-z0-9]+", s.lower())})
            if overlap:
                scored.append((overlap, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [s for _, s in scored[:2]] or [hits[0][0]["text"][:280]]
    return " ".join(picked)


async def _llm_stream(query: str, context: str):
    """Optional real-LLM path (OpenAI). Yields text deltas. Falls back on error."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return
    try:
        from openai import OpenAI  # imported lazily; only needed if a key is set

        client = OpenAI(api_key=key)
        prompt = (
            "Answer the question using ONLY the context below. "
            "If the answer is not in the context, say you don't have that "
            "information. Be concise.\n\n"
            f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
        )
        stream = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=0.2,
        )
        for part in stream:
            delta = part.choices[0].delta.content or ""
            if delta:
                yield delta
    except Exception:
        return  # caller falls back to extractive


# --------------------------------------------------------------------------- #
# Langfuse observability (optional)
# When LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY are set, every /chat request is
# traced: a retrieval span (cited sources + scores) and an answer generation,
# tagged with the grounded/refusal outcome. Without keys this is a no-op, so the
# demo keeps running with zero configuration.
# --------------------------------------------------------------------------- #
LANGFUSE = None
if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
    try:
        from langfuse import Langfuse

        LANGFUSE = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception:
        LANGFUSE = None


# --------------------------------------------------------------------------- #
# API models
# --------------------------------------------------------------------------- #
class ChatIn(BaseModel):
    message: str


class DocIn(BaseModel):
    title: str
    text: str


class FeedbackIn(BaseModel):
    vote: str  # "up" | "down"


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"ok": True, "docs": len(DOCS), "chunks": len(CHUNKS), "vector_search": _vector_ready}


@app.get("/docs")
def list_docs():
    return [{"id": d["id"], "title": d["title"], "chars": len(d["text"])} for d in DOCS]


@app.post("/docs")
def add_doc(doc: DocIn):
    if not doc.text.strip():
        raise HTTPException(400, "Empty document")
    d = {"id": str(uuid.uuid4())[:8], "title": doc.title.strip() or "Untitled", "text": doc.text.strip()}
    DOCS.append(d)
    STORE.save(d)  # write-through: survives a pod restart
    _reindex()
    return {"id": d["id"], "title": d["title"]}


@app.delete("/docs/{doc_id}")
def del_doc(doc_id: str):
    global DOCS
    DOCS = [d for d in DOCS if d["id"] != doc_id]
    STORE.delete(doc_id)
    _reindex()
    return {"ok": True}


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".txt", ".md"}


@app.post("/docs/upload")
async def upload_doc(file: UploadFile):
    """Add a document from an uploaded file (.pdf, .txt or .md)."""
    name = file.filename or "upload"
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use .pdf, .txt or .md")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")

    if ext == ".pdf":
        try:
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            raise HTTPException(400, "Could not read this PDF")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="ignore")

    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 40:
        raise HTTPException(
            400,
            "No readable text found in the file (scanned/image-only PDFs need OCR, which the demo doesn't include)",
        )

    d = {"id": str(uuid.uuid4())[:8], "title": os.path.splitext(name)[0][:80], "text": text}
    DOCS.append(d)
    STORE.save(d)  # write-through: survives a pod restart
    _reindex()
    return {"id": d["id"], "title": d["title"], "chars": len(text)}


@app.post("/chat")
async def chat(inp: ChatIn):
    query = inp.message.strip()
    if not query:
        raise HTTPException(400, "Empty message")
    hits = _retrieve(query)
    sources = [{"title": h["title"], "score": round(s, 3)} for h, s in hits]

    lf_root = None
    if LANGFUSE:
        try:
            lf_root = LANGFUSE.start_observation(
                name="rag-chat", as_type="span", input={"query": query}
            )
            lf_retrieve = lf_root.start_observation(
                name="retrieve",
                as_type="span",
                input={"query": query, "engine": "pgvector" if _vector_ready else "tfidf"},
            )
            lf_retrieve.update(output={"hits": len(hits), "sources": sources})
            lf_retrieve.end()
        except Exception:
            lf_root = None

    def _lf_finish(answer: str, grounded: bool, model: str | None = None):
        if not lf_root:
            return
        try:
            if model:
                lf_gen = lf_root.start_observation(
                    name="answer", as_type="generation", model=model, input={"query": query}
                )
                lf_gen.update(output=answer)
                lf_gen.end()
            lf_root.update(
                output={"answer": answer, "grounded": grounded, "sources": sources}
            )
            lf_root.end()
            LANGFUSE.flush()
        except Exception:
            pass

    async def gen():
        record = {"id": str(uuid.uuid4())[:8], "q": query, "ts": time.time()}
        if not hits:
            msg = "I couldn't find anything about that in the documents I have. Could you rephrase, or ask about our shipping, returns, or account topics?"
            for w in msg.split(" "):
                yield f"data: {json.dumps({'delta': w + ' '})}\n\n"
                await asyncio.sleep(0.02)
            record.update(answer=msg, sources=[], grounded=False)
            QUESTIONS.append(record)
            _lf_finish(msg, grounded=False, model="refusal-no-retrieval-hit")
            yield f"data: {json.dumps({'done': True, 'sources': [], 'grounded': False})}\n\n"
            return

        context = "\n\n".join(f"[{h['title']}] {h['text']}" for h, _ in hits)
        collected = ""

        used_llm = False
        async for delta in _llm_stream(query, context):
            used_llm = True
            collected += delta
            yield f"data: {json.dumps({'delta': delta})}\n\n"

        if not used_llm:  # free/extractive fallback
            answer = _extractive_answer(query, hits)
            for w in answer.split(" "):
                collected += w + " "
                yield f"data: {json.dumps({'delta': w + ' '})}\n\n"
                await asyncio.sleep(0.025)

        record.update(answer=collected.strip(), sources=sources, grounded=True)
        QUESTIONS.append(record)
        _lf_finish(
            collected.strip(),
            grounded=True,
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini") if used_llm else "extractive-tfidf",
        )
        yield f"data: {json.dumps({'done': True, 'sources': sources, 'grounded': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# Telegram interface — same RAG brain and knowledge base, chat via Telegram.
# Set TELEGRAM_BOT_TOKEN (+ optional TELEGRAM_WEBHOOK_SECRET) and register the
# webhook: https://api.telegram.org/bot<token>/setWebhook?url=<api>/telegram/webhook
# --------------------------------------------------------------------------- #
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

TG_START_TEXT = (
    "Hi! I'm DocuChat — a document-grounded support bot. I answer ONLY from my "
    "knowledge base (a demo store: shipping, returns, accounts) and I cite my sources.\n\n"
    "Try asking:\n"
    "• How long does shipping take?\n"
    "• What's your return policy?\n"
    "• How do I reset my password?\n\n"
    "If it's not in my documents, I'll say so instead of making something up.\n"
    "Web version + admin panel: https://yagami-reverse.github.io/docuchat/"
)


async def _tg_send(chat_id: int, text: str) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
        )


@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    if TG_SECRET and req.headers.get("x-telegram-bot-api-secret-token") != TG_SECRET:
        raise HTTPException(403, "Bad webhook secret")
    if not TG_TOKEN:
        return {"ok": True}

    update = await req.json()
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return {"ok": True}

    if text.startswith("/start") or text.startswith("/help"):
        await _tg_send(chat_id, TG_START_TEXT)
        return {"ok": True}

    hits = _retrieve(text)
    record = {"id": str(uuid.uuid4())[:8], "q": f"[tg] {text}", "ts": time.time()}
    if not hits:
        answer = (
            "I couldn't find anything about that in my documents. "
            "Try asking about shipping, returns, or account topics."
        )
        record.update(answer=answer, sources=[], grounded=False)
        QUESTIONS.append(record)
        await _tg_send(chat_id, answer)
        return {"ok": True}

    context = "\n\n".join(f"[{h['title']}] {h['text']}" for h, _ in hits)
    answer = ""
    async for delta in _llm_stream(text, context):
        answer += delta
    if not answer:
        answer = _extractive_answer(text, hits)

    sources = [{"title": h["title"], "score": round(s, 3)} for h, s in hits]
    record.update(answer=answer, sources=sources, grounded=True)
    QUESTIONS.append(record)

    await _tg_send(chat_id, f"{answer}\n\n\U0001F4C4 Sources: " + ", ".join(h["title"] for h, _ in hits))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# WhatsApp interface (Meta Cloud API) — same RAG brain, chat via WhatsApp.
# Env: WHATSAPP_TOKEN (access token), WHATSAPP_PHONE_ID (phone number id),
#      WHATSAPP_VERIFY_TOKEN (any string, echoed in Meta's GET handshake),
#      WHATSAPP_APP_SECRET (optional, enables X-Hub-Signature-256 verification).
# Register the webhook in the Meta app dashboard: callback URL
# <api>/whatsapp/webhook + the same verify token, subscribe to "messages".
# --------------------------------------------------------------------------- #
WA_TOKEN = os.getenv("WHATSAPP_TOKEN")
WA_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WA_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WA_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WA_GRAPH_URL = "https://graph.facebook.com/v20.0"

# Meta delivers at-least-once and retries on slow responses — dedupe by wamid.
_WA_SEEN: set = set()
_WA_SEEN_CAP = 500

WA_HELP_TEXT = (
    "Hi! I'm DocuChat — a document-grounded support bot. I answer ONLY from my "
    "knowledge base (a demo store: shipping, returns, accounts) and I cite my sources. "
    "Try: \"How long does shipping take?\" If it's not in my documents, I'll say so."
)


# Last WhatsApp send outcome — exposed via /whatsapp/debug so delivery
# failures (expired token, recipient not allow-listed, closed 24h window) can
# be inspected without shell access to the host. Diagnostic aid; harmless.
_WA_LAST: dict = {}


def _recipient_variants(to: str) -> list[str]:
    """Candidate recipient forms to try, most-canonical first.

    Test numbers only deliver to an allow-list, and the same handset can be
    listed under a different national formatting than the E.164 `from` a
    webhook reports. The clearest case is Kazakhstan/Russia (+7): the domestic
    trunk prefix '8' is sometimes stored after the country code, so an inbound
    `from` of 77XXXXXXXXX must be retried as 787XXXXXXXXX. Production business
    numbers have no allow-list, so this fallback simply never triggers there.
    """
    variants = [to]
    if to.startswith("77") and len(to) == 11:
        variants.append("78" + to[1:])  # 77753206799 -> 787753206799
    return variants


async def _wa_send(to: str, text: str) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        resp = None
        for cand in _recipient_variants(to):
            resp = await client.post(
                f"{WA_GRAPH_URL}/{WA_PHONE_ID}/messages",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": cand,
                    "type": "text",
                    "text": {"body": text[:4000]},
                },
            )
            _WA_LAST.clear()
            _WA_LAST.update(to=cand, status=resp.status_code, body=resp.text[:400], ts=time.time())
            if resp.status_code < 400:
                return
            # Only fall through to an alternate number form on the allow-list
            # error; any other failure (bad token, closed window) won't be
            # fixed by reformatting, so stop and surface it.
            if "131030" not in resp.text:
                break

    if resp is not None and resp.status_code >= 400:
        print(f"[wa] send failed {resp.status_code} to {to}: {resp.text[:300]}", flush=True)


@app.get("/whatsapp/debug")
def whatsapp_debug():
    """Last outbound send result + config presence (no secrets leaked)."""
    return {
        "token_set": bool(WA_TOKEN),
        "phone_id": WA_PHONE_ID,
        "last_send": _WA_LAST or None,
    }


def _wa_signature_ok(raw: bytes, header: str) -> bool:
    if not WA_APP_SECRET:
        return True  # verification disabled until the secret is configured
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(WA_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


@app.get("/whatsapp/webhook")
def whatsapp_verify(req: Request):
    """Meta's one-time subscription handshake: echo hub.challenge back."""
    q = req.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == WA_VERIFY_TOKEN:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Verification failed")


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(req: Request):
    raw = await req.body()
    if not _wa_signature_ok(raw, req.headers.get("x-hub-signature-256", "")):
        raise HTTPException(403, "Bad signature")
    if not (WA_TOKEN and WA_PHONE_ID):
        return {"ok": True}

    try:
        update = json.loads(raw)
    except ValueError:
        return {"ok": True}

    # Payload: entry[].changes[].value.messages[] (statuses[] = delivery receipts, ignored)
    for entry in update.get("entry", []):
        for change in entry.get("changes", []):
            for msg in (change.get("value") or {}).get("messages", []) or []:
                wamid = msg.get("id", "")
                if wamid in _WA_SEEN:
                    continue
                _WA_SEEN.add(wamid)
                if len(_WA_SEEN) > _WA_SEEN_CAP:
                    _WA_SEEN.pop()

                sender = msg.get("from", "")
                if not sender:
                    continue
                if msg.get("type") != "text":
                    await _wa_send(sender, "I can only read text messages for now. " + WA_HELP_TEXT)
                    continue
                text = ((msg.get("text") or {}).get("body") or "").strip()
                if not text:
                    continue
                if text.lower() in ("hi", "hello", "help", "start", "/start", "/help"):
                    await _wa_send(sender, WA_HELP_TEXT)
                    continue

                hits = _retrieve(text)
                record = {"id": str(uuid.uuid4())[:8], "q": f"[wa] {text}", "ts": time.time()}
                if not hits:
                    answer = (
                        "I couldn't find anything about that in my documents. "
                        "Try asking about shipping, returns, or account topics."
                    )
                    record.update(answer=answer, sources=[], grounded=False)
                    QUESTIONS.append(record)
                    await _wa_send(sender, answer)
                    continue

                context = "\n\n".join(f"[{h['title']}] {h['text']}" for h, _ in hits)
                answer = ""
                async for delta in _llm_stream(text, context):
                    answer += delta
                if not answer:
                    answer = _extractive_answer(text, hits)

                sources = [{"title": h["title"], "score": round(s, 3)} for h, s in hits]
                record.update(answer=answer, sources=sources, grounded=True)
                QUESTIONS.append(record)

                await _wa_send(
                    sender,
                    f"{answer}\n\n\U0001F4C4 Sources: " + ", ".join(h["title"] for h, _ in hits),
                )

    return {"ok": True}


@app.post("/feedback")
def feedback(fb: FeedbackIn):
    if fb.vote not in ("up", "down"):
        raise HTTPException(400, "vote must be 'up' or 'down'")
    FEEDBACK[fb.vote] += 1
    return {"ok": True, **FEEDBACK}


@app.get("/questions")
def questions(limit: int = 50):
    return list(reversed(QUESTIONS[-limit:]))


@app.get("/stats")
def stats():
    total = FEEDBACK["up"] + FEEDBACK["down"]
    return {
        "documents": len(DOCS),
        "questions_asked": len(QUESTIONS),
        "grounded": sum(1 for q in QUESTIONS if q.get("grounded")),
        "unanswered": sum(1 for q in QUESTIONS if not q.get("grounded")),
        "feedback": FEEDBACK,
        "satisfaction": round(100 * FEEDBACK["up"] / total) if total else None,
    }


# --------------------------------------------------------------------------- #
# Seed data — a fictional store, matching the "FAQ / shipping / returns" domain
# --------------------------------------------------------------------------- #
def _seed():
    DOCS.extend(
        [
            {
                "id": "shipping",
                "title": "Shipping Policy",
                "text": (
                    "We ship worldwide. Orders are processed within 1-2 business days. "
                    "Standard shipping takes 3-5 business days within the US and 7-14 "
                    "business days internationally. Express shipping (1-2 business days) "
                    "is available at checkout for an extra fee. Shipping is free on all "
                    "orders over 50 dollars. Once your order ships you receive a tracking "
                    "link by email. We currently cannot ship to PO boxes."
                ),
            },
            {
                "id": "returns",
                "title": "Return & Refund Policy",
                "text": (
                    "You can return most items within 30 days of delivery for a full "
                    "refund. Items must be unused and in the original packaging. To start "
                    "a return, open your account, go to Orders, and select Return. Refunds "
                    "are issued to the original payment method within 5-7 business days "
                    "after we receive the item. Final-sale and personalized items cannot be "
                    "returned. Return shipping is free for defective items; otherwise a "
                    "5 dollar return label fee applies."
                ),
            },
            {
                "id": "account",
                "title": "Account & Orders FAQ",
                "text": (
                    "To reset your password, click 'Forgot password' on the sign-in page "
                    "and follow the email link. You can change your shipping address before "
                    "an order ships from Orders > Edit. To cancel an order, contact support "
                    "within 1 hour of placing it. We accept Visa, Mastercard, and PayPal. "
                    "Gift cards never expire and can be combined with one promo code per order."
                ),
            },
        ]
    )
    _reindex()


def _bootstrap() -> None:
    """
    Build the knowledge base, preferring whatever is already in Postgres.

    Fresh volume  → the seed documents are written to the database.
    Restarted pod → the database wins, so uploads survive the restart.
    No DATABASE_URL → original zero-config in-memory behaviour, unchanged.
    """
    STORE.wait_reachable(timeout=float(os.getenv("DB_WAIT_TIMEOUT_S", "90")))
    STORE.init_schema()
    persisted = STORE.load_all()
    if persisted:
        DOCS.extend(persisted)
        _reindex()
        source = "database"
    else:
        _seed()
        for d in DOCS:
            STORE.save(d)
        source = "seed"
    startup_log(
        documents=len(DOCS),
        chunks=len(CHUNKS),
        persistence=STORE.enabled,
        loaded_from=source,
    )


_bootstrap()

# Probes + metrics last, so readiness reflects a fully built index.
install(app, STORE, is_indexed=lambda: _vectorizer is not None)
