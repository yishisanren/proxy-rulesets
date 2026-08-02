# Karing v2 Rule-set Subscriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit Karing-compatible SRS v2 subscriptions for AI and broker-hk while preserving existing SRS v1 files for older clients, and document all three Karing subscription URLs.

**Architecture:** Keep the canonical AI and broker source rule sets unchanged. Add a small deterministic Python converter that copies a source rule-set while changing only its schema version to 2, compile those derived JSON files with sing-box, and retain adblock's existing SRS v2 artifact. Extend local and CI builds so generated artifacts do not drift.

**Tech Stack:** Python 3 standard library, Bash, sing-box CLI, GitHub Actions, unittest.

---

### Task 1: Define the generated-artifact contract with failing tests

**Files:**
- Create: `tests/test_karing_rulesets.py`

- [ ] **Step 1: Write tests for version conversion and committed artifacts**

Create unittest cases that execute `scripts/set_ruleset_version.py`, require the output JSON to have `version: 2` with unchanged `rules`, and require `ai/ai-all-karing.{json,srs}`, `broker/broker-hk-karing.{json,srs}`, and `adblock/ad-reject.srs` to carry the SRS v2 magic header.

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL because the converter and Karing-specific AI/broker artifacts do not exist.

### Task 2: Implement deterministic v2 derivation

**Files:**
- Create: `scripts/set_ruleset_version.py`

- [ ] **Step 1: Implement the minimum converter**

Accept `INPUT OUTPUT VERSION`, validate that the source contains `rules`, copy the JSON, change only `version`, and write stable UTF-8 JSON.

- [ ] **Step 2: Run the focused converter test**

Run: `python3 -m unittest tests.test_karing_rulesets.KaringRuleSetTests.test_version_deriver_preserves_rules -v`
Expected: PASS.

### Task 3: Integrate local and CI builds

**Files:**
- Modify: `build.sh`
- Modify: `.github/workflows/build.yml`
- Create: `ai/ai-all-karing.json`
- Create: `ai/ai-all-karing.srs`
- Create: `broker/broker-hk-karing.json`
- Create: `broker/broker-hk-karing.srs`

- [ ] **Step 1: Extend the local build**

Derive and compile Karing v2 files for broker and AI using the resolved sing-box binary. Keep the existing v1 files unchanged.

- [ ] **Step 2: Extend GitHub Actions**

Generate both broker formats plus the AI Karing derivative, add explicit binary paths, and commit both `broker/` and `ai/` outputs.

- [ ] **Step 3: Generate artifacts locally**

Run the converter and sing-box compilation commands with a pinned local executable.

- [ ] **Step 4: Run the complete test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all tests PASS.

### Task 4: Document and publish subscriptions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document Karing formats and URLs**

Add AI to the repository layout/data table, add Karing rows for AI and broker-hk, and keep the adblock Karing row.

- [ ] **Step 2: Verify representative matching and non-matching domains**

Run `sing-box rule-set match -f binary` on all three SRS v2 files. Require AI domains such as `chatgpt.com` and `anthropic.com`, broker domains such as `futunn.com` and `laohu8.com`, and ad domains such as `doubleclick.net` to match; require unrelated control domains not to match.

- [ ] **Step 3: Commit, push, and merge**

Commit on `feat/karing-v2-rulesets`, push, open a PR, verify checks, and merge to `main`.

- [ ] **Step 4: Verify remote bytes**

Download all three raw URLs from `main`, compare them with the verified local artifacts using SHA-256, check SRS v2 magic, and rerun representative match tests against the downloaded files.
