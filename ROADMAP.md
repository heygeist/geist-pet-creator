# Roadmap

## v0.1 beta — npx-first open source

- Agent Skills layout at `skills/geist-pet-creator/`
- global or project install through `npx skills`
- isolated, pinned Pillow runtime with check/install/repair/remove
- Quick default, Studio opt-in, Full Automation explicit opt-in
- local-only core workflow with external-provider disclosure and spend ceilings
- MIT code/instructions, separate asset and brand terms
- macOS/Linux CI across Python 3.11-3.14 and Node.js 20/22

## v0.2 — native Codex plugin

- add the Codex plugin manifest and validate its schema
- publish through the appropriate Codex plugin distribution path
- keep the standalone skill and `npx` path working
- document migration without changing the Pet source contract

## v1.0 readiness

Do not label the project stable until all of these hold:

- three external users have completed real Pet builds;
- clean install, validate, export, and uninstall pass on macOS and Linux;
- no unresolved data-loss or unexpected-spend defect;
- the Pet source contract has remained compatible across two releases;
- at least two maintainers can review releases and security changes.

The project has no fixed beta release cadence. Releases are cut when the main
branch is green and the release evidence is complete.
