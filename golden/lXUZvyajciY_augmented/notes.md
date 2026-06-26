---
event_id: yt_lXUZvyajciY
date: 2025-10-17
title_inferred: "Andrej Karpathy on the Decade of Agents, Flaws of Reinforcement Learning, and AI's Future"
duration: "146:07"
speakers_detected: 7
languages: [en]
generated: 2026-06-25
profile: lecture
---

# Andrej Karpathy on the Decade of Agents, Flaws of Reinforcement Learning, and AI's Future

## Summary
Andrej Karpathy argues that we are in the 'decade of agents,' not the 'year,' because current models possess significant cognitive deficits that will take years to solve. He critiques modern reinforcement learning as a deeply flawed, high-variance process, memorably describing it as 'sucking supervision through a straw.' Karpathy distinguishes between the 'ghosts' we are building—digital intelligences based on imitating human data—and biological 'animals' shaped by evolution, suggesting we should focus on engineering useful systems rather than mimicking biology. He concludes by framing AI not as a revolutionary break but as a continuation of a centuries-long trend of automation, which will likely continue, rather than accelerate, the existing exponential curve of economic growth.

## Operating Algorithm
Start with a practical engineering goal (build useful things) → Identify historical missteps and premature attempts (e.g., RL on games before good representations) → Analyze current SOTA's fundamental limitations (e.g., RL's sparse supervision, model collapse) → Formulate analogies to biological/human processes to highlight gaps (e.g., evolution vs. pre-training) → Propose research directions to bridge these gaps (e.g., process supervision, separating cognition from memory)

*Tags: Analogy · Mechanism · Sequencing · Distinction*

## Through 3 Expert Lenses
- 🔬 **ML Researcher** — Karpathy's critique of outcome-based RL is spot-on; the credit assignment problem is a fundamental bottleneck. His focus on process-based supervision, reflection, and solving model collapse points directly to the key research frontiers needed to move beyond current paradigms. `[45:58]`
- 🛠️ **AI Practitioner** — His experience with NanoChat is a crucial reality check. Agents are not magic; they excel at boilerplate and familiar domains but fail at novel, architecturally precise tasks. The advice to build from scratch to gain true understanding is timeless and especially relevant in this era of high-level abstractions. `[32:38]`
- 📈 **AI Strategist** — The 'decade of agents' framing provides a realistic timeline that counters industry hype. His view of AI as a continuation of automation, unlikely to cause a discontinuous jump in GDP growth, is a contrarian but historically grounded perspective on its economic integration. `[83:35]`

## Cognitive Moves
- **Pre-training is this kind of like crappy evolution.** — *Analogy* — Frames pre-training not as an end-state but as a foundational, brute-force process analogous to evolution, setting the stage for more refined learning later. `[14:09]`
- **We're not actually building animals, we're building ghosts.** — *Distinction* — Creates a sharp distinction between AI (digital, imitation-based) and biological intelligence (evolved, embodied) to prevent flawed reasoning from direct biological comparisons. `[10:42]`
- **You're sucking supervision through a straw.** — *Mechanism* — Provides a vivid, intuitive model for why sparse-reward RL is so inefficient, by explaining the mechanism of broadcasting a single final reward bit across a long, complex trajectory. `[43:47]`
- **You actually have to get the language model first... before you sort get to those agents.** — *Sequencing* — Establishes a necessary order of operations in AI development, explaining why earlier agent attempts (like on Atari/Universe) failed due to lacking a powerful representation layer. `[08:46]`
- **I don't see AI as like a distinct technology... we've been recursively self-improving... for a long time.** — *Reframe* — Re-frames the 'AI revolution' not as a singular, discontinuous event but as the latest step in a continuous, centuries-long process of automation, changing the expectation of its economic impact. `[84:22]`
- **We're not actually that good at memorization, which is actually a feature, not a bug.** — *Inversion* — Flips a perceived human weakness (poor memory) into a strength (forcing generalization) to argue for a new research direction: building AIs with intentionally less memory. `[57:34]`

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
- Building truly capable AI agents will be a decade-long endeavor, not a single-year breakthrough, due to current cognitive deficits like the lack of continual learning. `[01:20]`
- Current reinforcement learning is a 'terrible,' high-variance method that inefficiently applies a single reward signal across an entire complex trajectory. `[42:27]`
- We are building digital 'ghosts' by imitating human data, not biological 'animals' which are products of evolution with immense built-in hardware. `[10:42]`
- Pre-training acts as a 'crappy evolution,' creating a foundational model, but its power is hindered by excessive memorization of internet 'garbage'. `[14:09]`
- Model collapse, where models produce non-diverse outputs, is a major obstacle for synthetic data generation and achieving human-like creativity. `[52:56]`
- The ideal AI would have a 'cognitive core' with less memory, forcing it to generalize and reason rather than rely on rote memorization, similar to how human memory limitations are a feature. `[57:39]`
- AI's progress is a continuation of a long-term, recursive trend of automation, and its economic impact will likely be absorbed into the existing exponential growth curve rather than creating a new, steeper one. `[83:55]`

