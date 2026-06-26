---
event_id: yt_lXUZvyajciY
date: 2025-10-17
title_inferred: "Andrej Karpathy on the Decade of Agents, Flaws of Reinforcement Learning, and the Future of AI"
duration: "146:07"
speakers_detected: 7
languages: [en]
generated: 2026-06-26
profile: lecture
---

# Andrej Karpathy on the Decade of Agents, Flaws of Reinforcement Learning, and the Future of AI

## Summary
Andrej Karpathy argues that developing truly capable AI agents will be a decade-long endeavor, not a single year's achievement. He critiques current reinforcement learning (RL) as a deeply flawed and inefficient paradigm, comparing it to "sucking supervision through a straw." Karpathy posits that we are building digital "ghosts" through imitation, not evolved "animals," and that a key research challenge is to isolate a model's "cognitive core" from its vast, often distracting, memorized knowledge. He views the current AI progress not as a sudden explosion, but as a continuation of a centuries-long trend of automation that will gradually reshape society.

## Operating Algorithm
Take a hyped claim → re-anchor on a precise definition or original framing → run a human/animal/evolution analogy but immediately flag its disanalogy → reason from the actual mechanism (information per token, credit assignment, data manifold) → place it on a continuum of automation/computing history → convert to a tractable-but-slow engineering bet

*Tags: Reframe · Mechanism · Analogy · Distinction*

## Through 3 Expert Lenses
- 🔬 **AI Researcher** — The critique of outcome-based RL is spot-on; its high variance and credit assignment problems are major hurdles. The field needs to pivot towards process-based supervision and developing methods for models to reflect and generate high-entropy synthetic data, which are significant unsolved research problems. `[43:47]`
- 💻 **Software Engineer** — The advice to build systems from scratch to truly learn is fundamental. His experience with NanoChat shows that while AI agents are great for boilerplate code, they fail on novel, intellectually-intense tasks, often getting stuck on common patterns and bloating the codebase. `[33:33]`
- 📈 **Technology Futurist** — The perspective that the 'intelligence explosion' is a continuous, decades-long process of automation, rather than a singular future event, provides a grounded framework for forecasting. This suggests a gradual societal transformation, not an overnight AGI takeover, though the potential for a hyper-exponential jump in growth remains a key point of debate. `[83:35]`

## Cognitive Moves
- **'Decade of agents' as a deliberate correction to 'year of agents'** — *Reframe* — Re-anchors the listener's timeline expectation from hype to a slower base-rate-driven estimate by reframing the unit of time `[01:20]`
- **We're not building animals, we're building ghosts** — *Distinction* — Splits 'intelligence' into evolution-derived vs imitation-derived kinds so the listener stops importing animal-learning intuitions wholesale `[10:42]`
- **0.07 bits/token in weights vs 320KB/token in KV cache — a 35-millionfold difference** — *Mechanism* — Swaps a fuzzy 'in-context feels smarter' intuition for a quantified information-density mechanism explaining why context learning differs from pretraining `[15:03]`
- **RL 'sucks supervision through a straw' — broadcasts one final bit across the whole trajectory** — *Mechanism* — Exposes the credit-assignment flaw of outcome-based RL by making the noisy upweighting of every token vivid and concrete `[43:47]`
- **If I can't build it, I don't understand it — build from scratch, no copy-paste** — *First-principles* — Reframes learning as forced confrontation with hidden gaps, collapsing 'surface knowledge' into 'real knowledge' only via construction `[30:06]`
- **AI is just an extension of computing; the intelligence explosion has been happening for decades** — *Reframe* — Dissolves the 'discrete AGI jump' framing by placing AI on the same hyper-exponential automation curve as compilers and the iPhone `[83:33]`
- **Coding works first because everything is text and infrastructure (diffs, IDEs) is pre-built** — *First-principles* — Maps which domains LLMs penetrate to a structural property (text-native + tooling) rather than to general intelligence `[75:11]`

## Outline
- **AGI is still a decade away** `[00:00]`
- **LLM cognitive deficits** `[30:33]`
- **RL is terrible** `[40:53]`
- **How do humans learn?** `[50:26]`
- **AGI will blend into 2% GDP growth** `[67:13]`
- **ASI** `[78:24]`
- **Evolution of intelligence & culture** `[93:38]`
- **Why self driving took so long** `[103:43]`
- **Future of education** `[117:08]`

