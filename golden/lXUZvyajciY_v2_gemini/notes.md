---
event_id: yt_lXUZvyajciY
date: 2025-10-17
title_inferred: "Andrej Karpathy on the Decade of Agents, Flaws of RL, and the Future of AI"
duration: "146:07"
speakers_detected: 7
languages: [en]
generated: 2026-06-25
profile: lecture
---

# Andrej Karpathy on the Decade of Agents, Flaws of RL, and the Future of AI

## Summary
Andrej Karpathy argues that developing capable AI agents will be a decade-long endeavor, not a single year's project, due to fundamental challenges like continual learning and multimodality. He critiques current reinforcement learning (RL) as a deeply flawed, high-variance method, suggesting the field must move towards more sophisticated, process-based supervision. Karpathy contrasts AI development with biological evolution, positing that we are building digital "ghosts" by imitating internet data, not "animals" with innate hardware. He also discusses the dangers of model collapse from synthetic data, the need to distill a "cognitive core" of intelligence separate from memorized facts, and views AI's rise as a continuation of a centuries-long automation trend rather than a sudden intelligence explosion.

## Operating Algorithm
Observe a system's practical limitations → Frame the problem with a familiar analogy (e.g., biology, history) → Stress-test the analogy to find the breaking point → Isolate the core mechanism revealed by the break → Project future progress based on solving for that mechanism

*Tags: Analogy · Distinction · Mechanism · First-principles*

## Through 4 Expert Lenses
- 👨‍🔬 **ML Researcher** — Karpathy's critique of standard RL as 'sucking supervision through a straw' highlights the severe credit assignment problem. His call for methods beyond outcome-based rewards, like reflection and review, points toward a necessary shift to more human-like, process-based supervision to overcome sparse, noisy reward signals. `[43:47]`
- 💻 **AI Practitioner** — The distinction between autocomplete-style coding assistants and 'vibe coding' agents is crucial. While agents fail on complex, novel tasks like building NanoChat, they excel at boilerplate, suggesting a future where developers act as architects who delegate well-defined tasks but retain control over core logic. `[31:58]`
- 🧠 **Cognitive Scientist** — The analogy of LLMs to 'ghosts' rather than 'animals' is a powerful framing. Karpathy argues that AI, trained via imitation on internet data, follows a different developmental path than evolved biological intelligence, which relies on maturation and has a different relationship with reinforcement learning. `[10:42]`
- 📈 **AI Futurist** — Karpathy's view of AI progress as a continuation of a centuries-long automation trend, rather than a discrete intelligence explosion, is a grounding perspective. His prediction that AI's impact will be absorbed into the existing GDP growth curve challenges narratives of an imminent, sharp economic takeoff. `[83:35]`

## Cognitive Moves
- **Frame AI agents as employees or interns you would hire.** — *Analogy* — Makes the abstract concept of an 'agent' concrete and relatable, anchoring its required capabilities to a familiar human role. `[01:52]`
- **Distinguish between building 'animals' and building 'ghosts'.** — *Distinction* — Prevents over-extension of biological analogies by sharply separating the current AI paradigm (digital, imitation-based) from its biological inspiration (evolved, embodied). `[10:42]`
- **Describe standard RL as 'sucking supervision through a straw'.** — *Mechanism* — Replaces a vague notion of 'RL is inefficient' with a concrete mental model of an information bottleneck, highlighting the problem of sparse, delayed rewards. `[43:47]`
- **Sequence AI history to frame the Atari-era as a premature jump to agents before foundational representations (LLMs) were ready.** — *Sequencing* — Establishes a necessary order of operations for building complex systems, arguing that powerful representations must precede complex agentic behavior. `[05:36]`
- **Separate a model's 'knowledge' from its 'cognitive core'.** — *Distinction* — Reframes the goal of AI development from accumulating facts to isolating and improving the underlying reasoning algorithms, suggesting memory can be a distraction. `[16:17]`
- **Reframe the 'intelligence explosion' not as a future event but as the continuation of a centuries-long trend of automation.** — *Reframe* — Collapses a dramatic, singular future event into a familiar, continuous historical process, lowering the sense of discontinuity and making the future feel more like 'business as usual'. `[83:35]`

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
- Developing truly capable AI agents will be a decade-long endeavor, not something achieved in a single year, due to unsolved problems like continual learning and multimodality. `[01:20]`
- Current reinforcement learning methods are "terrible" because they inefficiently learn from a single reward signal at the end of a long trajectory, a process he calls "sucking supervision through a straw." `[43:47]`
- AI systems are not analogous to animals; they are more like "ghosts" or "ethereal spirit entities" because they are trained by imitating human digital artifacts, not through an evolutionary process. `[10:42]`
- Training LLMs on their own synthetic data leads to "model collapse," where the output distribution loses diversity and richness, a key research problem to solve for continual improvement. `[52:56]`
- The future of AI development should focus on creating a "cognitive core"—the algorithmic part of intelligence—while reducing reliance on rote memorization, which LLMs are currently too good at. `[16:17]`
- The AI revolution is not a discrete event but a continuation of a centuries-long trend of automation; its economic impact will likely be absorbed into the existing exponential growth curve of GDP. `[83:55]`
- Coding is the first and most successful domain for LLM agents because it is text-native and has pre-existing infrastructure (like IDEs and diff tools) that aligns well with how LLMs process information. `[75:02]`

