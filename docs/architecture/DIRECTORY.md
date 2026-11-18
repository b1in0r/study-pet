# 开发目录与模块边界

## 目标目录

下列是逐步到达的结构。当前已建立 storage 的连接/迁移入口及 knowledge 的资料库/提取模块；其余按实际开发建立，避免出现大量空模块。

```text
study-pet/
├─ AGENTS.md                      # 仓库开发导航与约定，不放个人档案
├─ README.md
├─ studypet/
│  ├─ __main__.py                 # 保留 CLI 入口
│  ├─ web.py                      # 保留网页启动入口，逐步只做 HTTP 适配
│  ├─ tasks.py                    # 保留 TaskStore 兼容接口
│  ├─ agent.py                    # 保留 AgentStore / ReminderEngine 兼容接口
│  ├─ assistant/                  # 待建：模型调用与工具执行循环
│  │  ├─ runtime.py
│  │  ├─ tools.py                 # 工具 schema、白名单与结果结构
│  │  └─ prompts/                # 有版本号的通用指令模板
│  ├─ services/                   # 待建：用例、事务与业务规则
│  │  ├─ profile.py               # 事实确认、纠正、过期和替代
│  │  ├─ conversation.py          # 对话消息和流式回复生命周期
│  │  ├─ planning.py              # 计划草稿→确认→任务
│  │  └─ review.py                # 日/周复盘
│  ├─ context/                    # 待建：送进模型之前的上下文管理
│  │  ├─ builder.py               # 单一装配入口
│  │  ├─ retrieval.py             # 过滤、检索、排序、去重
│  │  ├─ budget.py                # token 预算和裁剪
│  │  └─ summaries.py             # 带覆盖范围与版本的摘要
│  ├─ memory/                     # 待建：记忆提取与维护
│  │  ├─ extraction.py            # 从已完成对话生成候选事实
│  │  └─ consolidation.py         # 合并候选、检测冲突，不越过确认规则
│  ├─ storage/                    # 已建：唯一连接工厂和版本迁移
│  │  ├─ database.py
│  │  ├─ migrate.py
│  │  ├─ migrations/              # 已启用 0002_document_library.sql
│  │  └─ repositories/            # 待建：SQL 封装，不调用模型、不弹窗
│  ├─ knowledge/                  # 已建：用户选择导入的资料
│  │  ├─ library.py               # 原件、版本、分块与检索；后续按需要拆分
│  │  ├─ extract.py               # PDF、DOCX、文本与图片提取
│  │  ├─ worker.py                # 独立解析进程
│  │  └─ ocr.py                   # Windows 本地 OCR
│  ├─ models/                     # 待建：供应商适配、流式输出、token 计量
│  │  ├─ base.py
│  │  └─ providers.py
│  ├─ web_static/                 # 现有前端，先保持原生 HTML/CSS/JS
│  ├─ notifications.py            # 现有 Windows 通知
│  ├─ display.py                  # 现有屏幕桥接入口
│  ├─ screen_render.py
│  ├─ screen_protocol.py
│  └─ codex_status.py             # 现有 Codex 用量/完成回复读取
├─ firmware/                     # 现有硬件固件
├─ tools/                        # 开发/运维辅助脚本，不放业务规则
├─ tests/                        # 存储、业务、上下文和接口的行为检查
├─ evals/                        # 待建：虚构用户的记忆与规划评测案例
├─ examples/                     # 待建：空配置和虚构样例
├─ docs/
│  ├─ architecture/              # 本规划
│  └─ ...                        # 现有运行、硬件与开发文档
└─ .local/                       # 已忽略，全部私有
   ├─ studypet.sqlite3           # 保持当前主库路径
   ├─ attachments/              # 待建：按文档 ID/版本保存导入文件
   ├─ derived/                  # 待建：可重建提取文本/检索索引
   ├─ exports/                  # 待建：用户主动导出的资料与档案
   ├─ backups/                  # 待建：主库＋附件清单的备份集
   ├─ config/                   # 待建：本机模型/上下文设置，不存明文密钥
   ├─ logs/                     # 待建：不包含聊天正文的技术日志
   └─ ...                       # 保留现有字体、桥接、预览与固件备份
```

## 调用边界

| 模块 | 负责 | 依赖边界 |
| --- | --- | --- |
| 网页/CLI | 参数解析、输入校验、展示 | 调用 services，不直接拼模型上下文 |
| services | 业务规则、版本检查、确认、事务 | 调用 repositories 和任务服务 |
| assistant | 一轮交互的状态、工具循环、失败处理 | 通过 context 和 models 工作，不自行执行 SQL |
| context | 读取相关资料、预算、来源清单 | 只读业务记录，派生摘要通过专门服务保存 |
| memory | 候选事实提取与冲突建议 | 无权直接覆盖已确认画像 |
| models | 通用消息到供应商协议的转换 | 不读取整个硬盘、不决定任务是否完成 |
| storage | 连接、迁移、查询与事务 | 不依赖 UI、硬件或具体模型 |
| knowledge | 文件导入、版本、分块和索引 | 通过 storage 保存元数据，使用托管附件目录 |
| 屏幕/通知 | 展示和提醒 | 不持有模型密钥，不维护第二份任务库 |

应用服务持有一次业务动作的事务；需要多个 repository 时传同一连接。模型网络请求与用户等待均发生在数据库事务之外。

`assistant/` 与现有 `agent.py` 使用不同名称；避免同时出现 `agent.py` 和 `agent/` 导致导入路径冲突。

## 现有代码的拆分顺序

1. 引入连接工厂与正式迁移入口，先保留 `TaskStore`、`AgentStore` 的公开接口。
2. 让现有两个 Store 也使用连接工厂，再新增 repository；消除外部对 `TaskStore._connect()` 的依赖。
3. 新功能走 services；网页现有接口和 CLI 命令保持兼容。
4. 对话闭环稳定后，再按必要性拆 HTTP 路由和静态前端。
5. 硬件模块保持当前路径，直到实际出现整合需要。

## 开发上下文与个人上下文

`AGENTS.md`、本目录设计和评测样例供开发者/Codex 理解工程。运行时个人画像由数据库生成，经 Context Builder 选择后给个人助理使用。

个人资料不写入仓库 `AGENTS.md` 或提示词模板。导出的 `USER.md` 若提供，也放在 `.local/exports/`，带生成时间与版本；默认只读导出，不作为第二个可写真相来源。
