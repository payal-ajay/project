"""
llm/review_agent.py

ESG batch review agent using:
- LangChain (google_genai:gemini-2.5-flash-lite) — exact pattern from official docs
- LangGraph StateGraph — exact pattern from official docs
- FAISS RAG store — emission factor lookup

Official doc patterns used:
  LangChain: https://docs.langchain.com/oss/python/langchain/overview
  LangGraph:  https://docs.langchain.com/oss/python/langgraph/overview
"""

import os
import statistics
import logging
from typing import TypedDict

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ── LangChain: ChatGoogleGenerativeAI (from langchain-google-genai) ───────────
try:
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from langchain_core.messages import HumanMessage, SystemMessage
    LLM_AVAILABLE = bool(os.getenv("GOOGLE_API_KEY"))
except ImportError:
    LLM_AVAILABLE = False
    logger.warning("langchain-google-genai not installed. Run: pip install langchain-google-genai")

# ── LangGraph: StateGraph — exact hello-world pattern from docs ────────────────
try:
    from langgraph.graph import StateGraph, MessagesState, START, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("langgraph not installed. Run: pip install -U langgraph")


# ── Emission factor knowledge base for RAG ────────────────────────────────────
EMISSION_FACTOR_DOCS = [
    "Natural gas: 2.02392 kgCO2e per kWh (DEFRA 2023, Scope 1)",
    "Diesel: 2.68630 kgCO2e per litre (DEFRA 2023, Scope 1)",
    "Petrol/Gasoline: 2.31390 kgCO2e per litre (DEFRA 2023, Scope 1)",
    "LPG: 1.55540 kgCO2e per litre (DEFRA 2023, Scope 1)",
    "UK grid electricity: 0.20493 kgCO2e per kWh (DEFRA 2023, Scope 2)",
    "US average grid electricity: 0.38600 kgCO2e per kWh (EPA 2023, Scope 2)",
    "Short-haul flight economy: 0.255 kgCO2e per passenger-km (DEFRA 2023, with RFI)",
    "Long-haul flight economy: 0.195 kgCO2e per passenger-km (DEFRA 2023, with RFI)",
    "Business class flight: 2.0x economy factor (DEFRA 2023)",
    "Hotel stay UK average: 20.8 kgCO2e per room-night (DEFRA 2023)",
    "Taxi/private hire: 0.149 kgCO2e per km (DEFRA 2023)",
    "Rail travel UK: 0.041 kgCO2e per passenger-km (DEFRA 2023)",
]

_rag_store = None


def get_rag_store():
    """Build FAISS vector store from emission factor docs using Gemini embeddings."""
    global _rag_store
    if _rag_store is not None or not LLM_AVAILABLE:
        return _rag_store
    try:
        # GoogleGenerativeAIEmbeddings — part of langchain-google-genai
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        docs = [Document(page_content=d) for d in EMISSION_FACTOR_DOCS]
        _rag_store = FAISS.from_documents(docs, embeddings)
        logger.info("RAG store built with %d emission factor docs", len(docs))
    except Exception as e:
        logger.warning("Could not build RAG store: %s", e)
    return _rag_store


def rag_lookup_factor(query: str) -> str:
    """Retrieve the most relevant emission factor for a category query."""
    store = get_rag_store()
    if not store:
        return "RAG unavailable — no API key or embedding error"
    try:
        results = store.similarity_search(query, k=1)
        return results[0].page_content if results else "No matching factor found"
    except Exception as e:
        return f"RAG error: {e}"


# ── Rule-based anomaly detection (always runs, LLM or not) ────────────────────

def detect_anomalies(records: list[dict]) -> list[dict]:
    """
    Flag records that are statistical outliers (>3 std devs from batch mean),
    have zero/negative quantities, or are missing dates.
    Always runs — no API key needed.
    """
    quantities = [r["quantity"] for r in records if r.get("quantity") is not None]

    if len(quantities) >= 3:
        mean = statistics.mean(quantities)
        stdev = statistics.stdev(quantities)
        upper_bound = mean + 3 * stdev
    else:
        mean = stdev = upper_bound = None

    for rec in records:
        reasons = []
        qty = rec.get("quantity")

        if qty is None:
            reasons.append("Quantity could not be parsed")
        elif qty <= 0:
            reasons.append(f"Non-positive quantity: {qty}")
        elif upper_bound is not None and qty > upper_bound:
            reasons.append(
                f"Quantity {qty:.2f} is {(qty - mean) / stdev:.1f}σ above batch mean {mean:.2f}"
            )

        if not rec.get("activity_date"):
            reasons.append("Missing activity date")

        rec["is_suspicious"] = bool(reasons)
        rec["suspicion_reason"] = "; ".join(reasons)

    return records


