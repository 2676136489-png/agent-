"""Document parsing: PDF / Markdown / TXT → 纯文本（尽量保留页码）。

[P0] 解析的目标不是「把文字抠出来」就完了，而是**保留位置信息**：
PDF 要记页码，文本要记字符区间。否则后面无法生成可追溯的 Citation。
"""

from __future__ import annotations

import io

from pydantic import BaseModel

SUPPORTED_TYPES = {
    "application/pdf": ".pdf",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "text/x-markdown": ".md",
}


class ParsedDocument(BaseModel):
    """解析结果。pages 为 None 表示纯文本（没有页码概念）。"""

    pages: list[str] | None
    text: str
    page_count: int | None = None


def _detect_type(filename: str, content_type: str | None) -> str:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith(".md") or lowered.endswith(".markdown"):
        return "text/markdown"
    if lowered.endswith(".txt"):
        return "text/plain"
    return content_type or "text/plain"


def parse_bytes(
    data: bytes,
    filename: str,
    content_type: str | None = None,
) -> tuple[ParsedDocument, str]:
    """返回（解析结果, 标准化的 mime_type）。"""
    mime_type = _detect_type(filename, content_type)

    if mime_type == "application/pdf":
        return _parse_pdf(data), mime_type

    # utf-8-sig：Windows 下的文本编辑器经常写出带 BOM 的文件，
    # 用 utf-8 解码会把 BOM 变成一个乱码字符混进正文，影响检索质量
    text = data.decode("utf-8-sig", errors="ignore")
    return ParsedDocument(pages=None, text=text, page_count=None), mime_type


def _parse_pdf(data: bytes) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return ParsedDocument(pages=pages, text="\n\n".join(pages), page_count=len(pages))
