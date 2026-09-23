import json
import math
from collections import Counter
from typing import List, Dict, Any, Optional

from app.rag.vector_store import vector_store
from app.rag.text_utils import tokenize, jaccard


class HybridRetriever:
    """
    Multi-query retrieval with hybrid ranking:
      1. each query pulls a candidate pool from the vector store;
      2. vector scores are normalised per query (scores from different queries/backends aren't comparable);
      3. a BM25 keyword score over the pool rewards exact terms (names, metrics, periods) that embeddings blur;
      4. MMR selection trades relevance against redundancy so the deck sees several documents and angles,
         within a result count and character budget.
    """

    VECTOR_WEIGHT = 0.6
    LEXICAL_WEIGHT = 0.4
    MMR_LAMBDA = 0.75
    BM25_K1 = 1.5
    BM25_B = 0.75

    def __init__(self, top_k: int = 15, max_chars: int = 30000):
        self.top_k = top_k
        self.max_chars = max_chars
        self.vector_store = vector_store

    def retrieve(self, project_id: str, query: str, sub_queries: Optional[List[str]] = None,
                 top_k: Optional[int] = None, max_chars: Optional[int] = None) -> List[Dict[str, Any]]:
        top_k = top_k or self.top_k
        max_chars = max_chars or self.max_chars
        queries = list(dict.fromkeys(q for q in [query] + (sub_queries or []) if q and q.strip()))
        pool_size = max(top_k * 2, 20)

        # 1-2. Candidate pool with the best per-query-normalised vector score for each chunk
        candidates: Dict[str, Dict[str, Any]] = {}
        for q in queries:
            results = self.vector_store.similarity_search(project_id, q, top_k=pool_size)
            if not results:
                continue
            scores = [float(r.get("score", 0.0)) for r in results]
            hi, lo = max(scores), min(scores)
            for res, score in zip(results, scores):
                norm = 1.0 if hi == lo else (score - lo) / (hi - lo)
                item = self._to_context(res)
                key = f"{item['document']}_{item['page']}_{item['chunk_index']}"
                if key not in candidates or norm > candidates[key]["vector_score"]:
                    item["vector_score"] = norm
                    candidates[key] = item
        if not candidates:
            return []

        # 3. Hybrid relevance
        items = list(candidates.values())
        lexical = self._bm25(items, [t for q in queries for t in tokenize(q)])
        for item, lex in zip(items, lexical):
            item["relevance_score"] = self.VECTOR_WEIGHT * item["vector_score"] + self.LEXICAL_WEIGHT * lex
            item["_tokens"] = set(tokenize(item["content"]))

        # 4. MMR selection within the budgets
        selected: List[Dict[str, Any]] = []
        used_chars = 0
        remaining = sorted(items, key=lambda x: x["relevance_score"], reverse=True)
        while remaining and len(selected) < top_k:
            def mmr(c):
                redundancy = max((jaccard(c["_tokens"], s["_tokens"]) for s in selected), default=0.0)
                return self.MMR_LAMBDA * c["relevance_score"] - (1 - self.MMR_LAMBDA) * redundancy
            best = max(remaining, key=mmr)
            remaining.remove(best)
            if selected and used_chars + len(best["content"]) > max_chars:
                continue
            selected.append(best)
            used_chars += len(best["content"])

        for item in selected:
            item.pop("_tokens", None)
            item.pop("vector_score", None)
        return selected

    @staticmethod
    def _to_context(res: Dict[str, Any]) -> Dict[str, Any]:
        meta = res.get("metadata", {})
        table_data = meta.get("table_data")
        if isinstance(table_data, str):  # Pinecone stores it as a JSON string
            try:
                table_data = json.loads(table_data)
            except ValueError:
                table_data = None
        return {
            "content": res["content"],
            "document": meta.get("filename", "Unknown Document"),
            "document_id": meta.get("document_id"),
            "page": meta.get("page"),
            "section": meta.get("section", "General"),
            "relevance_score": float(res.get("score", 0.0)),
            "chunk_index": meta.get("chunk_index", 0),
            "is_table": meta.get("is_table", False),
            "table_data": table_data,
        }

    def _bm25(self, items: List[Dict[str, Any]], query_terms: List[str]) -> List[float]:
        """BM25 of each candidate against the union of query terms, scaled to [0, 1]."""
        terms = set(query_terms)
        if not terms:
            return [0.0] * len(items)
        docs = [Counter(tokenize(i["content"])) for i in items]
        n = len(docs)
        avg_len = sum(sum(d.values()) for d in docs) / n or 1.0
        df = {t: sum(1 for d in docs if t in d) for t in terms}
        scores = []
        for d in docs:
            length = sum(d.values())
            s = 0.0
            for t in terms:
                if t not in d:
                    continue
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                tf = d[t]
                s += idf * tf * (self.BM25_K1 + 1) / (tf + self.BM25_K1 * (1 - self.BM25_B + self.BM25_B * length / avg_len))
            scores.append(s)
        hi = max(scores)
        return [s / hi if hi > 0 else 0.0 for s in scores]


retriever = HybridRetriever()
