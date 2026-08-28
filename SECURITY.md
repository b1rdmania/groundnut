# Security policy

Groundnut processes evidence and can be embedded in consequential workflows.

## Current posture

Groundnut is **security work in progress**. It has not completed or passed a
comprehensive security review. Current live-acquisition controls restrict URI
schemes and public destinations, revalidate redirects, and bound encoded,
decoded and extracted content. The default transport binds connections to
validated addresses, and PDF parsing runs in a separately resource-limited
worker. These new controls have not yet received the independent security review
required for a stronger posture claim. Privileged injected transports remain
outside the default connection guarantee, and operating-system enforcement
details remain part of the review surface. See the
[acquisition and locator hardening plan](./docs/plans/security-hardening-plan-v1.md).

Do not describe a release as secure, security-approved or comprehensively
audited solely because its conformance suite passes.

## Reporting

Report a vulnerability through the private vulnerability reporting of GitHub,
not through a public issue:

https://github.com/b1rdmania/groundnut/security/advisories/new

Include the affected revision, a minimal synthetic reproduction, the expected
impact, and a suggested mitigation. Do not include credentials, private
source material, or protected evaluation data.

The current development branch is supported. Historical research snapshots and
downstream consumer integrations are not separate supported products.
