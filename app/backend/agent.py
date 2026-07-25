"""LangGraph orchestration over DocuChat's retriever.

A multi-step RAG agent built as an explicit state graph:

    plan ──> retrieve ──> assess ──┬──> answer ──> END
              ^                    │
              └────(rewrite)───────┘   (max 2 extra hops)

- ``plan`` picks the next search query (the raw question first, then
  LLM/heuristic rewrites when retrieval comes back thin);
- ``retrieve`` calls the same ``_retrieve`` the production API uses — the
  agent is a client of the app's retriever, not a re-implementation;
- ``assess`` is a conditional edge: enough grounded context → answer,
  otherwise loop for another hop;
- ``answer`` generates strictly from retrieved context and returns sources.
  With no ``GEMINI_API_KEY`` it falls back to the extractive answerer, so the
  demo runs with zero keys — same philosophy as the rest of DocuChat.

Run:  python agent.py "How long does shipping take?"
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END

from app import _retrieve, _extractive_answer  # the production retriever

MAX_HOPS = 3
MIN_SCORE = 0.12  # below this the hop found nothing usable


# --------------------------------------------------------------------------- state
def _extend(a: list, b: list) -> list:
    return a + b


class AgentState(TypedDict, total=False):
    question: str
    query: str
    hops: int
    hits: Annotated[list, _extend]  # accumulated (doc, chunk, score) across hops
    answer: str
    sources: list


# ----------------------------------------------------------------------------- llm
def _gemini(prompt: str) -> str | None:
    """Single Gemini call with bounded retry; None when unconfigured/failing."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    body = json.dumps(
        {"contents": [{"parts": [{"text": prompt}]}]}
    ).encode()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={key}"
    )
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=45) as res:
                data = json.loads(res.read())
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            time.sleep(0.7 * (2**attempt))
    return None


# --------------------------------------------------------------------------- nodes
def plan(state: AgentState) -> AgentState:
    """Choose the next retrieval query. Hop 1 uses the question verbatim;
    later hops rewrite it (LLM if available, keyword fallback otherwise)."""
    if state.get("hops", 0) == 0:
        return {"query": state["question"]}

    rewrite = _gemini(
        "Rewrite this search query to find different relevant passages in a "
        "store-policy knowledge base. Return ONLY the query.\n"
        f"Original question: {state['question']}\n"
        f"Already tried: {state.get('query', '')}"
    )
    if not rewrite:
        # Heuristic fallback: strip filler words to widen the match.
        stop = {"how", "what", "is", "the", "do", "does", "a", "an", "and", "it", "to"}
        rewrite = " ".join(w for w in state["question"].lower().split() if w not in stop)
    return {"query": rewrite}


def retrieve(state: AgentState) -> AgentState:
    """One hop against the production retriever."""
    hits = _retrieve(state["query"], k=3)
    return {"hits": list(hits), "hops": state.get("hops", 0) + 1}


def assess(state: AgentState) -> str:
    """Conditional edge: stop hopping once we have usable context (or ran out
    of budget); otherwise loop back to plan for a rewritten query."""
    usable = [h for h in state.get("hits", []) if h[1] >= MIN_SCORE]
    if usable or state.get("hops", 0) >= MAX_HOPS:
        return "answer"
    return "plan"


def answer(state: AgentState) -> AgentState:
    """Grounded generation from accumulated context, citations attached."""
    # Hits are (chunk, score) pairs, chunk = {doc_id, title, text}.
    # Deduplicate by chunk text, best score first.
    seen: dict[str, tuple] = {}
    for h in sorted(state.get("hits", []), key=lambda x: -x[1]):
        seen.setdefault(h[0]["text"], h)
    hits = [h for h in seen.values() if h[1] >= MIN_SCORE][:4]

    if not hits:
        return {
            "answer": "I couldn't find this in the documentation — flagging for a human.",
            "sources": [],
        }

    context = "\n\n".join(f"[{h[0]['title']}] {h[0]['text']}" for h in hits)
    generated = _gemini(
        "Answer the question using ONLY the context. If the context doesn't "
        "cover it, say you don't know. Be concise.\n\n"
        f"Context:\n{context}\n\nQuestion: {state['question']}"
    )
    if not generated:
        generated = _extractive_answer(state["question"], hits)

    sources = []
    for h in hits:
        title = h[0]["title"]
        if title not in sources:
            sources.append(title)
    return {"answer": generated, "sources": sources}


# --------------------------------------------------------------------------- graph
def build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan)
    g.add_node("retrieve", retrieve)
    g.add_node("answer", answer)
    g.set_entry_point("plan")
    g.add_edge("plan", "retrieve")
    g.add_conditional_edges("retrieve", assess, {"plan": "plan", "answer": "answer"})
    g.add_edge("answer", END)
    return g.compile()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How long does shipping take, and is it free?"
    result = build_graph().invoke({"question": question, "hops": 0, "hits": []})
    print(f"Q: {question}")
    print(f"A: {result['answer']}")
    print(f"Sources: {', '.join(result['sources']) or '—'}")
    print(f"Hops used: {result['hops']}")
