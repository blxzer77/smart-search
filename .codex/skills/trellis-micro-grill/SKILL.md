---
name: trellis-micro-grill
description: "Ask one high-value clarification question for small underspecified Trellis requests without creating a task by default."
---

# trellis-micro-grill

Use this skill for a small but underspecified request that should not create a Trellis task yet. It adapts the user's `grill-me` workflow into the Trellis mode ladder.

## When To Use

Use Micro-Grill when all are true:

- The request is likely one small deliverable or one direct action.
- Missing details would materially change the result.
- Creating a Trellis task would be heavier than the current uncertainty justifies.
- The user has not already provided enough detail to proceed.

Do not use Micro-Grill for:

- Multi-deliverable work.
- Cross-platform workflow changes.
- Risky refactors, migrations, prompt deployments, or durable architecture decisions.
- Work that already has an active Trellis task.

Escalate to Lite Task or Full Task if any of those appear.

## Procedure

1. State that this is Micro-Grill and that no Trellis task or file artifact will be created by default.
2. Ask exactly one high-value question at a time.
3. For each question, include a recommended answer based on the available evidence.
4. If the answer can be found from local files or repository context, inspect the codebase first instead of asking the user.
5. After each user answer, summarize the clarified requirement in one or two Chinese sentences.
6. Stop grilling as soon as the request is clear enough to execute directly.

## Escalation

Escalate once, without repeating already answered questions:

- To Lite Task when the clarified work is one independently verifiable deliverable that needs persistence, review, or continuation.
- To Full Task when the clarified work has multiple deliverables, broad impact, platform-adapter changes, external research dependency, or durable design risk.

If escalation happens, hand the clarified answers into `trellis-brainstorm` and update Trellis artifacts there.

## Language

- Ask the user in Simplified Chinese.
- Keep technical tool prompts, model handoffs, search queries, and delegation prompts in English when practical.
- Do not expose hidden chain-of-thought; provide concise reasons, recommendations, and decisions instead.
