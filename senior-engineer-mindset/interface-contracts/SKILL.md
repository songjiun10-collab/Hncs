---
name: interface-contracts
description: Design public interfaces so that observable behavior becomes an implicit promise — Hyrum's Law and contract-first API design. Use when designing REST/GraphQL endpoints, module boundaries, type contracts between files, component props, or any surface where one piece of code talks to another. Complements design-for-the-next-reader with a sharper focus on what you're accidentally promising.
---

# Interface contracts

## Hyrum's Law

> With a sufficient number of API consumers, it does not matter what you promise in the contract — **all observable behavior** of your system will be depended on by somebody.

Undocumented quirks, exact error message wording, ordering, even timing — **everything visible becomes a de facto contract.** What that means in practice:

- Be **deliberate** about what you expose. Every observable behavior is a potential promise.
- Don't let implementation details leak. If it's visible, someone will depend on it.
- Anything that's hard to remove later — plan to remove it (or never expose it) **at design time.**
- Passing tests isn't the same as safe. Even a perfect contract test suite doesn't stop a "safe" change from breaking a consumer who depended on undocumented behavior.
- Principal angle: this is exactly how cross-team blast radius happens — a field, an ordering, or an error string never meant as a promise gets consumed by another team's service, and now your "internal" change is their incident.
- Concrete case (Hncs): every `apply_*` in `brands/*.py` shares one signature — BGR `np.ndarray` in, same-shape out, image first, every other arg defaulted. Nobody wrote that down as an API spec, but `tools/video_engine.py` and `hybrid_engine/` both call any `apply_*` interchangeably on that assumption — that's Hyrum's Law happening in a two-person codebase, not just a big-company thing. The two real deviations (`apply_acros`/`apply_monochrome` in `fuji.py` return a 2D single-channel array, not 3-channel BGR) aren't hidden — they're made an explicit, documented exception and pinned by a golden test, so the deviation can't silently regress back into "looks like every other `apply_*`."

## Define the interface first

Write the contract before the implementation. The contract is the spec; the implementation just satisfies it.

- Write function signatures, input/output types, and what each method guarantees (idempotency, partial updates, failure behavior) before the code
- Spell out error cases explicitly: what happens on a missing resource? Invalid input? How is partial failure represented?
- Write the call site for this contract from the caller's point of view first — is it pleasant to use?

## One-version rule

Never make consumers choose between multiple versions of the same dependency or API. Different consumers wanting different versions creates a diamond-dependency problem. Always design for a world where exactly one version exists — extend it, don't fork it.

## Checklist

- Does this interface expose anything that could **unintentionally** become a promise? (error message wording, return ordering, internal type names)
- If you must deviate from an established contract (like `apply_monochrome`'s 2D return), is the deviation documented and pinned by a test — or just quietly different and waiting to break the next caller who assumes uniformity?
- How painful would it be to change this later? If it's painful, design more carefully now.
- Is the shape and ownership of data crossing this boundary clear? Is it hard to misuse?
- Does this change break an existing consumer's **undocumented** observed behavior? Ask this regardless of whether the tests pass.
- Principal angle: for a widely-consumed interface, a breaking change isn't just a code diff — it's a migration you're imposing on every team downstream. Weigh a deprecation window and a communicated migration path as part of the design, not as cleanup after the fact.
- Distinguished/Fellow angle: if this becomes the pattern every service in the company copies, the real question is whether other teams can operate it correctly five years out without you personally there to explain the edge cases.
- Executive angle (CTO/VP-Eng): a promise baked into a public interface is a standing support and liability cost — weigh what it takes to keep honoring it (or the customer/contractual fallout of breaking it) against the convenience of shipping it now.
