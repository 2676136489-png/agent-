"""RAG domain models: Source / Document / DocumentChunk.

[P0] 为什么要分三张表（缺一不可）：

- **Source**：知识从哪来。同一个来源（比如一份 PDF、一个网页）会产生一个 Document，
  但未来同一来源可能有多个版本/多个文档 —— 先留好这一层，避免后面改表。
- **Document**：一份被摄入的文件本体（文件名、类型、页数、状态）。
- **DocumentChunk**：真正被检索的最小单位。**RAG 检索的是 chunk，不是 document**，
  因为一份 50 页的 PDF 不可能整篇塞进 prompt。

它们的关系：Source 1─n Document 1─n DocumentChunk
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Source(BaseModel):
    id: str
    type: str = Field(description="upload | web")
    name: str
    url: str | None = None
    created_at: datetime


class Document(BaseModel):
    id: str
    source_id: str
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int | None = None
    chunk_count: int = 0
    status: str = Field(description="processing | ready | failed")
    error: str | None = None
    # 记录生成向量时用的模型：换 embedding 模型后旧 chunk 不再参与检索，
    # 避免维度不一致直接崩掉
    embedding_model: str | None = None
    created_at: datetime


class DocumentChunk(BaseModel):
    """[P0] 检索的最小单位，也是 Citation 的载体。"""

    id: str
    document_id: str
    chunk_index: int
    content: str
    # 页码（PDF）或字符区间（文本类）—— 定位「这句话在原文的哪里」
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    token_estimate: int = 0
    created_at: datetime


class RetrievedChunk(BaseModel):
    """一次检索的结果：chunk + 相似度 + 它所属文档的摘要信息。"""

    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float = Field(description="余弦相似度，越大越相关")
    page: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    chunk_index: int = 0


class Citation(BaseModel):
    """最终答案要引用的来源。

    [P0] 这是本项目「Evidence-first」的最小落地单位：
    每一条结论都要能回答「你凭什么这么说」—— 答案就是这里的 document_id + chunk_id + page。
    """

    chunk_id: str
    document_id: str
    filename: str
    page: int | None = None
    quote: str = Field(description="被引用的原文片段")
    score: float | None = None
