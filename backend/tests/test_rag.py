"""RAG pipeline tests: chunking → embedding → vector search → citation.

跑法：uv run pytest
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.rag.chunking import chunk_parsed_document, chunk_text
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.parsing import ParsedDocument, parse_bytes
from app.rag.schemas import Citation
from app.rag.service import KnowledgeService
from app.rag.store import KnowledgeStore
from app.rag.vector import VectorIndex
from app.tools.base import ToolContext
from app.tools.search_knowledge_base import SearchKnowledgeBaseTool

SAMPLE_MD = """# AI Agent 岗位技术要求

AI Agent 开发岗位通常要求候选人熟悉 Python 与 TypeScript。

## 核心技能
- LLM API 集成与 Prompt Engineering
- RAG：Embedding、向量检索、Rerank
- Agent 编排与工具调用

## 加分项
具备可观测性与评测经验者优先。
"""


# ---------- chunking ----------


def test_chunk_text_respects_size_and_overlap():
    text = "这是一段用于测试的文本。" * 100
    chunks = chunk_text(text, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    # 每个 chunk 都有原始位置，才能生成可追溯的引用
    assert chunks[0].char_start == 0
    assert all(chunk.char_end > chunk.char_start for chunk in chunks)


def test_chunk_pdf_like_pages_keep_page_number():
    parsed = ParsedDocument(pages=["第一页内容。" * 20, "第二页内容。" * 20], text="", page_count=2)
    chunks = chunk_parsed_document(parsed, chunk_size=120, overlap=20)
    assert len(chunks) >= 2
    assert chunks[0].page == 1
    assert chunks[-1].page == 2


def test_empty_text_produces_no_chunks():
    assert chunk_text("", 100, 20) == []


# ---------- parsing ----------


def test_parse_markdown():
    parsed, mime = parse_bytes(SAMPLE_MD.encode("utf-8"), "notes.md")
    assert mime == "text/markdown"
    assert "Prompt Engineering" in parsed.text
    # 纯文本没有页码概念
    assert parsed.page_count is None


# ---------- embedding ----------


async def test_hash_embedding_is_deterministic():
    provider = HashEmbeddingProvider(64)
    first = await provider.embed(["hello world"])
    second = await provider.embed(["hello world"])
    assert first[0] == second[0]
    assert len(first[0]) == 64


# ---------- vector search ----------


def test_vector_search_ranks_by_similarity():
    index = VectorIndex()
    # 三个正交方向的向量：检索 (1,0,0) 时第一个必须排第一
    index.rebuild(
        [("a", [1.0, 0.0, 0.0]), ("b", [0.0, 1.0, 0.0]), ("c", [0.9, 0.1, 0.0])],
        version=1,
    )
    hits = index.search([1.0, 0.0, 0.0], top_k=2)
    assert hits[0][0] == "a"
    assert hits[1][0] == "c"
    assert hits[0][1] > hits[1][1]


def test_empty_index_returns_nothing():
    assert VectorIndex().search([1.0, 0.0], 5) == []


# ---------- end-to-end ingest + search ----------


def _build_service(tmp_path: Path) -> KnowledgeService:
    settings = Settings(storage_dir=str(tmp_path / "files"))
    store = KnowledgeStore(tmp_path / "test.db")
    return KnowledgeService(store=store, provider=HashEmbeddingProvider(128), settings=settings)


async def test_ingest_and_search_returns_citable_chunks(tmp_path: Path):
    service = _build_service(tmp_path)
    document = await service.ingest(
        data=SAMPLE_MD.encode("utf-8"),
        filename="notes.md",
        content_type="text/markdown",
    )

    # 1) 文档状态与元信息
    assert document.status == "ready"
    assert document.chunk_count >= 1
    assert document.embedding_model == "local-hash-v1"

    # 2) chunk 必须带 document_id 与原始位置
    chunks = service.list_chunks(document.id)
    assert chunks[0].document_id == document.id
    assert chunks[0].char_start is not None

    # 3) 检索命中的是同一个文档，且带 score
    hits = await service.search("RAG 向量检索", top_k=3)
    assert hits
    assert hits[0].document_id == document.id
    assert hits[0].filename == "notes.md"
    assert hits[0].score > 0


async def test_search_empty_knowledge_base_returns_nothing(tmp_path: Path):
    service = _build_service(tmp_path)
    assert await service.search("anything", 3) == []


async def test_ingest_empty_file_marks_document_failed(tmp_path: Path):
    from app.core.errors import AppError

    service = _build_service(tmp_path)
    with pytest.raises(AppError):
        await service.ingest(data=b"   ", filename="blank.txt")

    documents = service.list_documents()
    assert documents[0].status == "failed"


# ---------- tool ----------


async def test_search_knowledge_base_tool_produces_citations(tmp_path: Path):
    """工具必须产出结构化 citations，否则最终答案无法溯源。"""
    import app.rag.service as rag_service

    service = _build_service(tmp_path)
    await service.ingest(
        data=SAMPLE_MD.encode("utf-8"),
        filename="notes.md",
    )
    # 让工具使用我们这个临时 service
    original = rag_service.get_knowledge_service
    rag_service.get_knowledge_service = lambda: service
    try:
        ctx = ToolContext(run_id="t")
        result = await SearchKnowledgeBaseTool().execute({"query": "RAG 向量检索"}, ctx)
    finally:
        rag_service.get_knowledge_service = original

    assert result.ok is True
    assert len(result.citations) >= 1
    citation = Citation.model_validate(result.citations[0])
    assert citation.document_id
    assert citation.chunk_id
    assert citation.quote
