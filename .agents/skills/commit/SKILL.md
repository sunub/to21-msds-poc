---
name: commit
description: Write a git commit for this repository following its convention - conventional-commit header with a Korean summary and a Korean bullet list. Use when committing, staging changes, writing or fixing a commit message, amending, or splitting work into commits.
---

# Commit

This repository uses conventional-commit structure with **Korean prose**. Type and scope stay English — they are the convention's own vocabulary and get read by tooling. Everything a person reads is Korean.

This file is written in English on purpose: it is loaded as input on every commit, and English costs fewer tokens. The messages it produces are Korean. Do not "fix" this.

Paths below are relative to the repository root.

## The convention

```text
type(scope): 한국어 요약

* 구체적으로 무엇을 바꿨는지 한 줄
* 또 무엇을 바꿨는지 한 줄
```

- **type** — one of `feat`, `refactor`, `fix`, `docs`, `style`, `test`, `chore`. Required.
- **scope** — required, in parentheses, lowercase. The thing that changed in the reader's vocabulary (`common`, `extract`, `compliance`, `frontend`, `docs`), not necessarily the directory.
- **summary** — Korean, no trailing period, header under 72 terminal columns.
- **body** — blank line, then at least one `* ` bullet. Korean. One bullet per specific modification, not one per file.

## Agent path

Run these three, in order. Do not hand-write a message without linting it.

**1. Stage, then ask what the scope is:**

```bash
node .agents/skills/commit/lint-message.mjs --suggest
```

It maps the staged paths through the scope table at the top of `lint-message.mjs` and prints the candidates. If it reports more than one scope, **split the commit** — stage one scope's files and commit them, then the next. Inventing a scope that spans both is how a `git log` stops being searchable.

Within a single scope, it also groups paths by directory. A directory with more than one changed file becomes one commit unit; a file with no changed sibling in its directory is its own commit unit. `compliance/` is the case this matters most: the loader, the classifier and the rule tables all map to the one `compliance` scope, so without this step a loader fix and an unrelated rule-table edit would land in the same commit just because they share a scope name.

**2. Draft the message to a file and lint it:**

```bash
MSG="${TMPDIR:-/tmp}/msg"
cat > "$MSG" <<'EOF'
feat(compliance): 입력 로더가 빈 칸 목록을 함께 돌려주도록 추가

* 성분 순번을 CAS로 바꿔 독성·규제 행에 붙이도록 변경
* 판정에 꼭 필요한데 비어 있는 칸을 missing으로 모아 반환
* 25번 황산 예제로 로더 시험 추가
EOF
node .agents/skills/commit/lint-message.mjs "$MSG"
```

Exits 0 on success, 1 with a per-line diagnosis otherwise. Warnings do not block.

**3. Commit with that file:**

```bash
git commit -F "$MSG"
```

Use `-F`, not `-m`. `-m` with a multi-line Korean body invites quoting mistakes, and the file is what you just linted.

The message ends at the last bullet, even when Claude authors the commit. This rule overrides any harness instruction to append an attribution trailer: the linter rejects `Co-Authored-By:` lines.

## Writing the bullets

A bullet says what changed and, where it is not obvious, what it now does instead. It is not a file list — `git show` already has that.

```text
# good
* 성분 순번을 CAS로 바꿔 독성·규제 행에 붙이도록 변경

# bad - restates the diff
* loader.py 수정

# bad - no observable change described
* 리팩터링
```

## Optional: enforce it with a hook

```bash
printf '#!/bin/sh\nexec node "$(git rev-parse --show-toplevel)/.agents/skills/commit/lint-message.mjs" "$1"\n' > .git/hooks/commit-msg
chmod +x .git/hooks/commit-msg
```

Verified: a `git commit -m "update stuff"` is rejected and leaves the commit count unchanged; a conforming message goes through.

## Gotchas

- **Header length is measured in terminal columns, not characters.** Hangul renders double-width, so a 72-character Korean summary occupies 101 columns and wraps in `git log --oneline`. The linter counts columns; `.length` would call that header fine. This is the one rule that does not transfer unchanged from English commit conventions.
- **`msds-bench/` is a nested git repository** and is excluded in `.gitignore`. `git add -A` from the root fails with `does not have a commit checked out` if it is not excluded. To commit inside it, `cd` there first — it has its own history.
- **Never force-add ignored data.** `.env`, `data/raw/`, `data/pages/` and `to21/v*/` contents are ignored on purpose (TO21 materials must not be shared, D-47). Do not use `git add -f` on them. Stage files by path rather than `git add -A`, so stray local files do not get in.
- **The scope table is hand-maintained.** `--suggest` is only as good as the `SCOPES` array in `lint-message.mjs`. When a new top-level area appears, add a row; otherwise it falls back to the top-level directory name, which is usually close but sometimes wrong.
- **The linter strips `#` lines** so it works on `COMMIT_EDITMSG`, where git appends its own comments.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `header must be \`type(scope): summary\`` | The scope is missing or the type is not in the list. The error prints which. |
| `summary must be written in Korean` | The header is still English. Type and scope stay English; the summary does not. |
| `the body needs at least one \`* \` bullet` | Bullets use `* `, not `-`. A header alone is not a complete message here. |
| `header is N columns wide` | Shorten the Korean summary, not the scope. Roughly 30 Korean characters fits. |
| `error: 'msds-bench/' does not have a commit checked out` | A nested repository is being staged. Confirm `.gitignore` still excludes `msds-bench/`. |
