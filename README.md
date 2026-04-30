# DevFlow Engine

> AI 驱动的研发流程引擎 Demo：把一个自然语言需求，推进成可审查、可回退、可交付的研发流水线。

![Status](https://img.shields.io/badge/status-MVP%20Demo-1664ff)
![Agent](https://img.shields.io/badge/agent-Mock%20Agent-00b2ff)
![Runtime](https://img.shields.io/badge/runtime-Static%20Web-green)
![Test](https://img.shields.io/badge/test-Node.js-orange)

![DevFlow Engine 控制台界面](docs/assets/devflow-console.png)

## 项目简介

DevFlow Engine 是一个面向“AI Native 研发流程”的实验性 Demo。它不把 AI 当成单点代码生成工具，而是把多个 Agent 编排进一条研发 Pipeline 中，让系统从需求输入开始，依次完成需求分析、方案设计、代码生成、测试生成、代码评审和交付总结。

当前版本是 **Mock Agent MVP**：Agent 暂时不调用真实大模型，而是使用模板化输出，优先验证完整流程是否成立。

核心演示目标是：

- 一个需求可以被拆成多个研发阶段。
- 每个阶段由明确职责的 Agent 产出结果。
- 人可以在关键节点 Approve 或 Reject。
- Reject 后，流程会带着原因回退并重新生成。
- 最终形成交付总结和 MR 描述草稿。

## Demo 场景

默认演示需求：

> 给任务管理系统增加按优先级筛选任务的功能。

系统会围绕这个需求跑完以下流程：

```text
需求分析
  ↓
方案设计
  ↓
人工审批（Approve / Reject）
  ↓
代码生成
  ↓
测试生成
  ↓
代码评审
  ↓
人工审批（Approve / Reject）
  ↓
交付总结
```

## 功能亮点

### 1. Pipeline 流程编排

`pipeline-core.js` 负责管理流程状态，包括当前阶段、阶段产物、审批记录和流程完成状态。

### 2. 6 个 Mock Agent

当前版本包含 6 个角色：

| 阶段 | Agent | 产物 |
|---|---|---|
| 需求分析 | 需求分析 Agent | 用户故事、功能范围、验收标准 |
| 方案设计 | 方案设计 Agent | 技术方案、涉及模块、风险点 |
| 代码生成 | 代码生成 Agent | 修改文件列表、diff 摘要 |
| 测试生成 | 测试生成 Agent | 测试用例、模拟测试结果 |
| 代码评审 | 代码评审 Agent | 评审结论、风险列表 |
| 交付总结 | 交付总结 Agent | 变更摘要、测试摘要、MR 描述草稿 |

### 3. Human-in-the-loop

在方案设计和代码评审阶段，Pipeline 会暂停等待人工决策：

- `Approve`：继续进入下一阶段
- `Reject`：要求填写原因，并回到当前阶段重新生成

例如在方案设计阶段填写：

```text
缺少空状态处理
```

系统会重新生成一版包含该问题修正说明的技术方案。

### 4. 演示向导 UI

前端采用偏字节系工具台风格：白底、蓝色主操作、高密度信息布局、底部固定操作条。页面会显示“下一步该做什么”，避免演示时来回滚动和猜按钮。

## 如何运行

这是一个静态 Web Demo，不需要安装前端依赖。

直接用浏览器打开：

```text
index.html
```

如果希望通过本地服务访问，可以在项目目录运行：

```bash
python -m http.server 5500
```

然后访问：

```text
http://127.0.0.1:5500/index.html
```

## 演示步骤

1. 打开 `index.html`
2. 确认默认需求，点击 `创建 Pipeline`
3. 按页面“下一步”提示，点击 `执行：需求分析`
4. 继续执行到 `方案设计`
5. 在方案审批点，先填写 Reject 原因并点击 `Reject`
6. 重新执行 `方案设计`，观察产物中包含驳回原因
7. 点击 `Approve`
8. 继续执行代码生成、测试生成、代码评审
9. 最终审批通过后，生成交付总结

也可以点击 `自动演示到下个决策点`，快速跑到需要人工判断的位置。

## 项目结构

```text
.
├── index.html                         # DevFlow 控制台页面
├── styles.css                         # 控制台样式
├── script.js                          # 页面交互和状态渲染
├── pipeline-core.js                   # Pipeline 状态机与 Mock Agent
├── tests/
│   └── pipeline-core.test.js          # Pipeline 核心逻辑测试
└── docs/
    ├── MVP定义.md
    ├── 需求要点-阶段拆解-Must-have清单.md
    └── 阶段输入输出与Agent设计.md
```

## 验证命令

项目使用 Node.js 原生能力测试核心逻辑。

```bash
node tests/pipeline-core.test.js
node --check pipeline-core.js
node --check script.js
```

预期结果：

```text
pipeline-core tests passed
```

并且两个 `node --check` 命令无报错。

## 当前限制

当前版本主要验证流程闭环，因此暂未实现：

- 真实大模型调用
- 真实代码库修改
- Git 分支创建和 MR / PR 提交
- 后端 REST API 服务
- 多模型 Provider 切换
- 代码库语义索引

这些能力会作为后续增强方向。

## 后续计划

- 接入真实 LLM，把部分 Mock Agent 替换成模型调用。
- 补充后端 API：Pipeline 创建、启动、状态查询、审批提交、产物查询。
- 增加 OpenAPI / Swagger 文档。
- 增加真实目标项目，让代码生成阶段产出可应用的 diff。
- 增加运行日志、耗时、Token 消耗等可观测指标。

## 设计取舍

第一版没有直接接入真实 AI，是有意为之。当前阶段最重要的是先证明流程本身成立：Agent 分工、Pipeline 流转、人工审批、Reject 回退和最终交付都能稳定演示。等这条链路跑通后，再接真实模型会更稳，也更容易控制输出格式。
