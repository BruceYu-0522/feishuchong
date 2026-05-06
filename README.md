# DevFlow Engine

> AI 驱动的研发流程引擎：输入任意自然语言需求，6 个 AI Agent 依次完成需求分析、方案设计、代码生成、测试生成、代码评审和交付总结。每个阶段产出后都进入 Approve/Reject 检查点。

![Status](https://img.shields.io/badge/status-AI--Driven-1664ff)
![Agent](https://img.shields.io/badge/agent-Skill--driven%20LLM-00b2ff)
![Runtime](https://img.shields.io/badge/runtime-FastAPI%20%2B%20Static%20Web-green)
![Test](https://img.shields.io/badge/test-pytest%20%2B%20Node.js-orange)

## 核心设计理念

- **AI 是主驾驶，不是副驾驶。** 每个研发阶段由专门的 AI Agent 执行，不是靠硬编码模板生成假数据。
- **Pipeline 是骨架，Agent 是肌肉。** Pipeline 引擎管理阶段流转、数据传递和审查点；Agent 负责实际产出。
- **Human-in-the-Loop。** 每一个研发环节产出后都停在检查点，由人类做 Approve/Reject 决策。
- **通用引擎，而非单一 Demo。** 输入任何需求（不只是"优先级筛选"），系统都能产出对应结果。

## 流程概览

```text
用户输入任意需求
      ↓
需求分析 Agent ─── 结构化需求文档（含验收标准）
      ↓
人工审批 ←── Approve / Reject（澄清问题、业务逻辑、验收标准）
      ↓
方案设计 Agent ─── 技术方案 + 动态方案蓝图
      ↓
人工审批 ←── Approve / Reject（带原因回退重做）
      ↓
代码生成 Agent ─── 读取项目文件 → AI 生成完整代码 → 写入运行副本
      ↓
人工审批 ←── Approve / Reject（代码变更范围与运行副本）
      ↓
测试生成 Agent ─── 读取变更代码 → AI 生成可运行测试
      ↓
人工审批 ←── Approve / Reject（测试覆盖与验证方式）
      ↓
代码评审 Agent ─── 多维度审查（正确性/安全性/规范性）
      ↓
人工审批 ←── Approve / Reject
      ↓
交付总结 Agent ─── 变更摘要 + 测试摘要 + MR 描述草稿
      ↓
人工审批 ←── Approve / Reject（最终交付包）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 LLM API

```bash
# Windows PowerShell
$env:DEVFLOW_LLM_ENABLED="true"
$env:DEVFLOW_LLM_BASE_URL="https://api.lingyaai.cn"
$env:DEVFLOW_LLM_API_KEY="你的API密钥"

# Linux / macOS
export DEVFLOW_LLM_ENABLED=true
export DEVFLOW_LLM_BASE_URL=https://api.lingyaai.cn
export DEVFLOW_LLM_API_KEY=你的API密钥
```

系统通过中转站 API 按阶段路由到不同模型：

| 阶段 | Agent | 模型 |
|---|---|---|
| 需求分析 | 需求分析 Agent | `deepseek-v4-flash` |
| 方案设计 | 方案设计 Agent | `gpt-5.4` |
| 代码生成 | 代码生成 Agent | `claude-sonnet-4-5-20250929` |
| 测试生成 | 测试生成 Agent | `deepseek-v4-pro` |
| 代码评审 | 代码评审 Agent | `claude-opus-4-5-20251101` |
| 交付总结 | 交付总结 Agent | `deepseek-v4-flash` |

### 3. 启动后端

```bash
uvicorn backend.main:app --reload
```

API 文档：http://127.0.0.1:8000/docs

### 4. 打开前端

```bash
python -m http.server 5500
```

访问 http://127.0.0.1:5500/index.html

### 5. 运行一个 Pipeline

1. 在输入框中输入任意功能需求（例如："给任务管理系统增加暗色模式"）
2. 点击"开始生成"
3. 在需求分析检查点查看结构化 PRD、澄清问题和需求原型，选择 Approve 或 Reject
4. 通过后等待方案设计完成，并在方案审批点查看产物（包括 AI 生成的方案蓝图）
5. 继续运行，代码生成、测试生成、代码评审和交付总结都会逐一停下等待确认
6. 通过交付总结检查点后，流程进入完成状态

### 6. 验证生成的代码

```bash
# 查看运行副本中的代码改动
ls devflow-runs/<pipeline-id>/target-app/

# 运行 AI 生成的测试
node devflow-runs/<pipeline-id>/target-app/tests/*.test.js
```

## 运行测试

```bash
pytest backend/tests/test_pipeline_api.py -q
node tests/pipeline-core.test.js
node --check pipeline-core.js
node --check script.js
```

## 项目结构

```text
.
├── index.html                         # DevFlow 控制台页面
├── styles.css                         # 控制台样式
├── script.js                          # 前端交互（API-only，无本地 mock）
├── pipeline-core.js                   # STAGES 定义 + API 客户端
├── target-app/                        # 被 DevFlow 修改的示例项目
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── requirements.txt                   # Python 后端依赖
├── backend/
│   ├── main.py                         # FastAPI 入口（6 个 API 端点）
│   ├── pipeline_engine.py              # Pipeline 状态机（纯 LLM 驱动）
│   ├── code_executor.py                # AI 代码生成与执行（无硬编码 fallback）
│   ├── llm_runner.py                   # Skill-driven LLM 调用与模型路由
│   ├── schemas.py                      # Pydantic 数据模型
│   ├── skills.py                       # Skill 元数据读取
│   ├── storage.py                      # 内存存储
│   └── tests/
│       └── test_pipeline_api.py        # 后端 API 测试（含 LLM mock）
├── skills/
│   ├── requirements-analysis.skill.md
│   ├── technical-design.skill.md
│   ├── code-change.skill.md
│   ├── test-design.skill.md
│   ├── code-review.skill.md
│   └── delivery-summary.skill.md
├── tests/
│   └── pipeline-core.test.js          # 前端核心逻辑测试
└── docs/
    ├── MVP定义.md
    └── 阶段输入输出与Agent设计.md
```

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/pipelines` | 创建 Pipeline |
| GET | `/pipelines/{id}` | 查询 Pipeline 状态 |
| POST | `/pipelines/{id}/run-next` | 执行下一个阶段 |
| POST | `/pipelines/{id}/run-until-review` | 自动运行到审查点 |
| POST | `/pipelines/{id}/review` | 提交审批决策 |
| GET | `/runs/{id}/target-app/{path}` | 预览生成的代码产物 |

## 与旧版的关键区别

旧版（已废弃）的问题：
- Agent 输出全部硬编码，无论输入什么需求都返回"优先级筛选"相关结果
- 前端有本地 mock 模式，完全绕过 AI
- 代码生成是写死的字符串替换

当前版本：
- **AI 是唯一执行路径。** 不配置 LLM 无法运行，不会悄悄降级到假数据。
- **通用引擎。** 输入任何需求，AI Agent 都会基于实际输入生成对应产物。
- **真实代码生成。** 代码 Agent 读取项目文件，通过 LLM 生成完整代码并写入磁盘。
- **动态方案蓝图。** 从 AI 输出的方案内容中动态提取结构，不再硬编码。
