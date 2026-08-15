# Contributing

Issues and pull requests are welcome. This is a maintainer-led project and has no
response-time SLA.

## Before opening a pull request

1. Keep changes focused and explain the user-visible behavior.
2. Add or update tests for behavior changes.
3. Run `python3 scripts/check_repository.py` and the test commands from the pull
   request template.
4. Include source, license, and provenance for every artwork contribution.
   Generated binary-only artwork is not accepted.
5. Never commit API keys, Pet bundles containing keys, or provider responses that
   expose private prompts or user references.

Changes to the Pet source contract, approval gates, security model, cost limits,
or public command behavior require maintainer approval and a short RFC in the
pull request description. Backward-compatible fixes do not need a separate RFC.

## Developer Certificate of Origin

Every commit must include a `Signed-off-by` line certifying the
[Developer Certificate of Origin 1.1](https://developercertificate.org/):

```bash
git commit --signoff
```

By contributing, you agree that your contribution is licensed under the same
terms as the file being changed. Artwork requires its own explicit license.
