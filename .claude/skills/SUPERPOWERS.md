# Vendored Superpowers skills

The skill folders here (brainstorming, diagnosing-superpowers,
dispatching-parallel-agents, executing-plans, finishing-a-development-branch,
receiving-code-review, requesting-code-review, subagent-driven-development,
systematic-debugging, test-driven-development, using-git-worktrees,
using-superpowers, verification-before-completion, writing-plans,
writing-skills) are copied unmodified from
https://github.com/obra/superpowers, MIT licensed (see SUPERPOWERS-LICENSE).

- Version: 6.4.2
- Commit: 8ca22dba9a94f28898bbce59f2537ff4d87c747d

## Why vendored

Cloud sessions on claude.ai/code do not install plugins listed under
`enabledPlugins` / `extraKnownMarketplaces`, and multi-repo sessions skip
repo SessionStart hooks. Skills committed under `.claude/skills/` load from
the clone in every session, so this copy is the reliable path.

## Differences from the plugin install

- Skills load unnamespaced: the text refers to `superpowers:brainstorming`,
  the skill here is `brainstorming`. Same for every `superpowers:<name>`.
- The plugin's SessionStart hook, which preloads `using-superpowers` into
  context, is not included. Skills still trigger from their descriptions.

## Updating

```bash
git clone --depth 1 https://github.com/obra/superpowers /tmp/superpowers
cp -a /tmp/superpowers/skills/. .claude/skills/
cp /tmp/superpowers/LICENSE .claude/skills/SUPERPOWERS-LICENSE
```

Then bump the version and commit above. Delete any skill folder that
upstream removed.
