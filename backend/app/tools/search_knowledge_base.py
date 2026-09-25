"""search_knowledge_base tool.

Agent 可以自己决定什么时候查知识库 —— 我们不做硬编码路由。
工具描述写得越清楚，模型判断得越准（这是 Tool Calling 调优的第一杠杆）。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.rag import service as rag_service
from app.rag.schemas import Citation
from app.tools.base import BaseTool, ToolContext


class SearchKnowledgeBaseArgs(BaseModel):
    query: str = Field(min_length=2, max_length=300, description="检索意图，用自然语言描述")
    top_k: int = Field(default=5, ge=1, le=10, description="返回几条")


class SearchKnowledgeBaseTool(BaseTool):
    name = "search_knowledge_base"
    description = (
        "在用户上传的知识库（PDF / Markdown / TXT）中做语义检索，"
        "返回最相关的原文片段及其 document_id、chunk_id、页码。"
        "当用户的问题可能已经包含在他上传的资料里时，优先使用本工具；"
        "找不到相关内容时再考虑 search_web。"
    )
    args_schema = SearchKnowledgeBaseArgs
    timeout_seconds = 20.0

    async def _run(self, args: BaseModel, ctx: ToolContext) -> str:
        assert isinstance(args, SearchKnowledgeBaseArgs)
        # 通过模块属性查找而不是直接持有函数引用，测试里才能替换成临时实例
        service = rag_service.get_knowledge_service()
        hits = await service.search(args.query, args.top_k)

        if not hits:
            return "知识库中没有找到相关内容（也可能是知识库为空）。可以改用 search_web。"

        # [P0] 引用单独结构化保存，不混在给模型看的文本里：
        # 文本负责让模型理解，citations 负责让最终答案可追溯。
        ctx.artifacts["citations"] = [
            Citation(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                filename=hit.filename,
                page=hit.page,
                quote=hit.content[:300],
                score=hit.score,
            ).model_dump()
            for hit in hits
        ]

        payload = [
            {
                "document_id": hit.document_id,
                "chunk_id": hit.chunk_id,
                "filename": hit.filename,
                "page": hit.page,
                "score": hit.score,
                "content": hit.content,
            }
            for hit in hits
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)
