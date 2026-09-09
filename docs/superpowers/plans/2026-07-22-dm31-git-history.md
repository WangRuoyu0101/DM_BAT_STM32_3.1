# DM3.1 Git History Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the clean DM2.1 Git history into the current DM3.1 workspace, point `origin` at the new repository, and create one local DM3.1 migration commit.

**Architecture:** Copy only the adjacent repository metadata; keep the current DM3.1 working tree intact. Audit ignore rules before staging, then use normal Git add/commit and verify history, remote, and status.

**Tech Stack:** Git and shell commands only.

## Global Constraints

- Source metadata is `../DM2.1_BAT/.git`; never modify `../DM2.1_BAT`.
- Expected inherited branch is `main` and expected inherited HEAD is `216c8c8`.
- New origin is exactly `git@github.com:WangRuoyu0101/DM_BAT_STM32_3.0.git` for fetch and push.
- Do not use `git init`, reset, rebase, force checkout, force push, or automatic push.
- Do not commit `.venv`, `__pycache__`, `*.pyc`, build output, `.DS_Store`, `.superpowers`, or `tmp`.
- Preserve all current DM3.1 source and documentation files.

---

### Task 1: Restore metadata and audit the working tree

**Files:**
- Copy: `../DM2.1_BAT/.git` -> `.git`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: clean adjacent repository metadata at HEAD `216c8c8`.
- Produces: current workspace recognized as the inherited `main` repository with generated files ignored.

- [ ] **Step 1: Revalidate the source repository**

```sh
test -d ../DM2.1_BAT/.git
test -z "$(git -C ../DM2.1_BAT status --porcelain)"
test "$(git -C ../DM2.1_BAT branch --show-current)" = main
test "$(git -C ../DM2.1_BAT rev-parse --short HEAD)" = 216c8c8
```

Expected: exit 0 with no output.

- [ ] **Step 2: Copy the historical metadata without touching files**

```sh
test ! -e .git
cp -a ../DM2.1_BAT/.git .git
```

Expected: `.git` exists; the current source tree is unchanged.

- [ ] **Step 3: Verify inherited history before any staging**

```sh
test "$(git branch --show-current)" = main
test "$(git rev-parse --short HEAD)" = 216c8c8
git log -3 --oneline
```

Expected: HEAD `216c8c8` followed by the existing DM2.1 history.

- [ ] **Step 4: Restore and extend the inherited ignore rules minimally**

The metadata copy does not copy working-tree files, and the current workspace has no
root `.gitignore`. Recreate the inherited rules plus the DM3.1 local-output rules as:

```gitignore
.DS_Store
.worktrees/

# Build output
build/

# Local toolchains should be installed separately or provided outside Git.
toolchains/

# Editor and OS noise
*.swp
*.swo
Thumbs.db

# Python / Qt local output
.venv/
__pycache__/
*.py[cod]
deployment/
dist/

# Local agent and scratch data
.superpowers/
tmp/
```

- [ ] **Step 5: Audit ignored and staged candidates**

```sh
git status --short --untracked-files=all
git check-ignore -v QT_Host/.venv STM32/build STM32/.DS_Store .superpowers/sdd/progress.md tmp
```

Expected: generated/local paths are ignored; source, tests, README, specs, plans, schematics, and project files remain visible as intended changes.

### Task 2: Switch origin, commit, and verify

**Files:**
- Modify: Git remote configuration in `.git/config`
- Commit: all intended DM3.1 working-tree changes

**Interfaces:**
- Consumes: the audited inherited repository from Task 1.
- Produces: one local migration commit on `main` and the new DM3.1 `origin`.

- [ ] **Step 1: Change origin through Git**

```sh
git remote set-url origin git@github.com:WangRuoyu0101/DM_BAT_STM32_3.0.git
git remote -v
```

Expected: both fetch and push URLs equal the new URL.

- [ ] **Step 2: Stage intended files and inspect the index**

```sh
git add -A
git status --short
git diff --cached --stat
```

Expected: no ignored virtual environment, cache, build, `.DS_Store`, `.superpowers`, or `tmp` path is staged.

- [ ] **Step 3: Run the existing regression suites before commit**

```sh
python3 -m unittest discover -s STM32/tests
python3 -m unittest discover -s Linux_ROS_WS/src/stm32_jetson_serial_comm/tests
PYTHONPATH=QT_Host:Linux_ROS_WS/src/stm32_jetson_serial_comm QT_QPA_PLATFORM=offscreen \
/tmp/dm31-qt-venv/bin/python -m unittest discover -s QT_Host/tests
```

Expected: 52 STM32, 91 Jetson/host, and 12 Qt tests pass.

- [ ] **Step 4: Create the local migration commit**

```sh
git commit -m "feat: adapt DM3.1 board and add Qt debug host"
```

Expected: one new commit on `main` descending from `216c8c8`.

- [ ] **Step 5: Verify the completed repository**

```sh
git log -3 --oneline --decorate
git remote -v
git status --short
```

Expected: new commit is HEAD, `origin` uses the DM3.1 URL, and status has no unexpected changes. Do not push.
