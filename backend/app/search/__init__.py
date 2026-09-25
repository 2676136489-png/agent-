"""搜索配额域。

配额是「搜索」这条线的领域概念（不是工具的通用设施），所以单独成包：
- `quota.py`：SQLite 记账与额度决策（预扣 / 结算 / 退款 / 跨月 rollover）
- `errors.py`：额度相关的异常，由 provider 抛出、工具层翻译成 error_kind
"""
