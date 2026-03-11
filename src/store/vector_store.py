"""
Vector store (Chroma) for semantic search over modules.
Each module is stored as a document (path + function/class names) and optional purpose text.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from src.store.sqlite_store import get_data_dir

if TYPE_CHECKING:
    from src.models.module import ModuleNode

_CHROMA_CLIENT: Any = None
_CHROMA_COLLECTION: Any = None


def _chroma_persist_dir(repo_root: Optional[Path] = None) -> Path:
    return get_data_dir(repo_root) / "chroma"


def init_vector_store(persist_dir: Optional[Path] = None, repo_root: Optional[Path] = None) -> bool:
    """
    Initialize Chroma persistent client and create/get 'modules' collection.
    Returns True if Chroma is available and init succeeded, False otherwise (graceful degradation).
    """
    global _CHROMA_CLIENT, _CHROMA_COLLECTION
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    except ImportError:
        return False
    path = persist_dir or _chroma_persist_dir(repo_root)
    path.mkdir(parents=True, exist_ok=True)
    try:
        _CHROMA_CLIENT = chromadb.PersistentClient(path=str(path))
        ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        _CHROMA_COLLECTION = _CHROMA_CLIENT.get_or_create_collection(
            name="modules",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        return True
    except Exception:
        return False


def _module_document(m: "ModuleNode") -> str:
    """Build searchable text for a module (full ModuleNode schema: path, language, purpose, domain, etc.)."""
    parts = [m.path, m.language]
    for f in m.public_functions:
        parts.append(f.name)
    for c in m.classes:
        parts.append(c.name)
        parts.extend(c.bases)
    if getattr(m, "purpose_statement", None) and m.purpose_statement:
        parts.append(str(m.purpose_statement))
    if getattr(m, "domain_cluster", None) and m.domain_cluster:
        parts.append(str(m.domain_cluster))
    if getattr(m, "last_modified", None) and m.last_modified:
        parts.append(str(m.last_modified))
    return " ".join(parts)


def add_modules_to_vector_store(
    analysis_id: int,
    repo_id: str,
    modules: list["ModuleNode"],
    persist_dir: Optional[Path] = None,
) -> bool:
    """
    Add module documents to Chroma. IDs are analysis_id:path to support multiple runs.
    Returns True if added, False if Chroma not available.
    """
    global _CHROMA_COLLECTION
    if _CHROMA_COLLECTION is None:
        if not init_vector_store(persist_dir):
            return False
    assert _CHROMA_COLLECTION is not None
    if not modules:
        return True
    ids = [f"{analysis_id}:{m.path}" for m in modules]
    documents = [_module_document(m) for m in modules]
    metadatas = []
    for m in modules:
        meta: dict[str, Any] = {
            "analysis_id": analysis_id,
            "repo_id": repo_id,
            "path": m.path,
            "language": m.language,
        }
        if getattr(m, "purpose_statement", None) and m.purpose_statement:
            meta["purpose_statement"] = str(m.purpose_statement)[:500]
        if getattr(m, "domain_cluster", None) and m.domain_cluster:
            meta["domain_cluster"] = str(m.domain_cluster)
        if getattr(m, "complexity_score", None) is not None:
            meta["complexity_score"] = float(m.complexity_score)
        if getattr(m, "change_velocity_30d", None) is not None:
            meta["change_velocity_30d"] = float(m.change_velocity_30d)
        if getattr(m, "is_dead_code_candidate", None) is not None:
            meta["is_dead_code_candidate"] = bool(m.is_dead_code_candidate)
        if getattr(m, "last_modified", None) and m.last_modified:
            meta["last_modified"] = str(m.last_modified)
        metadatas.append(meta)
    _CHROMA_COLLECTION.add(ids=ids, documents=documents, metadatas=metadatas)
    return True


def search_modules(
    query: str,
    n_results: int = 10,
    repo_id: Optional[str] = None,
    persist_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Semantic search over stored modules. Optional filter by repo_id (metadata).
    Returns list of dicts with id, path, analysis_id, repo_id, distance.
    """
    global _CHROMA_COLLECTION
    if _CHROMA_COLLECTION is None:
        if not init_vector_store(persist_dir):
            return []
    assert _CHROMA_COLLECTION is not None
    where = {"repo_id": repo_id} if repo_id else None
    result = _CHROMA_COLLECTION.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["metadatas", "distances"],
    )
    out: list[dict] = []
    if result["ids"] and result["ids"][0]:
        for i, id_ in enumerate(result["ids"][0]):
            meta = (result["metadatas"][0][i]) if result["metadatas"] and result["metadatas"][0] else {}
            dist = (result["distances"][0][i]) if result.get("distances") and result["distances"][0] else None
            out.append({
                "id": id_,
                "path": meta.get("path", ""),
                "analysis_id": meta.get("analysis_id"),
                "repo_id": meta.get("repo_id"),
                "distance": dist,
            })
    return out
