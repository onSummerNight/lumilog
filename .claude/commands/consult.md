---
description: "Advisory answer: recommendation, options, risks. No file edits."
argument-hint: "<question>"
disable-model-invocation: true
---
Act as a consultant on this question. Do not edit files or run commands that change anything.

Question: $ARGUMENTS

Answer in under 200 words unless asked for more:
1. Your recommendation in one or two sentences.
2. Two or three options with the real trade-off of each.
3. The main risk, and what would change your mind.
4. The next concrete step.

Say plainly when you don't know or when the user's plan has a problem. If the user accepts a recommendation, offer to record it with `/decide`.
