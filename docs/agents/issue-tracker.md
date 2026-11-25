# Issue tracker

Pia tracks issues and specs in GitHub Issues for `kingiol/Pia`. Use the `gh` CLI. Confirm the target with `gh repo view --json nameWithOwner` before your first write, especially in a fork. Pass `-R kingiol/Pia` to target Pia explicitly.

## Issue operations

- **Publish** an issue or spec with `gh issue create --title "..." --body-file <file>`.
- **Read** a ticket with `gh issue view <number> --json number,title,body,labels,comments`.
- **List** tickets with `gh issue list --state open --json number,title,body,labels,comments`. Use `--label` and `--state` to narrow the results.
- **Set a triage label** with `gh issue edit <number> --add-label "..." --remove-label "..."`. Use the [triage label mapping](triage-labels.md).
- **Comment** with `gh issue comment <number> --body-file <file>`. To close a ticket, post the explanation and then use `gh issue close <number>`.

## Parent issues and dependencies

- **Sub-issues**. Add `--parent <parent>` to `gh issue create`, or use `gh issue edit <parent> --add-sub-issue <child>` for an existing ticket. If sub-issues are unavailable, add the child to the parent's task list and put `Part of #<parent>` at the top of the child body.
- **Blocking**. Use `gh issue create --blocked-by <blocker>` or `gh issue edit <child> --add-blocked-by <blocker>`. If native dependencies are unavailable, put `Blocked by: #<blocker>` at the top of the child body. A ticket is startable once every blocker is closed.
- **Open blockers**. Use `gh api repos/kingiol/Pia/issues/<number> --jq .issue_dependencies_summary.blocked_by`. For blockers recorded in the body, check the state of each linked issue.

## Pull requests as a triage surface

**PRs as a request surface: no.**

If enabled, read the PR body and comments with `gh pr view <number>` and `gh pr view <number> --comments`, and review its changes with `gh pr diff <number>`. List open PRs with `gh api --paginate 'repos/kingiol/Pia/pulls?state=open'` and exclude author associations `OWNER`, `MEMBER`, and `COLLABORATOR`. Use `gh pr comment`, `gh pr edit`, and `gh pr close` for triage. Resolve a bare number with `gh pr view` first, then `gh issue view`.

## Wayfinding

- Use a `wayfinder:map` issue for Notes, Decisions-so-far, and Fog. Link child tickets as sub-issues and label them `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`).
- For the frontier, read the map's children in map order and pick the first open, unassigned ticket with zero open blockers.
- Claim the ticket with `gh issue edit <number> --add-assignee @me`. To resolve it, post the answer, close the ticket, and add a brief summary and a link to the map's Decisions-so-far.
