"""Chunking: 把长文本切成可检索的小块。

[P0] 为什么必须切块：
1. **上下文长度有限**：一本 300 页的 PDF 塞不进 prompt
2. **检索要精准**：整篇文档只有一个向量，任何 query 都会命中它，等于没检索
3. **引用要精确**：Citation 要指向「第几页的哪一段」，整篇文档没法指

为什么需要 overlap：
如果严格按 800 字切断，正好落在句子中间的话，这个 chunk 的语义就不完整，
而且跨边界的答案会两边都检索不到。重叠 120 字能让边界处的信息在两侧都出现。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.parsing import ParsedDocument


@dataclass
class ChunkDraft:
    content: str
    page: int | None
    char_start: int | None
    char_end: int | None


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文按 1 字 1 token，英文按 4 字符 1 token。"""
    chinese = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    others = len(text) - chinese
    return chinese + others // 4


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[ChunkDraft]:
    """按字符窗口切分纯文本（用于 Markdown / TXT）。"""
    if not text.strip():
        return []

    drafts: list[ChunkDraft] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        # 尽量在句号/换行处收尾，避免把句子切断
        if end < length:
            for pivot in range(end, start + chunk_size // 2, -1):
                if text[pivot - 1] in "。！？\n":
                    end = pivot
                    break
        content = text[start:end].strip()
        if content:
            drafts.append(
                ChunkDraft(content=content, page=None, char_start=start, char_end=end)
            )
        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return drafts


def chunk_parsed_document(
    parsed: ParsedDocument,
    chunk_size: int,
    overlap: int,
) -> list[ChunkDraft]:
    """PDF 按页切（保留页码），纯文本按窗口切。"""
    if parsed.pages is None:
        return chunk_text(parsed.text, chunk_size, overlap)

    drafts: list[ChunkDraft] = []
    offset = 0
    for page_index, page_text in enumerate(parsed.pages, start=1):
        if not page_text.strip():
            continue
        # 页内再按窗口切，保证长页不会整页成为一个巨大 chunk
        for draft in chunk_text(page_text, chunk_size, overlap):
            drafts.append(
                ChunkDraft(
                    content=draft.content,
                    page=page_index,
                    char_start=offset + (draft.char_start or 0),
                    char_end=offset + (draft.char_end or 0),
                )
            )
        offset += len(page_text) + 2  # +2 是拼接页时加的 \n\n

    return drafts
