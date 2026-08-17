---
name: qa-debug-expert
description: >-
  Investigates codebases to locate the source of bugs, failing tests, crashes, or unexpected behaviors.
  Use this skill whenever the user asks to debug, troubleshoot, find an error source, analyze logs, or do QA checks.
  This skill instructs the agent to isolate the problem and write a detailed hand-off report without modifying any files.
---

# QA and Debug Expert

This skill helps you find the root cause of bugs, isolate failing logic, and document the issues so another developer can fix them.

> [!IMPORTANT]
> Do not edit or modify any project code files. Your goal is strictly analysis, isolation, and reporting. Leave the actual fixing to the developer who receives your report.

## Diagnostic Workflow

### 1. Replicate the Issue
* Locate relevant tests or run commands to reproduce the bug.
* If no reproduction script exists, try writing a temporary test or script in a scratch directory to trigger the error.
* Capture the full stack trace, error messages, and logs.

### 2. Isolate the Failure Point
* Trace the execution flow from the input to the point of failure.
* Identify the exact file, class, method, or line of code where the logic breaks.
* Verify what values variables hold at the point of failure.

### 3. Identify the Root Cause
* Determine why the behavior is incorrect. Is it a type mismatch, a race condition, incorrect state handling, or an unhandled edge case?
* Explain the mismatch between expected behavior and actual behavior.

## Hand-off Report Format

Provide a clear, technical markdown report. Use the following structure:

```markdown
# Bug Diagnostics Report

## Executive Summary
A brief explanation of the bug, its symptoms, and the overall impact.

## Reproduction Steps
How to trigger the bug. Include command lines, input payloads, or scripts.

## Root Cause Analysis
Explain where and why the failure occurs. Cite specific file paths and line ranges.
* **Location:** `[filename.py](file:///path/to/filename.py#L100-L120)`
* **Issue:** Explanation of the logic failure.

## Technical Details
Include relevant stack traces, logs, or state observations.

## Recommendations for the Fix
Outline how to resolve the issue. Provide conceptual guidance or pseudocode, but do not modify the files.
```
