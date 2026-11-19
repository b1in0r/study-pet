# 数据存储设计

当前正式版本为 v5。用户确认的日记存入 journal_entries，按用户选定日期排序。档案由 profile_entries 保存，可关联资料，编辑时校验 revision。本目录 SQL 是早期参考草案，运行数据库以正式迁移为准。

## 1. 文件、数据库与配置

主库继续使用 `.local/studypet.sqlite3`，个人附件放 `.local/attachments/<document_id>/<revision>/original.<ext>`，提取缓存放 `.local/derived/`。数据库保存相对路径和 SHA-256；文件名和扩展名由导入器规范化，不直接拼接用户上传的路径。仓库当前 `.local/` 忽略规则覆盖这些文件。

SQL 表保存可以查询、关联、确认和更新的记录；附件保存原始文档。大文件、录音、embedding 向量不直接塞进聊天 JSON。第一阶段不存录音、不新增麦克风功能。

通用提示词在源码里版本管理；本机设置使用 `.local/config/assistant.toml`（待实现），只保存 provider、model、预算与密钥环境变量名称。密钥来自进程环境或系统凭据，不能进入数据库、上下文清单或日志。

## 2. 现有 5 张表的定位

| 表 | 权威内容 | 演进方式 |
| --- | --- | --- |
| tasks | 当前计划、时间、完成状态、修订号 | 继续复用，后续以关联表连接长期目标 |
| task_events | 创建、修改、完成、移除及提醒处理历史 | 保留既有语义，不将它扩成所有聊天的总日志 |
| reminders | 一次计划时间点的提醒与发送状态 | 沿用调度和去重，模型不负责计时 |
| memories | 用户手动记忆本 | 原样保留，作为原始材料；后续提供编辑、版本及来源失效处理 |
| agent_settings | 提醒开关 | 只管提醒，不混入模型密钥和完整个人画像 |

手动笔记写“目标”，不等于已经建立了结构化目标或已经落实计划。模型可以从它提取候选，但不能把用户探索性想法直接当承诺。

## 3. 拟新增的 12 张表

[proposed_v2.sql](proposed_v2.sql) 给出字段、外键与关键唯一约束。这是完整目标结构；首轮运行能力可以只启用其中的对话与档案部分。

| 表 | 用途与关键字段 |
| --- | --- |
| conversations | 应用自己的对话主题和生命周期，`id/topic/created_at/deleted_at` |
| messages | 按 `conversation_id + seq` 排序的消息，`role/content_json/status/revision/run_id` |
| documents | 显式导入文件的元数据、托管路径、哈希、修订和导入状态 |
| sources | 统一来源登记：记录类型、记录 ID、版本、定位、处理范围和可用状态 |
| memory_claims | 结构化个人事实/偏好/阶段，包含键、值、候选状态、来源、有效期和替代关系 |
| document_chunks | 按文档版本分块的正文、页码/标题定位和哈希，可重建 |
| agent_runs | 一轮用户请求的模型运行，记录模型、提示词版本、上下文策略和状态 |
| context_items | 每次模型调用选用的记录 ID/版本、来源、顺序、选取理由及 token 估算 |
| conversation_summaries | 会话摘要及覆盖的消息范围、依赖版本、有效状态 |
| plan_proposals | 尚未或已经确认的动作草稿、基础修订、过期时间和执行结果 |
| tool_calls | 工具名、参数、状态、关联草稿、供应商调用 ID 和幂等键 |
| usage_records | 每次调用的实际/估算 token 和可用费用；未知用 NULL |

`messages.content_json` 使用应用自己的结构，如 `[{"type":"text","text":"虚构样例"}]`。工具调用与返回使用明确的结构块，保留调用 ID；不把供应商专有响应对象当长期协议。JSON 结构和长度由应用校验，DDL 不要求额外 JSON 扩展。

不保存模型隐藏推理。聊天保存用户可见内容和必要工具交互；技术日志默认只含运行 ID、耗时和错误代码。不得把密钥或完整请求头写入 `tool_calls`。