# ── LangGraph review graph ─────────────────────────────────────────────────────
# Pattern from: https://docs.langchain.com/oss/python/langgraph/overview
#
# from langgraph.graph import StateGraph, MessagesState, START, END
# graph = StateGraph(MessagesState)
# graph.add_node(my_node)
# graph.add_edge(START, "my_node")
# graph.add_edge("my_node", END)
# graph = graph.compile()

class ReviewState(TypedDict):
    """State passed between LangGraph nodes."""
    records: list[dict]
    flagged_rows: list[dict]
    analysis_notes: list[str]
    batch_summary: str


def anomaly_check_node(state: ReviewState) -> ReviewState:
    """Node 1: Run rule-based anomaly detection on all records."""
    checked = detect_anomalies(state["records"])
    state["records"] = checked
    state["flagged_rows"] = [r for r in checked if r.get("is_suspicious")]
    return state


def llm_analysis_node(state: ReviewState) -> ReviewState:
    """
    Node 2: For each flagged row, ask Gemini for a one-sentence analyst note.
    Uses LangChain's ChatGoogleGenerativeAI — google_genai:gemini-2.5-flash-lite
    pattern from official docs.
    """
    if not LLM_AVAILABLE or not state["flagged_rows"]:
        state["analysis_notes"] = []
        return state

    # LangChain Google Gemini — from official docs pattern
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0,
    )

    notes = []
    for rec in state["flagged_rows"][:5]:  # Cap at 5 to stay in free tier limits
        messages = [
            SystemMessage(content=(
                "You are an ESG data analyst reviewing emission records. "
                "Given a suspicious record, write ONE sentence: what looks wrong and what to check."
            )),
            HumanMessage(content=(
                f"Category: {rec.get('category')}, "
                f"Quantity: {rec.get('quantity')} {rec.get('unit')}, "
                f"Date: {rec.get('activity_date')}, "
                f"Flag reason: {rec.get('suspicion_reason')}"
            )),
        ]
        try:
            response = llm.invoke(messages)
            notes.append(f"Row {rec.get('_row_index', '?')}: {response.content}")
        except Exception as e:
            notes.append(f"Row {rec.get('_row_index', '?')}: LLM error — {e}")

    state["analysis_notes"] = notes
    return state


def summarize_node(state: ReviewState) -> ReviewState:
    """
    Node 3: Ask Gemini for a plain-English batch summary for the analyst dashboard.
    """
    total = len(state["records"])
    flagged = len(state["flagged_rows"])
    notes_text = "\n".join(state.get("analysis_notes", [])) or "No flagged rows."

    if LLM_AVAILABLE:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0,
        )
        messages = [
            SystemMessage(content=(
                "You are an ESG data analyst. Write a 2-3 sentence summary "
                "for an analyst about to review this batch. Be direct and specific."
            )),
            HumanMessage(content=(
                f"Batch stats: {total} total records, {flagged} flagged.\n"
                f"Analyst notes:\n{notes_text}"
            )),
        ]
        try:
            response = llm.invoke(messages)
            state["batch_summary"] = response.content
        except Exception as e:
            state["batch_summary"] = (
                f"{total} records ingested, {flagged} flagged. LLM summary failed: {e}"
            )
    else:
        state["batch_summary"] = (
            f"{total} records ingested. {flagged} flagged by rule-based checks. "
            f"Set GOOGLE_API_KEY in .env to enable AI analysis."
        )

    return state


def build_review_graph():
    """
    Build the LangGraph StateGraph.
    Exact pattern from https://docs.langchain.com/oss/python/langgraph/overview:

        graph = StateGraph(MyState)
        graph.add_node(my_node)
        graph.add_edge(START, "my_node")
        graph.add_edge("my_node", END)
        graph = graph.compile()
    """
    if not LANGGRAPH_AVAILABLE:
        return None

    graph = StateGraph(ReviewState)

    graph.add_node("anomaly_check", anomaly_check_node)
    graph.add_node("llm_analysis", llm_analysis_node)
    graph.add_node("summarize", summarize_node)

    graph.add_edge(START, "anomaly_check")
    graph.add_edge("anomaly_check", "llm_analysis")
    graph.add_edge("llm_analysis", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()


# ── Public entry point ─────────────────────────────────────────────────────────

def run_review_agent(records: list[dict]) -> dict:
    """
    Run the full review pipeline on a parsed batch.
    Returns: { records (with flags), batch_summary, analysis_notes }
    """
    graph = build_review_graph()

    if graph:
        result = graph.invoke({
            "records": records,
            "flagged_rows": [],
            "analysis_notes": [],
            "batch_summary": "",
        })
        return {
            "records": result["records"],
            "batch_summary": result["batch_summary"],
            "analysis_notes": result["analysis_notes"],
        }

    # Fallback if langgraph not installed
    records = detect_anomalies(records)
    flagged = len([r for r in records if r.get("is_suspicious")])
    return {
        "records": records,
        "batch_summary": f"{len(records)} records processed. {flagged} flagged. Install langgraph for graph execution.",
        "analysis_notes": [],
    }