## Key Points
- Developing robust, reliable AI agents will be the work of a decade, not a single year, due to significant challenges in intelligence, multimodality, and continual learning. `[01:20]`
- Current reinforcement learning methods are "terrible" because they inefficiently update an entire trajectory based on a single, noisy reward signal at the end. `[43:13]`
- We are not building 'animals' through an evolutionary process; we are building 'ghosts'—digital entities that mimic human knowledge from the internet. `[10:42]`
- Pre-training on internet data acts as a 'crappy evolution,' creating a cognitive core but also burdening models with excessive memorization that can be distracting. `[14:09]`
- The 'intelligence explosion' is not a future event but a continuous process of automation and recursive self-improvement that has been underway for centuries. `[00:26]`
- To truly understand AI, one must build the code from scratch; reading blog posts or watching presentations is insufficient and leads to missing knowledge. `[00:34]`
- Training on synthetic data from LLMs is difficult because their outputs are 'silently collapsed,' lacking the diversity and entropy of human-generated data. `[52:56]`

## Methods / Approach
- Pre-training a transformer on vast internet text to predict the next token, which builds both a knowledge base and a 'cognitive core' for reasoning. `[15:33]`
- Outcome-based reinforcement learning, where many solution attempts are generated and the entire trajectories of successful ones are upweighted. `[43:13]`
- Process-based supervision, which provides feedback at each step of a task rather than only at the end, is a promising but difficult alternative to outcome-based RL. `[46:46]`
- Using LLMs as 'judges' to provide rewards for process-based supervision, a technique vulnerable to the student model finding adversarial examples. `[47:27]`
- Distillation, where a large, powerful model is used to train a smaller, more efficient model, which is how most small models are created. `[63:10]`

## Notable Claims & Evidence
- Reinforcement learning is terrible. — It inefficiently applies a single final reward bit across an entire complex trajectory, upweighting even incorrect intermediate steps. `[his frame]` `[00:00]`
  ↳ *fails when:* The provocation backfires when the alternative isn't worse — in narrow verifiable-reward domains (math, code unit tests) RL already drives frontier gains, so dismissing it wholesale misguides people who could ship today; AlphaGo/AlphaZero-style RL won decisively where credit assignment is clean.
- We are building 'ghosts,' not 'animals.' — AI is trained by imitating human data, not via an evolutionary process that bakes in hardware and innate behaviors like in animals. `[his frame]` `[10:42]`
  ↳ *fails when:* The ghost/animal distinction misleads if multimodal embodied training closes the gap; betting too hard on 'imitation only' has burned people who assumed LLMs can't acquire grounded world models (e.g. early skeptics of emergent capabilities).
