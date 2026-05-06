# Code Change Skill

## Upstream sources

- Primary source: Addy Osmani, `agent-skills`, `incremental-implementation`
- Supporting source: Vercel Labs, `agent-skills`, web engineering best practices when the target is frontend code
- Addy repository: https://github.com/addyosmani/agent-skills
- Addy skill path: https://github.com/addyosmani/agent-skills/tree/main/skills/incremental-implementation
- Vercel repository: https://github.com/vercel-labs/agent-skills
- GitHub stars checked on 2026-05-05: Addy about 27.8k, Vercel about 25.3k

## DevFlow adaptation

Use the upstream incremental-implementation workflow as the base method for the DevFlow code stage. The local adaptation requires the model to return complete file contents in DevFlow's JSON patch format.

## Purpose

Apply the approved design as a small, reviewable code change.

## Required input

- Requirements artifact
- Approved technical design
- Current project files
- Review history and latest reject reason, if any

## Workflow

1. Read the approved design and identify the smallest useful code change.
2. Modify only files needed for the requested behavior.
3. Preserve existing patterns and naming.
4. Keep generated code simple and local to the affected feature.
5. Include complete file content for every changed file.
6. Do not claim tests have run unless the test output is provided.

## Output contract

For model-driven code patching, return only JSON:

```json
{
  "files": [
    {
      "path": "relative/path.ext",
      "content": "complete file content"
    }
  ]
}
```

## Quality bar

- No unrelated refactors.
- No placeholder code.
- No invented dependencies unless absolutely necessary.
- Changed files must stay inside the target workspace.
- Output must be parseable JSON with no Markdown wrapper.