## Methods / Approach
- Pre-training on vast internet datasets to create a base model with a 'cognitive core' and broad knowledge. `[08:26]`
- Outcome-based reinforcement learning, where entire trajectories are up-weighted or down-weighted based on a single final reward. `[43:13]`
- Process-based supervision, an alternative to RL that provides feedback at each step of a task, though it is difficult to automate credit assignment. `[46:46]`
- Using powerful LLMs as 'judges' to provide automated, step-by-step rewards for process-based supervision, but this is vulnerable to adversarial examples. `[47:27]`
- Distillation, where a smaller model is trained to mimic a larger, more capable one, which is how most small, efficient models are created. `[63:03]`
- Building from scratch as a method for deep learning, as demonstrated by the NanoChat project, to force confrontation with misunderstood details. `[30:06]`

## Notable Claims & Evidence
- Reinforcement learning is terrible. — It applies a single bit of reward information across a long, complex trajectory, making it noisy and sample-inefficient. `[his frame]` `[00:00]`
- We're not building animals, we're building ghosts. — AI systems are disembodied, digital entities trained by imitating human data, unlike animals which are shaped by evolution and have innate hardware. `[his frame]` `[00:17]`
- AI will not create a discontinuous jump in GDP growth but will continue the existing exponential trend. — History shows other transformative technologies (computers, internet) were absorbed into the existing growth curve without creating a visible spike. `[his bet]` `[84:48]`
- The ideal AI would have less memory to force it to generalize and reason, making its poor memorization a feature, not a bug. — Humans' inability to perfectly memorize forces abstraction and pattern-matching, whereas LLMs are distracted by their vast, verbatim memory. `[his bet]` `[57:34]`
- Coding agents are currently not net-useful for novel, architecturally precise projects. — Personal experience building NanoChat showed models misunderstand custom context, introduce boilerplate, and use deprecated APIs. `[his bet]` `[35:42]`

**What doesn't transfer:** His specific timeline ('decade of agents') and model size predictions (billion-parameter core) are bets; the underlying mechanisms he identifies (RL's credit assignment problem, model collapse, the need for better data) are durable.

## Open Questions
- How can we implement effective process-based supervision without the LLM 'judge' being susceptible to adversarial examples? `[47:49]`
- How can we generate diverse synthetic data for training without succumbing to the 'model collapse' where outputs lack variety? `[53:40]`
- What is the optimal size for a 'cognitive core' that is stripped of most factual knowledge but retains its reasoning abilities? `[61:24]`
- How can we create an equivalent of human sleep for LLMs—a distillation phase to consolidate learning from a daily 'context window' into weights? `[23:59]`
- Can we develop methods to explicitly train for and maintain entropy in model outputs to counteract collapse and improve creativity? `[59:21]`

## Takeaways
- To truly understand a complex system, you must build it from scratch. Relying on high-level summaries or tools will leave you with crucial knowledge gaps. `[30:25]`
- Be skeptical of hype cycles. Building robust, general AI agents is a multi-year research and engineering challenge, not something that will be solved in a single 'year of the agent'. `[01:14]`
- Use coding agents as tools for specific tasks: generating boilerplate, working in an unfamiliar language, or handling common patterns. For novel or architecturally sensitive work, they can be more hindrance than help. `[32:13]`
- Recognize that current AI learns differently from humans. It's an imitation-based 'ghost,' not an evolved 'animal,' so direct biological analogies can be misleading. `[10:32]`

