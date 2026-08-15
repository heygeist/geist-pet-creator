# Maintainer evidence

Release evidence belongs here rather than inside the installed skill. Publish
only sanitized measurements made with original or explicitly authorized
fixtures. Do not commit private bundle paths, user prompts, provider keys, or
third-party character art.

For a release candidate, record:

- date, commit, platform, Python, and Node versions;
- mocked-provider CI results;
- one manually approved, cost-capped provider smoke test;
- clean install, validate, export, and uninstall results;
- known limitations and what the measurement does not prove.

Historical raw measurements that contained private local paths or
franchise-derived fixtures were intentionally removed from the distributable
tree before the open-source beta.
