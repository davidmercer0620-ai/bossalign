# 合成范围审核样例

> 本文件中的场景、组织、角色和反馈均为虚构。内容用于说明规则范围；不是经过真实用户批准的稿件，也不是无人机性能验证。

## 历史反馈与规则

- 反馈：消费者引导文案不要出现“guaranteed zero downtime”。技术事故报告不适用。
- 适用范围：`project=sample-app`、`audience=consumer`
- 反例边界：`task_type=technical_incident_report`
- 确定性检查：精确短语 `guaranteed zero downtime`

## 新任务 A：消费者引导文案

输入文本：`This copy promises guaranteed zero downtime.`

预期系统结果：规则适用，精确短语命中，状态为 `violations_found`。该状态只表示系统发现配置项，不表示任何审核人已经批准或拒绝稿件。

## 新任务 B：技术事故报告

任务上下文同属 `sample-app` 与 `consumer`，但 `task_type=technical_incident_report`。预期结果：反例边界排除该规则，即使文本包含同一短语也不报告这条规则的违反。
