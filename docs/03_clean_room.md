# 03：交付文本清洗的边界

`sanitize_deliverable()` 是一个小型文本辅助函数：移除 BossAlign 专用 HTML 注释、`[RULE-...]` / `[EVT-...]` 标签和部分明确标记的内部反馈括注，再规范多余空行。

它不是通用隐私扫描器，不会可靠识别任意个人信息、机密、提示词或业务数据，也不会自动改写标记移除后产生的语句。不要把它当作安全审查或文档导出系统。

```python
from bossalign.sanitizer import sanitize_deliverable

cleaned = sanitize_deliverable("正文 [RULE-abc]\n\n<!-- bossalign: internal -->")
```

若输出用于外部交付，应用仍需按自身数据规范审阅结果。规则来源与审核记录应保存在独立 SQLite 记忆中，不需要附加到最终文本。
