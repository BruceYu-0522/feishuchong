# Test Design Skill

## Upstream sources

- Primary source: Addy Osmani, `agent-skills`, `test-driven-development`
- Repository: https://github.com/addyosmani/agent-skills
- Skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/test-driven-development
- GitHub stars checked on 2026-05-05: about 27.8k

## DevFlow adaptation

Use the upstream test-driven-development workflow as the base method for the DevFlow test stage. The local adaptation asks the model to generate lightweight tests for the actual changed workspace.

## Purpose

Create tests that verify the behavior requested by the acceptance criteria and implemented by the code stage.

## Required input

- Requirements artifact
- Technical design artifact
- Code change artifact
- Current project files

## Workflow

1. Extract testable behavior from the acceptance criteria.
2. Prefer tests that exercise real code rather than testing mocks.
3. Cover the main path and at least one meaningful edge case.
4. Keep tests runnable with the project's existing tooling.
5. For this demo target, prefer Node.js `assert` and avoid new dependencies.
6. Do not state that tests passed unless the run output is available.

## Output contract

For model-driven test patching, return only JSON:

```json
{
  "files": [
    {
      "path": "tests/example.test.js",
      "content": "complete test file content"
    }
  ]
}
```

## Quality bar

- Test files must be under `tests/`.
- Tests must map to acceptance criteria.
- Tests must be deterministic.
- No snapshot-only or meaningless `assert(true)` tests unless explicitly used as a temporary smoke check.
