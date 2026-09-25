"""Knowledge base service: ingest 与 retrieval 的完整管线。

ingest:  上传 → 解析 → 切块 → embedding → 存库 → 重建索引
retrieve: query → embedding → 余弦检索 → 带上 document/page 信息返回
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.rag.chunking import chunk_parsed_document, estimate_tokens
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.rag.parsing import parse_bytes
from app.rag.schemas import Document, DocumentChunk, RetrievedChunk, Source
from app.rag.store import KnowledgeStore, get_knowledge_store, new_id
from app.rag.vector import VectorIndex

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(
        self,
        store: KnowledgeStore,
        provider: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._store = store
        self._provider = provider
        self._settings = settings
        self._index = VectorIndex()
        self._version = 0

    # ---------- ingest ----------

    async def ingest(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str | None = None,
    ) -> Document:
        parsed, mime_type = parse_bytes(data, filename, content_type)

        source: Source = self._store.create_source(type="upload", name=filename)
        document = self._store.create_document(
            source_id=source.id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(data),
        )

        try:
            # 1) 保存原始文件（路径由 document_id 推导，不必再存一列）
            extension = Path(filename).suffix or ".bin"
            storage_path = Path(self._settings.storage_dir) / f"{document.id}{extension}"
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            storage_path.write_bytes(data)

            # 2) 切块（PDF 带页码，文本带字符区间）
            drafts = chunk_parsed_document(
                parsed,
                self._settings.chunk_size,
                self._settings.chunk_overlap,
            )
            if not drafts:
                raise ValueError("没有从文件中提取到任何文本")

            # 3) 建 chunk 对象
            created_at = datetime.now(UTC)
            chunks = [
                DocumentChunk(
                    id=new_id("chk"),
                    document_id=document.id,
                    chunk_index=index,
                    content=draft.content,
                    page=draft.page,
                    char_start=draft.char_start,
                    char_end=draft.char_end,
                    token_estimate=estimate_tokens(draft.content),
                    created_at=created_at,
                )
                for index, draft in enumerate(drafts)
            ]

            # 4) embedding（批量一次调用，省请求数）
            vectors = await self._provider.embed([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise ValueError("embedding 返回数量与 chunk 数量不一致")

            # 5) 落库 + 标记完成
            self._store.save_chunks(chunks, vectors)
            self._store.update_document(
                document.id,
                status="ready",
                page_count=parsed.page_count,
                chunk_count=len(chunks),
                embedding_model=self._provider.model_name,
            )
            self._version += 1

            logger.info(
                "document ingested: id=%s chunks=%s file=%s",
                document.id,
                len(chunks),
                filename,
            )
        except Exception as exc:
            #  ingestion 失败不能让请求崩：标记 failed 并把原因暴露给调用方
            logger.exception("document ingestion failed: %s", document.id)
            self._store.update_document(document.id, status="failed", error=str(exc))
            raise AppError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文档处理失败：{exc}",
                status_code=400,
            ) from exc

        return self._store.get_document(document.id) or document

    # ---------- retrieve ----------

    def _ensure_index(self) -> None:
        if self._index.is_stale(self._version):
            items = self._store.load_vectors(self._provider.model_name)
            self._index.rebuild(items, self._version)
            logger.info("vector index rebuilt: chunks=%s", self._index.size)

    async def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        self._ensure_index()
        if self._index.size == 0:
            return []

        limit = top_k or self._settings.retrieval_top_k
        query_vectors = await self._provider.embed([query])
        hits = self._index.search(query_vectors[0], limit)

        results: list[RetrievedChunk] = []
        for chunk_id, score in hits:
            chunk = self._store.get_chunk(chunk_id)
            if chunk is None:
                continue
            document = self._store.get_document(chunk.document_id)
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    filename=document.filename if document else "(unknown)",
                    content=chunk.content,
                    score=round(score, 4),
                    page=chunk.page,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    chunk_index=chunk.chunk_index,
                )
            )
        return results

    # ---------- read ----------

    def list_documents(self) -> list[Document]:
        return self._store.list_documents()

    def list_chunks(self, document_id: str) -> list[DocumentChunk]:
        return self._store.list_chunks(document_id)


_SERVICE: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = KnowledgeService(
            store=get_knowledge_store(),
            provider=get_embedding_provider(),
            settings=get_settings(),
        )
    return _SERVICE