## Methods / Approach
- Pre-training on internet data is described as a "crappy evolution" that provides a starting point with built-in knowledge, analogous to what evolution does for animals. `[14:09]`
- Reinforcement Learning (RL) is critiqued for its high-variance, noisy updates where every action in a successful trajectory is upweighted, regardless of its actual contribution. `[43:13]`
- Process-based supervision is an alternative to outcome-based RL where an agent receives feedback at each step, but is difficult to implement due to the "gameability" of LLM judges. `[47:49]`
- Distillation is a process where knowledge from a larger model is transferred to a smaller one, which will be key to creating smaller, more efficient "cognitive core" models. `[63:03]`
- In-context learning allows a model to learn from examples in its context window, assimilating information at a rate millions of times higher than pre-training. `[15:03]`

## Notable Claims & Evidence
- Reinforcement learning is terrible. It just so happens that everything that we had before is much worse. — RL's credit assignment is extremely noisy, upweighting entire trajectories based on a single outcome. `[consensus]` `[00:02]`
  ↳ *fails when:* This view fails in domains with dense, easily specified rewards and clear state spaces where RL can be superhuman. Many robotics startups have failed by over-relying on sparse-reward RL in complex physical environments.
- We're not actually building animals, we're building ghosts. — AI is trained by imitating digital human artifacts, not through a biological evolutionary process that bakes in hardware and maturation. `[his frame]` `[10:42]`
  ↳ *fails when:* This metaphor breaks down if future systems successfully integrate rich sensory-motor loops and developmental algorithms, becoming more embodied. Proponents of neuromorphic computing or embodied AI would argue this frame is already limiting.
- Humans don't actually use reinforcement learning for complex intelligence tasks like problem solving. — Human intelligence is not based on the simple reward mechanisms of RL; RL in biology is more for motor tasks. `[contested]` `[10:52]`
  ↳ *fails when:* This claim is contested by cognitive scientists who model human skill acquisition and decision-making using RL principles, pointing to dopamine systems as a biological analog for reward signals.
- The focus on RL in games (like Atari) in the mid-2010s was a "misstep" that delayed progress towards agents for real-world knowledge work. — The approach lacked the powerful representations that were later developed through LLM pre-training. `[his bet]` `[05:36]`
  ↳ *fails when:* This is a retrospective take; at the time, it was seen as a breakthrough. The argument fails if the infrastructure and insights from that era were a necessary, albeit indirect, step towards the representational models that followed.
- A highly capable "cognitive core" for an AI could potentially exist in a model of only a billion parameters in the future. — Current large models are bloated with memorized knowledge from noisy internet data; distillation onto cleaner data will enable much smaller models. `[his bet]` `[60:22]`
  ↳ *fails when:* This prediction fails if general intelligence is inextricably linked with vast world knowledge, making a small, separate 'cognitive core' impossible. The 'scaling laws' camp implicitly bets against this by pursuing ever-larger models.

**What doesn't transfer:** His specific predictions on timelines and model sizes are bets; his method of breaking analogies to isolate core mechanisms is the durable part.

## Open Questions
- How can we create a process for AI to "distill" its experiences into its weights, similar to how humans consolidate memories during sleep? `[23:59]`
- How can we solve the problem of "model collapse" when training on synthetic data, maintaining entropy and diversity in the model's outputs? `[53:40]`
- What is the optimal size for a pure "cognitive core" of intelligence, stripped of most memorized knowledge? `[61:24]`
- How can we create reliable, non-gameable methods for process-based supervision to move beyond the limitations of outcome-based RL? `[47:20]`

