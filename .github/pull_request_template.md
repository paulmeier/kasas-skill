<!--
PR titles must follow Conventional Commits (feat:, fix:, docs:, refactor:,
perf:, deps:, ci:, chore:). The title becomes a CHANGELOG entry and drives the
next version, so write it for users. Add a `!` (e.g. feat!:) for breaking changes.
-->

## What & why

<!-- A short description of the change and the motivation. Link any issue. -->

## Checklist

- [ ] PR title follows Conventional Commits
- [ ] `make validate` passes (plugin + skill structure, tool names, helper flags)
- [ ] `make lint` and `make fmt-check` pass (auto-fix with `make fmt`)
- [ ] `make test` passes (pipeline smoke tests)
- [ ] If a skill references a new kasas MCP tool, it's added to `tools/kasas_tools.txt`
- [ ] Docs updated (README / CONTRIBUTING) if behaviour changed
