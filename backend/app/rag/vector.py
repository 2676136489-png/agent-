"""Vector index: 内存余弦相似度检索。

[P0] Vector Search 怎么工作（就三步）：
1. 把 query 也变成向量（用同一个 embedding 模型）
2. 计算 query 向量与每个 chunk 向量的**余弦相似度**
3. 按相似度从高到低取 top_k

余弦相似度 = 两个向量夹角的余弦，范围 [-1, 1]。
1 = 方向完全一致（最相关），0 = 无关，-1 = 相反。
用它而不是欧氏距离，是因为它只看方向、不看长度，长文本不会因为"数值大"而被误判更相似。

适用规模：当前实现会把全部向量读进内存，几千到几万条没问题。
超过 10 万条或需要多实例共享时，换成 pgvector / 专用向量库，接口保持不变。
"""

from __future__ import annotations

import threading

import numpy as np


class VectorIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None
        self._version: int = -1

    @property
    def size(self) -> int:
        return len(self._ids)

    def rebuild(self, items: list[tuple[str, list[float]]], version: int) -> None:
        """重建索引。调用方在数据变化时递增 version。"""
        if not items:
            with self._lock:
                self._ids, self._matrix, self._version = [], None, version
            return

        ids = [item[0] for item in items]
        matrix = np.asarray([item[1] for item in items], dtype=np.float32)
        # 归一化后，余弦相似度就等于点积，检索更快
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.where(norms == 0, 1, norms)

        with self._lock:
            self._ids, self._matrix, self._version = ids, matrix, version

    def is_stale(self, version: int) -> bool:
        return self._version != version

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if self._matrix is None or not self._ids:
            return []

        query = np.asarray(query_vector, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        if norm == 0:
            return []
        query = query / norm

        with self._lock:
            if self._matrix is None:
                return []
            scores = self._matrix @ query
            matrix_size = len(self._ids)

        k = min(top_k, matrix_size)
        # argpartition 比全量排序快：只需要前 k 个，不需要整体有序
        top_indices = np.argpartition(-scores, k - 1)[:k]
        top_indices = top_indices[np.argsort(-scores[top_indices])]

        return [(self._ids[int(index)], float(scores[int(index)])) for index in top_indices]