## Transfer Questions
- What is the 'crappy evolution' for our robot? Is it pre-training in a simulator, and what crucial real-world physics or interactions is that simulation failing to capture?  *(from: Analogy)* `[14:09]`
- Are we trying to build the full robotic agent too early? What is the 'language model' equivalent we need to build first—a robust world model, a foundational motor control system—before we can tackle complex, long-horizon tasks?  *(from: Sequencing)* `[08:46]`
- Where are we 'sucking supervision through a straw' in our robotics training? Is it a single 'task success' signal at the end of a long manipulation sequence, and how could we provide denser, process-based feedback at each step?  *(from: Mechanism)* `[43:47]`
- What perceived limitation of our current robots, like noisy sensors or imprecise actuators, could actually be a 'feature, not a bug'? Could it force the system to learn more robust, generalizable policies instead of overfitting to perfect conditions?  *(from: Inversion)* `[57:34]`
- Are we trying to build a biological 'animal' or a digital 'ghost'? Does our robot need to replicate the messy, evolved heuristics of a biological creature, or can we build a more alien but effective intelligence that leverages its digital nature (e.g., perfect memory, fast computation)?  *(from: Distinction)* `[10:42]`

## Field Implications — Where to Steer
- Researchers should pivot from purely outcome-based RL to developing robust methods for process-based supervision and reflective learning. `[45:27]`
- Practitioners need to develop skills in data curation and cleaning, as improving the quality of pre-training data is a major low-hanging fruit for better models. `[65:00]`
- The field needs to develop techniques to separate a model's reasoning 'cognitive core' from its rote memorization, potentially leading to smaller, more general, and less biased systems. `[16:17]`
- Engineers should focus on building the infrastructure for AI interaction beyond text, such as visual 'diffs' for graphical interfaces, to unlock agent capabilities in non-coding domains. `[76:55]`

## Industry Outlook — Fading vs Thriving
**📉 Fading**
- The paradigm of reinforcement learning on games with sparse rewards as a direct path to AGI. `[05:53]`
- The belief in a single, imminent 'year of the agent' breakthrough, replaced by a longer-term, decade-long view. `[01:20]`
- Training ever-larger models on raw, unfiltered internet data, as focus shifts to data quality and distillation. `[62:14]`

**📈 Thriving**
- Agentic systems built on top of powerful, pre-trained language models. `[07:36]`
- Research into more data-efficient learning algorithms like process-based supervision and reflection. `[45:18]`
- Data-centric AI approaches that focus on curating and refining high-quality training sets. `[62:46]`
- Smaller, distilled models that are more efficient and specialized, rather than a singular focus on scaling up parameter counts. `[60:08]`

## Speakers
- **A** — AI Researcher `00:00→92:02`
- **B** — Interviewer `00:00→92:02`

## References & Resources Mentioned
- AlexNet `[04:45]`
- Atari deep reinforcement learning (2013) `[05:18]`
- OpenAI Universe project `[06:59]`
- InstructGPT paper `[44:36]`
- Yann LeCun's 1989 convolutional network paper `[25:44]`
- NanoChat repository `[29:16]`
- DeepSeek V3.2 (sparse attention) `[24:59]`
- https://dwarkesh.substack.com/p/andrej-karpathy  *(from video description)*
- https://podcasts.apple.com/us/podcast/andrej-karpathy-agi-is-still-a-decade-away/id1516093381?i=1000732326311  *(from video description)*
- https://open.spotify.com/episode/3iIYVmmhXwh3fOumypWVpC?si=33d37708b2b44e2f  *(from video description)*
- https://labelbox.com/dwarkesh  *(from video description)*
- https://mercury.com  *(from video description)*
- https://gemini.google  *(from video description)*
- https://dwarkesh.com/advertise  *(from video description)*
