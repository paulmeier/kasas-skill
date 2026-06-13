# Contributing to kasas-skill

Thanks for helping improve the kasas plugin. This repo is small but it ships to
Claude Code and Claude Desktop users, so a light pipeline keeps it honest.

## Ground rules

- **`main` is protected.** All changes land through a pull request that passes
  CI — direct pushes are rejected.
- **Conventional Commits.** PR titles (and squash-merge commits) must follow
  [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`,
  `docs:`, `refactor:`, `perf:`, `deps:`, `ci:`, `chore:`. The title becomes a
  CHANGELOG entry and drives the next version. Use `!` (e.g. `feat!:`) for a
  breaking change.

## Local development

Everything CI runs is one command:

```sh
make ci        # validate + lint + fmt-check + test
```

Individual targets (`make help` lists them):

| Target | What it does |
| --- | --- |
| `make validate` | Stdlib check: JSON manifests, skill/agent frontmatter, that every `mcp__kasas__*` reference is a real kasas tool (`tools/kasas_tools.txt`), and that every helper-script flag used in a skill exists. |
| `make claude-validate` | The official `claude plugin validate .` (needs the Claude Code CLI). |
| `make lint` / `make fmt` / `make fmt-check` | [ruff](https://docs.astral.sh/ruff/) lint + format for the Python helpers. No global install needed — falls back to `uvx ruff`. |
| `make test` | End-to-end pipeline smoke tests (`tests/`): exact-decimal money math + valid SVG for every chart type. |

The runtime helpers in `scripts/` are **standard-library only** — keep them that
way so they run on any machine with Python 3.8+. Dev tooling (ruff) is pinned in
`requirements-dev.txt`.

## Adding or changing a skill

- A skill is a directory `skills/<name>/SKILL.md` with YAML frontmatter
  (`name`, `description`, optional `argument-hint`, `allowed-tools`) and a
  concrete, runnable body. The directory name becomes the `/kasas:<name>`
  command in Claude Code.
- It must work in **both** environments: the Claude Code path (bundled
  `scripts/` via Bash) and the Claude Desktop path (an Artifact). `make validate`
  does not check this — reviewers do.
- If you reference a new kasas MCP tool, add it to `tools/kasas_tools.txt` in the
  same PR, or `make validate` will fail.
- Money is always exact decimals (kasas amounts are signed decimal strings);
  never mix or convert currencies (kasas tracks one currency per account).

## Releases

[release-please](https://github.com/googleapis/release-please) watches `main` and
keeps an open "release" PR that accumulates the CHANGELOG and the next version.
Merging that PR bumps `version` in `.claude-plugin/plugin.json`, updates
`CHANGELOG.md`, and tags a GitHub Release with a packaged plugin bundle attached.
You never bump the version by hand.
