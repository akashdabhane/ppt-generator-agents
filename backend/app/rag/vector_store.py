import logging
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.embeddings import embedding_service

logger = logging.getLogger(__name__)


class BaseVectorStore(ABC):
    @abstractmethod
    def upsert_chunks(self, project_id: str, chunks: List[Dict[str, Any]]) -> List[str]:
        """Ingest document chunks into vector database."""
        pass

    @abstractmethod
    def similarity_search(
        self,
        project_id: str,
        query: str,
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve top_k relevant chunk passages for RAG query."""
        pass

    @abstractmethod
    def delete_document_chunks(self, project_id: str, document_id: str) -> None:
        """Delete vector records associated with a specific document."""
        pass


class MockInMemoryVectorStore(BaseVectorStore):
    """Fallback in-memory store for development & testing without requiring external vector DB services."""
    def __init__(self):
        self.store: Dict[str, List[Dict[str, Any]]] = {}

    def upsert_chunks(self, project_id: str, chunks: List[Dict[str, Any]]) -> List[str]:
        if project_id not in self.store:
            self.store[project_id] = []
        vector_ids = []
        for chunk in chunks:
            v_id = str(uuid.uuid4())
            item = {
                "vector_id": v_id,
                "content": chunk["content"],
                "metadata": chunk.get("metadata", {}),
                "document_id": chunk.get("metadata", {}).get("document_id")
            }
            self.store[project_id].append(item)
            vector_ids.append(v_id)
        return vector_ids

    def similarity_search(
        self,
        project_id: str,
        query: str,
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        project_chunks = self.store.get(project_id, [])
        if not project_chunks:
            return []
        
        query_terms = query.lower().split()
        results = []
        for chunk in project_chunks:
            content_lower = chunk["content"].lower()
            score = sum(1.0 for term in query_terms if term in content_lower)
            if score > 0 or len(project_chunks) <= top_k:
                results.append({
                    "content": chunk["content"],
                    "metadata": chunk["metadata"],
                    "score": float(score) / (len(query_terms) + 1e-5),
                    "vector_id": chunk["vector_id"]
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete_document_chunks(self, project_id: str, document_id: str) -> None:
        if project_id in self.store:
            self.store[project_id] = [
                c for c in self.store[project_id]
                if c.get("document_id") != document_id
            ]


class PineconeVectorStore(BaseVectorStore):
    """Production-grade Pinecone vector store implementation.
    
    Uses Pinecone Python Client for managed vector search.
    Requires PINECONE_API_KEY and PINECONE_INDEX_NAME in environment.
    """
    def __init__(self):
        self._initialized = False
        self.index = None
        if not settings.PINECONE_API_KEY:
            logger.warning("PINECONE_API_KEY is not set. Falling back to MockInMemoryVectorStore.")
            self._mock_store = MockInMemoryVectorStore()
            return

        try:
            from pinecone import Pinecone, ServerlessSpec
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            index_name = settings.PINECONE_INDEX_NAME or "ppt-generator-rag"
            
            # Check or create serverless index if it doesn't exist
            existing_indexes = [idx.name for idx in pc.list_indexes()]
            if index_name not in existing_indexes:
                try:
                    pc.create_index(
                        name=index_name,
                        dimension=1536,
                        metric="cosine",
                        spec=ServerlessSpec(cloud="aws", region="us-east-1")
                    )
                except Exception as create_err:
                    logger.warning(f"Could not auto-create Pinecone index '{index_name}': {create_err}")

            self.index = pc.Index(index_name)
            self._initialized = True
        except Exception as e:
            logger.warning(f"Failed to initialize Pinecone client ({e}). Using MockInMemoryVectorStore fallback.")
            self._mock_store = MockInMemoryVectorStore()

    @staticmethod
    def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Pinecone metadata only accepts strings, numbers, booleans and lists of strings (no nulls, no nesting)."""
        import json
        clean = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                clean[key] = json.dumps(value)  # Parsed back by HybridRetriever
            else:
                clean[key] = value
        return clean

    def upsert_chunks(self, project_id: str, chunks: List[Dict[str, Any]]) -> List[str]:
        if not self._initialized or not self.index:
            return self._mock_store.upsert_chunks(project_id, chunks)

        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.get_embeddings(texts)
        
        vectors_to_upsert = []
        vector_ids = []
        for idx, chunk in enumerate(chunks):
            v_id = str(uuid.uuid4())
            vector_ids.append(v_id)
            meta = self._sanitize_metadata(chunk.get("metadata", {}))
            meta["project_id"] = project_id
            meta["content"] = chunk["content"][:1000]  # Store preview in metadata
            
            vectors_to_upsert.append({
                "id": v_id,
                "values": embeddings[idx],
                "metadata": meta
            })

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(vectors_to_upsert), batch_size):
            self.index.upsert(
                vectors=vectors_to_upsert[i:i + batch_size],
                namespace=project_id
            )
        return vector_ids

    def similarity_search(
        self,
        project_id: str,
        query: str,
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if not self._initialized or not self.index:
            return self._mock_store.similarity_search(project_id, query, top_k, filter_dict)

        query_vec = embedding_service.get_embedding(query)
        
        query_filter = filter_dict or {}
        query_res = self.index.query(
            namespace=project_id,
            vector=query_vec,
            top_k=top_k,
            include_metadata=True,
            filter=query_filter if query_filter else None
        )

        results = []
        for match in query_res.get("matches", []):
            meta = match.get("metadata", {})
            results.append({
                "content": meta.get("content", ""),
                "metadata": meta,
                "score": float(match.get("score", 0.0)),
                "vector_id": match.get("id")
            })
        return results

    def delete_document_chunks(self, project_id: str, document_id: str) -> None:
        if not self._initialized or not self.index:
            self._mock_store.delete_document_chunks(project_id, document_id)
            return

        try:
            self.index.delete(
                namespace=project_id,
                filter={"document_id": document_id}
            )
        except Exception as e:
            logger.error(f"Error deleting chunks from Pinecone namespace {project_id}: {e}")


class PGVectorStore(BaseVectorStore):
    """PostgreSQL pgvector vector store implementation.
    
    Encapsulates all PostgreSQL pgvector storage logic inside this adapter class.
    Does not require altering standard relational SQL models across the application.
    """
    def __init__(self):
        self._initialized = False
        self.db_url = settings.PGVECTOR_DATABASE_URL or settings.DATABASE_URL
        if "postgresql" not in self.db_url:
            logger.warning("PGVECTOR requires a PostgreSQL connection string. Falling back to MockInMemoryVectorStore.")
            self._mock_store = MockInMemoryVectorStore()
            return
        
        try:
            from sqlalchemy import create_engine, text
            self.engine = create_engine(self.db_url)
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pgvector_embeddings (
                        id VARCHAR(36) PRIMARY KEY,
                        project_id VARCHAR(255) NOT NULL,
                        document_id VARCHAR(255),
                        content TEXT NOT NULL,
                        embedding vector(1536),
                        metadata_json JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_pgvector_proj ON pgvector_embeddings(project_id);
                """))
                conn.commit()
            self._initialized = True
        except Exception as e:
            logger.warning(f"Could not initialize PGVectorStore ({e}). Falling back to MockInMemoryVectorStore.")
            self._mock_store = MockInMemoryVectorStore()

    def upsert_chunks(self, project_id: str, chunks: List[Dict[str, Any]]) -> List[str]:
        if not self._initialized:
            return self._mock_store.upsert_chunks(project_id, chunks)

        import json
        from sqlalchemy import text
        texts = [c["content"] for c in chunks]
        embeddings = embedding_service.get_embeddings(texts)
        vector_ids = []

        with self.engine.connect() as conn:
            for idx, chunk in enumerate(chunks):
                v_id = str(uuid.uuid4())
                vector_ids.append(v_id)
                doc_id = chunk.get("metadata", {}).get("document_id")
                emb_str = f"[{','.join(str(x) for x in embeddings[idx])}]"
                meta_json = json.dumps(chunk.get("metadata", {}))

                conn.execute(
                    text("""
                        INSERT INTO pgvector_embeddings (id, project_id, document_id, content, embedding, metadata_json)
                        VALUES (:id, :project_id, :document_id, :content, :embedding::vector, :metadata_json::jsonb)
                    """),
                    {
                        "id": v_id,
                        "project_id": project_id,
                        "document_id": doc_id,
                        "content": chunk["content"],
                        "embedding": emb_str,
                        "metadata_json": meta_json
                    }
                )
            conn.commit()
        return vector_ids

    def similarity_search(
        self,
        project_id: str,
        query: str,
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if not self._initialized:
            return self._mock_store.similarity_search(project_id, query, top_k, filter_dict)

        import json
        from sqlalchemy import text
        query_vec = embedding_service.get_embedding(query)
        emb_str = f"[{','.join(str(x) for x in query_vec)}]"

        with self.engine.connect() as conn:
            stmt = text("""
                SELECT id, content, metadata_json, 1 - (embedding <=> :query_vec::vector) AS score
                FROM pgvector_embeddings
                WHERE project_id = :project_id
                ORDER BY embedding <=> :query_vec::vector ASC
                LIMIT :top_k
            """)
            rows = conn.execute(stmt, {
                "query_vec": emb_str,
                "project_id": project_id,
                "top_k": top_k
            }).fetchall()

        results = []
        for r in rows:
            meta = r.metadata_json if isinstance(r.metadata_json, dict) else json.loads(r.metadata_json or "{}")
            results.append({
                "content": r.content,
                "metadata": meta,
                "score": float(r.score) if r.score is not None else 0.0,
                "vector_id": r.id
            })
        return results

    def delete_document_chunks(self, project_id: str, document_id: str) -> None:
        if not self._initialized:
            self._mock_store.delete_document_chunks(project_id, document_id)
            return

        from sqlalchemy import text
        with self.engine.connect() as conn:
            conn.execute(
                text("DELETE FROM pgvector_embeddings WHERE project_id = :project_id AND document_id = :document_id"),
                {"project_id": project_id, "document_id": document_id}
            )
            conn.commit()
def get_vector_store() -> BaseVectorStore:
    """Factory function to instantiate vector store based on VECTOR_DB_TYPE config setting."""
    db_type = settings.VECTOR_DB_TYPE.lower() if settings.VECTOR_DB_TYPE else "pinecone"
    
    if db_type == "pinecone":
        logger.info("Initializing Pinecone Vector Store adapter.")
        return PineconeVectorStore()
    elif db_type == "pgvector":
        logger.info("Initializing PGVector Store adapter.")
        return PGVectorStore()
    elif db_type == "mock":
        logger.info("Initializing Mock In-Memory Vector Store adapter.")
        return MockInMemoryVectorStore()
    else:
        logger.warning(f"Unknown VECTOR_DB_TYPE '{db_type}'. Defaulting to PineconeVectorStore.")
        return PineconeVectorStore()


# Singleton vector store instance for the application
vector_store = get_vector_store()
