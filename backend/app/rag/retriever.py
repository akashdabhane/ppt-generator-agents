import json
from typing import List, Dict, Any, Optional
from app.rag.vector_store import vector_store


class HybridRetriever:
    def __init__(self, top_k: int = 15):
        self.top_k = top_k
        self.vector_store = vector_store

    def retrieve(self, project_id: str, query: str, sub_queries: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        queries = [query] + (sub_queries or [])
        all_results = []
        seen_keys = set()

        for q in queries:
            results = self.vector_store.similarity_search(project_id, q, top_k=self.top_k)
            for res in results:
                meta = res.get("metadata", {})
                doc_name = meta.get("filename", "Unknown Document")
                page = meta.get("page")
                sec = meta.get("section", "General")
                chunk_id = meta.get("chunk_index", 0)
                
                dedup_key = f"{doc_name}_{page}_{chunk_id}"
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    table_data = meta.get("table_data")
                    if isinstance(table_data, str):  # Pinecone stores it as a JSON string
                        try:
                            table_data = json.loads(table_data)
                        except ValueError:
                            table_data = None
                    all_results.append({
                        "content": res["content"],
                        "document": doc_name,
                        "page": page,
                        "section": sec,
                        "relevance_score": res.get("score", 1.0),
                        "chunk_index": chunk_id,
                        "is_table": meta.get("is_table", False),
                        "table_data": table_data
                    })

        # Rerank by relevance score
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return all_results[:self.top_k]


retriever = HybridRetriever()
