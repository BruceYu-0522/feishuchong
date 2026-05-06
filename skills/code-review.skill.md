# Code Review Skill

## Upstream sources

- Primary source: Addy Osmani, `agent-skills`, `code-review-and-quality`
- Repository: https://github.com/addyosmani/agent-skills
- Skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/code-review-and-quality
- GitHub stars checked on 2026-05-05: about 27.8k

## DevFlow adaptation

Use the upstream code-review-and-quality workflow as the base method for the DevFlow review stage. The local adaptation focuses the review on whether the generated artifacts satisfy the approved requirement and design.

## Purpose

Review the code and test artifacts for correctness, regressions, missing coverage, and delivery risk.

## Required input

- Requirements artifact
- Approved technical design
- Code change artifact
- Test artifact
- Review history

## Workflow

1. Compare the implementation against the acceptance criteria.
2. Compare the implementation against the approved design.
3. Check whether tests cover the important behavior and edge cases.
4. List findings before summary.
5. Order findings by severity.
6. Recommend approve only when there are no blocking issues.

## Output contract

Return concise Chinese content with these sections:

```text
评审结论：

发现的问题：
- [P0/P1/P2/P3] ...

覆盖情况：

残余风险：

建议：
```

## Quality bar

- Findings must be specific and actionable.
- Do not bury serious issues in a summary.
- Do not approve when acceptance criteria are missing.
- Mention uncertainty explicitly when evidence is incomplete.
