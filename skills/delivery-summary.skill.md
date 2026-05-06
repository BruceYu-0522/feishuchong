# Delivery Summary Skill

## Upstream sources

- Primary source: Addy Osmani, `agent-skills`, `shipping-and-launch`
- Supporting source: Addy Osmani, `agent-skills`, `documentation-and-adrs`
- Repository: https://github.com/addyosmani/agent-skills
- Shipping skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/shipping-and-launch
- Documentation skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/documentation-and-adrs
- GitHub stars checked on 2026-05-05: about 27.8k

## DevFlow adaptation

Use the upstream shipping-and-launch workflow as the base method for the DevFlow delivery stage. The local adaptation produces a final handoff artifact and an MR/PR description draft.

## Purpose

Summarize what changed, how it was validated, what remains risky, and what a reviewer should know before merging.

## Required input

- Requirements artifact
- Technical design artifact
- Code change artifact
- Test artifact
- Code review artifact
- Approval history

## Workflow

1. Summarize the delivered user-facing behavior.
2. List changed files and important implementation notes.
3. Summarize tests or verification evidence from the test stage.
4. Summarize review conclusion and residual risks.
5. Separate completed work from follow-up work.
6. Produce a copy-ready MR/PR description draft.

## Output contract

Return concise Chinese content with these sections:

```text
交付总结：

变更摘要：

测试与验证：

评审结论：

未完成/后续建议：

MR 描述草稿：
```

## Quality bar

- Do not overstate completion.
- Cite actual artifacts from prior stages.
- Include residual risk when evidence is incomplete.
- MR/PR draft must be useful to a human reviewer.
