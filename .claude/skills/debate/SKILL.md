---
name: debate
description: Run a debate between 5 subagents. Each proposes its own project idea, they criticize each other's ideas, and the winning idea becomes the answer. Use when the user says "debate", "дебаты", "пусть поспорят", or asks to come up with / choose a project, idea or solution through a contest of ideas.
---

# Debate: 5 agents propose, argue, one idea wins

The user explicitly asked for this, so spawning subagents is allowed. Reply in the user's language.

## Input
The topic is the skill args or the user's last request (e.g. "придумай проект"). If there is no topic at all, ask one short question. Otherwise do not ask: pick sensible defaults.

## Step 1: Proposals (5 agents in parallel)
In ONE message, launch 5 Agent calls (subagent_type `general-purpose`, foreground, all independent). Give each a distinct persona so ideas differ:

1. **Pragmatist**: useful, shippable in a day, solves a real problem.
2. **Creative**: unusual, playful, memorable.
3. **Engineer**: technically interesting, clean architecture, learning value.
4. **Product thinker**: clear audience, growth, why people would come back.
5. **Skeptic-builder**: smallest possible scope that still delights; hates bloat.

Prompt for each: the topic, the persona, and "Propose exactly ONE idea. Output: name, one-sentence pitch, who it is for, stack, MVP scope, biggest risk. Under 150 words. Do not write files or code." Tell them they work alone and do not know the others' ideas.

## Step 2: Debate (5 agents in parallel)
Collect the 5 proposals (number them A to E). Launch 5 agents again, same personas, each given ALL five proposals and told:
"You defend your own idea (yours is <letter>). Give: (a) the sharpest weakness of each of the other four, one sentence each; (b) the strongest attack on your own idea and your rebuttal; (c) if another idea beats yours on some point, say so and name what you would steal. Under 200 words. Be concrete, no flattery."

## Step 3: Vote (5 agents in parallel)
Give each agent all proposals and all debate arguments. Ask: "Vote for the single best idea. You may NOT vote for your own. Output: letter, then two sentences of reasoning, then a score 1-10 for each idea." Voting is anonymous and independent.

## Step 4: Verdict
Tally votes. Break ties by total of the 1-10 scores; if still tied, you decide and say so. Do not override a clear winner with your own taste.

Print, compactly:
- the five ideas (name + pitch, one line each),
- the strongest clash from the debate (2-3 lines),
- vote table (who voted for what, total scores),
- **Winner**: the idea in full, improved with the best points "stolen" from rivals during the debate.

## Step 5: Offer
End with one line: offer to build the winner's MVP. Do not start building and do not commit unless asked.

## Rules
- Subagents must not edit files or the repo.
- Never fabricate votes or arguments: use only what the agents returned.
- If an agent fails, rerun it once; if it fails again, continue with 4 and say so.