## Takeaways
- To truly understand AI systems, you must build them from scratch; reading blog posts or watching talks is insufficient. `[30:25]`
- When learning to code a complex system, put the reference code on one monitor and build your own version from scratch on the other, without copy-pasting. `[30:24]`
- Use AI coding agents for boilerplate and common tasks, but rely on your own skills for novel, intellectually intense, or architecturally specific code where agents currently fail. `[32:18]`
- Be skeptical of claims of imminent, super-capable AI agents; the path to building them is a decade-long research and engineering effort with many fundamental problems yet to be solved. `[01:14]`

## Transfer Questions
- What is the closest human role to the robot I'm building (e.g., warehouse picker, lab assistant), and what specific capabilities is my robot missing to fulfill that role?  *(from: Frame AI agents as employees or interns you would hire.)* `[01:52]`
- My robot is not a biological creature. What specific shortcuts can I take because it's a digital system (e.g., perfect memory, direct state access) instead of poorly imitating biology?  *(from: Distinguish between building 'animals' and building 'ghosts'.)* `[10:42]`
- Where in my robot's learning process is the feedback signal most sparse? How can I create denser, more immediate rewards instead of just relying on final task completion?  *(from: Describe standard RL as 'sucking supervision through a straw'.)* `[43:47]`
- What part of my robot's software is the general 'skill' (the cognitive core, e.g., path planning) versus the specific 'knowledge' (the map of this building)? How can I make the core more robust and the knowledge easily swappable?  *(from: Separate a model's 'knowledge' from its 'cognitive core'.)* `[16:17]`
- Instead of just using a pre-existing robotics library, what is the simplest version of the full stack I could build from scratch to truly understand all its failure modes?  *(from: Frame AI agents as employees or interns you would hire.)* `[30:06]`

## Field Implications — Where to Steer
- The field needs to develop new training algorithms beyond standard RL that incorporate reflection, review, and process-based supervision to achieve more robust learning. `[45:27]`
- Researchers should focus on methods to separate a model's "cognitive core" from its memorized knowledge, likely through better distillation and higher-quality, cognitively-focused data. `[16:17]`
- Practitioners need to develop skills in managing an "autonomy slider," creating workflows where humans supervise teams of AIs, delegating rote tasks and handling exceptions. `[71:19]`

## Industry Outlook — Fading vs Thriving
**📉 Fading**
- Relying solely on outcome-based reinforcement learning for complex agentic tasks. `[42:22]`
- The pursuit of ever-larger models for pre-training, shifting focus to data quality, distillation, and post-training enhancements. `[60:08]`
- Using RL on game environments as a primary path to AGI. `[05:53]`

**📈 Thriving**
- AI agents focused on coding, as it's a text-native domain with mature infrastructure. `[75:02]`
- Development of smaller, distilled models focused on cognitive abilities rather than rote memorization. `[63:10]`
- Process-based supervision and methods that allow models to reflect and review their outputs. `[45:18]`
- Human-in-the-loop systems where AI handles the bulk of tasks and humans supervise and manage exceptions. `[71:25]`

## Speakers
- **A** — Andrej Karpathy, AI Researcher `00:00→92:02`
- **B** — Interviewer `00:00→92:02`

## References & Resources Mentioned
- AlexNet `[04:45]`
- Atari deep reinforcement learning (2013) `[05:18]`
- Universe project (OpenAI) `[06:59]`
- NanoChat `[29:16]`
- InstructGPT `[44:36]`
- Yann LeCun's 1989 convolutional network `[25:44]`
- DeepSeek V3.2 `[24:59]`
- https://dwarkesh.substack.com/p/andrej-karpathy  *(from video description)*
- https://podcasts.apple.com/us/podcast/andrej-karpathy-agi-is-still-a-decade-away/id1516093381?i=1000732326311  *(from video description)*
- https://open.spotify.com/episode/3iIYVmmhXwh3fOumypWVpC?si=33d37708b2b44e2f  *(from video description)*
- https://labelbox.com/dwarkesh  *(from video description)*
- https://mercury.com  *(from video description)*
- https://gemini.google  *(from video description)*
- https://dwarkesh.com/advertise  *(from video description)*
