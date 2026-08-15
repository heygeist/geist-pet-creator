# Changelog

This project follows Semantic Versioning. Beta releases may refine workflow
instructions, but Pet source-contract changes receive explicit migration notes.

## Unreleased — v0.1.0-beta

### Added

- `npx skills` installation from the repository root
- isolated Pillow bootstrap and lifecycle commands
- Quick, Studio, and Full Automation workflow profiles
- privacy, cost-authority, contribution, security, brand, and asset policies
- clean-install tests and macOS/Linux CI matrices

### Changed

- the installable skill moved from `/geist-pet-creator` to
  `/skills/geist-pet-creator`
- Quick now generates one candidate per animation state by default; Studio keeps
  multi-candidate human selection

### Removed

- the brittle local `install.sh`
- franchise-derived example artwork and raw measurements containing private
  local paths

Existing Pet bundles do not need migration; only repository-relative skill paths
and development commands changed.