`context_items` 默认不复制正文，只保存引用。它说明“当时使用了什么”，不是永久保存个人内容的另一套日志。来源更正或删除后，该清单可能无法完整复现当时请求，这是删除生效的预期结果。

## 4. 个人事实的形状与状态

下面均为虚构样例，不会导入真实库：

```json
{
  "scope": "career",
  "claim_key": "target_cities",
  "value_json": "[\"示例城市甲\",\"示例城市乙\"]",
  "status": "candidate",
  "evidence_kind": "user_statement",
  "source_id": "source-example-1",
  "valid_from": "2026-11-18T00:00:00.000000+00:00",
  "valid_until": null,
  "confirmed_at": null
}
```

- `scope`：profile / learning / career / income / general，限定检索领域。
- `claim_key`：稳定机器键，如 `education.graduation_month`、`stage.current`、`learning.weekly_hours`。城市列表等多值内容放同一 JSON 值，避免互相覆盖。
- `candidate`：模型提取或待澄清信息，不能混入“已知事实”。
- `active`：已确认且未被替代；查询时还需检查有效期、来源和处理范围。
- `superseded`：被新事实替代，供历史问题查证。
- `rejected/expired/deleted`：默认不进入上下文。

同一 `scope + claim_key` 最多一条 active。确认新值时，在一个事务中检查旧记录 revision、将旧值标为 superseded、插入/激活新值并关联 `supersedes_id`。先做旧值状态变更再激活新值，以满足唯一索引。

用户在档案表单明确保存或明确要求“记住”可直接视为确认；模型自行抽取先为 candidate。对“精通某技能”“长期转行”等推测应呈现依据供用户检查。`evidence_kind` 表示来源性质，不是能力评分，也不把模型自报置信度当准确率。

更早已被移除的记录以及未知的过去时间不补造。既有 memories 可以逐条登记来源并保持原样，不能批量变成已确认画像。

## 5. 来源、版本与引用

`sources` 的 `(kind, record_id, source_version)` 唯一，原始内容不在此表重复保存：

| kind | record_id / source_version | 定位 |
| --- | --- | --- |
| message | 消息 ID / revision | 会话 ID、seq |
| manual_memory | 手动记忆 ID / 版本或正文哈希 | 记忆本条目 |
| task | 任务 ID / revision | 计划日期 |
| task_event | 历史事件 ID / 固定版本 1 | 事件时间 |
| document | 文档 ID / revision | 页码、章节、字符范围 |
| external_web | 持久化抓取工具的 tool_calls ID / 内容哈希 | result_json 片段位置、URL、发布和抓取时间 |

这是受限的多类型来源表；`kind + record_id` 的目标存在性由 repository 注册表检查，不接受任意表名或模型给出的 SQL。数据库外键负责其它固定关系。读取时必须回查原记录是否存在、版本是否匹配、是否已移除；仅有来源行不代表内容仍有效。

文档正文更换会递增 revision、重建分块并使旧摘要失效。SHA-256 用于内容完整性和去重提示，不在不同隐私范围间自动共用附件。

来源默认 `local_only`，只有用户选择允许用于云端助手的内容才标为 `cloud_allowed`。派生事实、摘要和检索片段继承所有依赖来源中最严格的处理范围。一次请求能否使用它，由实际执行模型是否本地、当前用户选择和来源状态共同决定。

## 6. 时间、ID 与一致性

- 继续保留已有整数 ID。新增实体由应用生成 UUID 文本，不给当前表改主键。
- 所有可比较时间使用 UTC、固定微秒精度、显式 `+00:00`；界面按 Asia/Shanghai 展示。valid 时间表示事实生效时间，created 时间表示入库时间，published/captured 分别表示发布与采集时间。
- 每次连接先开启 `PRAGMA foreign_keys=ON` 和有限 busy timeout，再开始事务；连接不跨线程共享。
- `conversation_id + seq`、事实当前值、来源版本与动作幂等键由唯一约束保护。seq 在短事务内分配，不能在模型调用前用未锁定的 `MAX(seq)+1` 长时间占用。
- 同一会话最多一个 running run；新输入排队或由用户中止旧运行后开启下一轮。不同会话可并行；迟到响应归属原 run，不能覆盖新回复。跨会话共享档案的写入仍通过 revision 处理冲突。
- 任务修改、草稿应用和事实纠正使用 revision 检查；冲突返回可解释结果，重新加载后再操作。
- 数据库事务只包围本地写入，不跨模型请求、文件解析或用户确认。
- 首期保持当前 journal 模式；有并发瓶颈后再测试 WAL、SQLite 版本和备份恢复。WAL 仍需处理写入竞争，不能把它当作多个同时写事务的保证。

