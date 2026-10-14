# 01：范围与反例边界

反馈本身不等于全局偏好。“消费者文案不要堆技术参数”不能自动变成“所有技术内容都删参数”。BossAlign 把范围与排除条件作为规则的一部分，并在上下文不足时返回不确定。

## 结构化范围

规则可按 `project`、`task_type`、`topic`、`audience`、`objective`、`task_id` 和 `tags` 匹配。字符串按空白归一化并忽略大小写后做精确比较，不使用包含匹配或向量相似度。

```json
{
  "applicable_scope": {
    "project": "sample-product",
    "audience": "consumer"
  },
  "negative_boundaries": [
    {"task_type": "technical_report"}
  ]
}
```

`applicable_scope` 中的条件必须全部满足。`negative_boundaries` 中任意一个条件对象全部满足时，该规则被排除。如果判断反例需要的字段缺失，规则不会启用，结果会标记为不确定。

## 可解释结果

选择结果会区分启用、排除、不确定和冲突。审核报告可以显示命中的规则、匹配原因、排除原因和冲突规则。未结构化的旧式 `prohibited_topics` 不会再做模糊匹配，而会要求调用方补充结构化条件。

## 限制

范围判断验证的是字段匹配，不是对自然语言上下文的完整理解。需要语义分类时，应用可接入 Provider；Provider 的输出仍是待确认规则或模型审核建议。
