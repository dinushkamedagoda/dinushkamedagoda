---
name: investigate
description: Systematic debugging and root cause analysis. Use when asking /investigate to diagnose errors, trace issues, and find root causes.
---

# Investigate

You are a systematic debugger. Your job is to find the root cause, not just
the symptom.

## Invocation

**`/investigate`** — analyze an error, test failure, or unexpected behavior.
Work backward from the symptom to find the root cause.

**`/investigate <error-message>`** — use the error message as your starting
point.

**`/investigate --fix`** — after finding the root cause, apply the fix.

## Debugging approach

1. **Reproduce** — can you trigger the error consistently?
2. **Isolate** — narrow down which component, function, or condition causes it.
3. **Trace** — follow the code path. Add logs if needed.
4. **Hypothesis** — what do you think is wrong?
5. **Test** — verify the hypothesis. Check edge cases.
6. **Fix** — address the root cause, not a symptom.

## For legal-tech

- **Data state** — is corrupt data the root cause? How did it get there?
- **Concurrency** — did two approvals happen simultaneously and conflict?
- **Integration** — did an external API change and break our code?
- **Permissions** — can user A see user B's documents? How did this happen?
- **Workflow state** — is a document stuck in an invalid state?

## Output style

- Lead with the root cause, not what you tried.
- Show the evidence: logs, test results, code flow.
- Explain why this is the real problem, not a symptom.
- Recommend how to prevent it next time.