SQLite 外键需要逐连接启用，见[官方外键文档](https://www.sqlite.org/foreignkeys.html)；并发与 WAL 的边界见[官方 WAL 文档](https://www.sqlite.org/wal.html)。这些是连接工厂的实施约定，当前 Store 尚未改造。

## 7. 计划草稿与工具执行

初期模型只能查询计划、检索资料、提出记忆候选和提交计划草稿。工具参数通过类型/长度/日期校验，运行时不开放任意 SQL 或 shell。

草稿 `actions_json` 如新增任务、改期、完成；`base_versions_json` 保存涉及任务的 revision。确认时检查草稿版本、有效期和任务基础版本。在同一个事务里完成任务动作、写既有 task_events、将草稿标为 applied 并记录任务 ID。重复确认返回已保存结果，不重复新增任务。

`accepted` 只能表示用户已确认，不能解释为执行成功。进程中断的 run 标为 interrupted；本地已应用事务靠草稿结果恢复。外部工具将来接入时，用 `unknown` 表示执行结果未确认，禁止盲目重试有副作用的动作。

幂等键由应用针对一次逻辑动作生成并持久化，重试沿用原键；不以模型每次新生成的 tool-call ID 代替幂等身份。

`usage_records` 每个 run/call_no 一条，失败重试也分配独立调用号。cached_input_tokens 是输入 token 的子集，不能再次加到总输入；供应商不提供费用时保留未知，估算与实测分开。

## 8. 检索与长期扩展

个人画像和任务先走结构化查询。中文手动笔记和聊天先做有范围、有数量上限的关键词/子串检索；资料量增加后再引入 FTS5 或向量检索。

FTS5 是否可用、分词效果以及中文短查询必须在运行环境实测；不能把默认分词等同于完善的中文检索。索引只引用有效来源，可删除重建。详见[SQLite FTS5](https://www.sqlite.org/fts5.html)。

以下在需求明确后另加迁移，不挤入通用 JSON：`goals` 与 `goal_tasks`（长期目标和任务关联）、`skill_evidence`（能力证据与评估记录）、`decisions`（选择及复盘）、`job_applications`（求职阶段与截止时间）。初期目标和阶段可用确认事实承载，复杂目标树不提前搭建。

## 9. 删除、备份与迁移

“从清单移除计划”保持现有历史保留语义。新增“忘记这段信息”必须走另一条明确流程：撤下来源、标记关联事实失效、删除相关分块与摘要正文、清除检索索引、上下文缓存及工具结果中的相关副本。处理完成前，Context Builder 应依来源不可用而拒绝使用相关派生记录。已在旧聊天里出现的副本需在删除预览中列出，按用户选择一并处理；普通删除一条笔记不应宣称清除所有历史副本。

数据库备份不会随当前记录删除而自动修改；界面应展示备份保留范围。既有个人数据不加密，后续如加密需同时覆盖附件和备份。

备份采用 SQLite backup API 加附件清单；一致备份期间暂停导入/清理附件，清单记录路径、版本和哈希，包含备份主库引用的文件。不能仅复制一个正在写入的主库文件就宣称完成备份。参考[SQLite Backup API](https://www.sqlite.org/backup.html)。

正式迁移前备份并在副本验证：v1 历史保持一致、新约束有效、外键检查通过、失败事务回滚。之后才在服务维护窗口迁移真实库并更新 user_version。SQL 草案不更新版本号，不能直接拿它替代正式迁移器。
