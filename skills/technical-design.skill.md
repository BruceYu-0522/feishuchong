# Technical Design Skill

## Upstream sources

- Primary source: Addy Osmani, `agent-skills`, `planning-and-task-breakdown`
- Supporting source: Addy Osmani, `agent-skills`, `spec-driven-development`
- Repository: https://github.com/addyosmani/agent-skills
- Planning skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/planning-and-task-breakdown
- Spec skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/spec-driven-development
- GitHub stars checked on 2026-05-05: about 27.8k

## DevFlow adaptation

Use the upstream planning and task-breakdown workflow as the base method for the DevFlow design stage. The local adaptation turns a requirement artifact into a small implementation plan that can be approved or rejected by a human reviewer.

## Purpose

Create a technical plan that explains the impact area, implementation path, risks, and validation strategy before code is generated.

## Required input

- Requirements-analysis artifact
- Target project files or project summary
- Review history and latest reject reason, if any

## Workflow

1. Map each acceptance criterion to a design decision.
2. Identify impacted files, modules, UI states, and data structures.
3. Break the work into small implementation steps.
4. Keep the plan minimal; avoid unnecessary architecture or platform changes.
5. Identify risk areas and validation checks.
6. If a reject reason exists, include a specific correction section.

## Output contract

Return concise Chinese content with these sections:

```text
方案摘要：

影响范围：

实现路径：
1.
2.
3.

数据/状态变化：

UI 或 API 变化：

风险与验证：

对 Reject 原因的处理：
```

## Quality bar

- Every implementation step must trace back to an acceptance criterion.
- The plan must be small enough for the next code stage to execute.
- Do not include unrelated refactors.
- Make human review easy by naming concrete files or modules when known.
