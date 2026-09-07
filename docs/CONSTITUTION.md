# Free Frontier Constitution

This document defines the architectural principles that should survive individual releases,
implementation rewrites, provider changes, and tooling trends.

Free Frontier exists to do one job well:

> Expose one stable OpenAI-compatible model interface and transparently route requests across
> eligible zero-marginal-cost model providers.

Everything in the core project should make that job more reliable, safer, simpler, or easier to
operate. Anything else needs a strong reason to exist here.

## 1. Boring is a feature

Free Frontier should be boring infrastructure that disappears once it works.

The ideal user experience is:

```text
install FrFr -> add provider keys -> point client at it -> forget it exists
```

A user should not need to become a Free Frontier operator just to use their existing model
providers reliably.

Prefer straightforward implementations over architecture that exists mainly to look advanced.
Do not add technology for prestige, trend alignment, resume value, or hypothetical scale.

## 2. Do one thing well

Free Frontier is a model-routing proxy, not a platform.

The core owns:

- one OpenAI-compatible client-facing interface
- logical-model abstraction
- route eligibility and ordering
- zero-cost policy enforcement
- request capability matching
- fallback and cooldown behavior
- provider transport integration
- routing observability

The core does not own:

- agent orchestration
- task or repository management
- prompt workflow systems
- agent memory
- IDE workflows
- dashboards
- editor extensions
- general-purpose automation
- unrelated model-development tooling

If a feature does not need to participate in receiving, routing, serving, or safely observing an
LLM request, it probably does not belong in the core.

## 3. FrFr should remain small

Keep the default installation lightweight and understandable.

Prefer:

- one process
- local configuration
- in-memory transient state
- standard-library solutions when they are sufficient
- existing project dependencies before introducing new ones
- direct function calls over internal services
- explicit code over generalized frameworks

Avoid adding:

- sidecar services
- message brokers
- distributed workers
- service meshes
- mandatory databases
- frontend build systems
- Node dependencies
- bundled web assets
- plugin frameworks without demonstrated demand
- internal network hops that can be ordinary function calls

The fact that a technology is lightweight, popular, or technically suitable is not by itself a
reason to add it.

## 4. No speculative infrastructure

Infrastructure must answer a current, demonstrated problem.

Before adding a dependency, service, process, persistence layer, abstraction, or subsystem, the
change must answer all of these questions:

1. What concrete problem exists today?
2. What user-visible or operational failure does the change solve?
3. Why can the existing architecture not solve it cleanly?
4. What is the smallest solution that solves the problem?
5. What new failure modes and maintenance obligations does it introduce?
6. Can it remain optional rather than becoming part of the default runtime?
7. Does the benefit still justify the cost after removing hypothetical future use cases?

If those answers are weak, reject the change for now.

Abstraction should follow pressure. Do not design generalized infrastructure before repeated
real-world cases demonstrate the need for it.

## 5. Persistence is earned, not assumed

Free Frontier should default to transient in-memory operational state.

Cooldowns, recent failures, counters, latency observations, and last-selected-route state do not
currently need to survive process restarts. Forgetting them on restart is acceptable and keeps
the core simpler.

Do not add a database merely because persistence might be useful someday.

SQLite is not banned. Neither are other persistence technologies. But persistence belongs in the
core only when there is a concrete requirement for state to survive restarts and losing that state
causes a meaningful user or routing problem.

If persistence becomes justified:

1. define exactly which state must survive and why
2. prefer the smallest local solution that satisfies the requirement
3. keep persistence optional when practical
4. avoid turning historical analytics into a routing dependency
5. do not introduce an external database service unless a local solution is demonstrably
   insufficient

A database must solve a problem. The existence of data is not itself that problem.

## 6. Presentation stays outside the core

Monitoring data belongs in Free Frontier. Monitoring presentation does not.

The core may expose stable machine-readable interfaces such as:

```text
/health
/status
/routes
```

Future presentation layers should be separate projects or packages that consume those interfaces.
Examples include:

- a web dashboard
- a VS Code extension
- a richer CLI status interface

The core package should not acquire React, frontend assets, editor SDKs, Electron, or other UI
runtime dependencies simply because a companion interface exists.

A dashboard must be able to disappear without changing routing behavior.

## 7. Observability observes

Observability must not become part of route selection correctness.

The routing data plane may emit state, metrics, and events. Observability consumers may read that
information. They must not be required for request routing, fallback, cooldowns, or recovery.

If the dashboard is down, FrFr should keep routing.

If the status API is never opened, FrFr should keep routing.

If no metrics consumer exists, FrFr should keep routing.

## 8. LiteLLM is plumbing, not the product

Free Frontier owns policy. LiteLLM owns provider-specific transport and normalization where it is
useful.

Do not move Free Frontier's product semantics into LiteLLM configuration merely because LiteLLM
can express something similar.

Free Frontier must remain able to define and test its own:

- free-only eligibility
- logical-model behavior
- capability constraints
- fallback policy
- cooldown semantics
- streaming commit boundary
- observability contract

Provider-specific plumbing should stay behind transport boundaries whenever practical.

## 9. Dependencies must pay rent

Every runtime dependency increases install size, supply-chain surface, upgrade work, and potential
failure modes.

A new dependency should provide a clear net reduction in code, complexity, correctness risk, or
maintenance burden.

Do not add a library for functionality that can be implemented clearly and safely with a small
amount of existing code.

Do not reimplement mature provider protocol plumbing that LiteLLM already handles well merely to
reduce the dependency count.

Minimal does not mean ideological. It means every dependency has a job.

## 10. Optimize the hot path, not hypothetical scale

The critical path is:

```text
client -> API -> FrFr routing policy -> provider transport -> upstream model
```

Keep that path short, explicit, and easy to reason about.

Do not introduce queues, persistence, remote coordination, or extra network boundaries into the
request path without measured evidence that they solve a real bottleneck or correctness problem.

Measure before optimizing. Prefer removing work over adding machinery.

## 11. Companion projects compose outward

If the ecosystem grows, Free Frontier core should expose clean interfaces and let other projects
compose around it.

Possible future companions may include a dashboard, VS Code extension, or specialized CLI. Those
projects should depend on the core's public APIs. The core should not depend on them.

The formal repository name remains `free-frontier` unless a real ecosystem makes a rename such as
`free-frontier-core` useful. Do not rename the project preemptively to simulate an ecosystem that
does not yet exist.

## 12. The change admission rule

When reviewing a proposed feature, ask:

> Does this make the one FrFr job materially better without making the core meaningfully harder to
> install, understand, operate, or maintain?

If yes, build the smallest version that works.

If no, keep it out.

When uncertain, do less.

## North star

**One endpoint. Free models. FrFr.**

The best version of Free Frontier is the one users barely have to think about.