- The AI 'intelligence explosion' is already happening and has been for decades. — It's a continuation of the long-term trend of automation and recursive self-improvement, visible in GDP growth since the industrial revolution. `[his bet]` `[83:33]`
  ↳ *fails when:* The 'business as usual' continuity bet backfires if AGI is genuinely labor itself (his own counter-interlocutor's point) — economists who extrapolated steady 2% growth through every prior transition would have missed the industrial-revolution regime change, which itself was a discontinuity by his own admission.
- LLM coding agents fail at novel, intellectually intense tasks. — Experience building NanoChat showed models misunderstand custom code, try to force common patterns (like DDP), and bloat the codebase. `[his bet]` `[32:38]`
  ↳ *fails when:* His n=1 Nano-chat experience generalizes poorly as a forecast — 'asymmetrically worse at novel code' is a moving target; people who declared models permanently bad at task X (e.g. competitive math, agentic browsing) have repeatedly been overtaken within a year by the next training run.
- The internet, as a training dataset, is 'total garbage.' — A random document from a pre-training set is more likely to be 'slop' like stock tickers than a well-written article, which is extremely rare. `[consensus]` `[62:14]`
  ↳ *fails when:* Widely held among practitioners, but the 'just need better data' inference fails if signal genuinely requires scale to wash out noise (his own a96d caveat) — over-aggressive curation has historically hurt diversity and caused distribution collapse, so the cleanup isn't free.

**What doesn't transfer:** His specific timelines (decade), the 1-billion-parameter cognitive core, and 'business as usual / no discrete jump' are personal bets and taste; the durable transferable parts are the mechanism-level reasoning (information-per-token, credit assignment, data-manifold collapse) and the 'build-it-to-understand-it' epistemics.

## Open Questions
- How can we create an equivalent of human sleep or reflection for LLMs to distill daily experiences into their weights for continual learning? `[23:59]`
- How can we generate synthetic data for training that avoids 'model collapse' and maintains the high entropy and diversity of human thought? `[53:40]`
- How can we effectively remove the vast memorized knowledge from LLMs to isolate the pure 'cognitive core' responsible for reasoning and problem-solving? `[16:17]`
- How can we design un-gameable reward models for process-based supervision, given that LLM judges are susceptible to adversarial examples? `[47:49]`

## Takeaways
- To truly learn and understand complex AI systems, you must build them from scratch. Do not just copy-paste code or read summaries. `[30:25]`
- Temper expectations for AI agents; their development into reliable digital employees is a decade-long challenge, not an imminent breakthrough. `[02:29]`
- Use current AI coding tools as powerful autocompletes for boilerplate or unfamiliar languages, but don't rely on them for architecting novel or complex systems. `[32:13]`
- View AI not as a magical technology but as the next step in a long history of automation, which helps in understanding its gradual integration and impact. `[67:35]`

## Transfer Questions
- For our robotics roadmap, are we predicting the 'year' or the 'decade' of a capability — and is our timeline anchored on a hype quote or on observed base rates from prior hardware/control milestones?  *(from: 'Decade of agents' reframe)* `[01:20]`
- Are we importing animal/biological learning intuitions into our robot's training that don't hold because evolution baked in priors we aren't reproducing?  *(from: ghosts-not-animals distinction)* `[10:42]`
- How much information per interaction does our embedded agent actually assimilate into weights vs working state, and is sparse reward the bottleneck rather than the policy architecture?  *(from: bits-per-token mechanism / sucking supervision through a straw)* `[43:47]`
- Where in our sim-to-real or RL pipeline are we broadcasting one terminal reward across a long trajectory, and could process-level or step-wise credit assignment cut the noise?  *(from: RL credit-assignment mechanism)* `[43:47]`
- Which of our robotics subsystems do we truly understand because we built them from scratch, versus subsystems where we only have 'surface knowledge' from copied stacks?  *(from: if I can't build it I don't understand it)* `[30:06]`
- Is the robotics capability we're targeting structurally amenable today (right sensors, pre-built tooling, clean feedback) the way coding was text-native, or are we fighting a domain with no 'diff viewer' equivalent?  *(from: coding-works-first structural mapping)* `[75:11]`

## Field Implications — Where to Steer
- Researchers should focus on moving beyond naive outcome-based RL to develop more robust learning algorithms involving reflection, review, and process-based supervision. `[45:18]`
- Practitioners need to prioritize creating high-quality, curated datasets, as progress is bottlenecked by the 'terrible' quality of raw internet data. `[65:00]`
- The field should explore methods to separate a model's reasoning abilities ('cognitive core') from its memorized knowledge, potentially leading to smaller, more general, and less biased models. `[57:39]`

## Industry Outlook — Fading vs Thriving
**📉 Fading**
- Using sparse-reward game environments (e.g., Atari) as the primary paradigm for developing AGI, which is now seen as a misstep. `[05:36]`
- The belief that simply increasing model parameter count is the primary driver of progress; focus is shifting to data quality, algorithms, and distillation. `[60:08]`
- The idea of fully replacing knowledge workers with AI in the short term; the more likely model is human supervision of AI teams. `[71:21]`

**📈 Thriving**
- AI agents for digital knowledge work, though on a decade-long timeline. `[01:52]`
- Improved learning algorithms beyond current RL, such as those incorporating reflection, review, and process-based supervision. `[45:27]`
- Data curation and distillation techniques to create smaller, more efficient, and more capable models from higher-quality data. `[63:08]`
- Coding as the initial, most successful application domain for LLM agents due to its text-based nature and existing infrastructure. `[75:02]`

## Speakers
- **A** — AI Researcher (Andrej Karpathy) `00:00→92:02`
- **B** — Interviewer `00:00→92:02`

## References & Resources Mentioned
- Richard Sutton `[03:19]`
- Jeff Hinton `[04:33]`
- AlexNet `[04:45]`
- Atari deep reinforcement learning `[05:18]`
- OpenAI Universe project `[06:59]`
- Yann LeCun's 1989 convolutional network paper `[25:44]`
- NanoChat repository `[29:16]`
- InstructGPT paper `[44:36]`
- DeepSeek V3.2 model `[24:59]`
- https://dwarkesh.substack.com/p/andrej-karpathy  *(from video description)*
- https://podcasts.apple.com/us/podcast/andrej-karpathy-agi-is-still-a-decade-away/id1516093381?i=1000732326311  *(from video description)*
- https://open.spotify.com/episode/3iIYVmmhXwh3fOumypWVpC?si=33d37708b2b44e2f  *(from video description)*
- https://labelbox.com/dwarkesh  *(from video description)*
- https://mercury.com  *(from video description)*
- https://gemini.google  *(from video description)*
- https://dwarkesh.com/advertise  *(from video description)*
