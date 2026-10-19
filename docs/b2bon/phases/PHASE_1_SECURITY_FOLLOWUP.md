# PHASE 01 — Security follow-up for staging

- Date: 2026-10-19
- Target: `staging` via PR #6
- State: IMPLEMENTED IN PART; NOT CERTIFIED
- Production/master changes: none

## Context

The existing `PHASE_1_COMPLETION.md` already records the original Domain Separation phase as complete. This follow-up addresses additional findings from the 2026-10-19 read-only audit; it does not replace that completion report.

## Changes in this follow-up

1. `site_fetcher.py` validates URL schemes, embedded credentials and destination ports before requests, repeating validation on each redirect.
2. DNS results must be globally routable; special-purpose ranges such as CGNAT and documentation ranges are rejected.
3. Negative tests cover unsafe URL schemes, embedded credentials, non-standard ports, redirects to non-HTTP schemes, and special-purpose IP ranges.
4. `.github/workflows/security.yml` adds secret scanning, Semgrep security analysis, Python dependency auditing, npm high/critical auditing and OSV scanning.
5. The OSV job was corrected to call Google's documented reusable workflow at `google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml@v2.7.0`. The first corrected run successfully executed the scanner and uploaded SARIF, but the reporter step returned failure; this is not a green gate.
6. `SECURITY_BOUNDARIES.md` was reconciled with the current CI and AI Gateway behavior and records residual risks instead of presenting happy-path tests as complete proof.

## Commercial scope freeze — PO instruction, 2026-10-19

The currently published prices at https://b2bon.cyberfort.com.br/planos are the reference values. This work must not change prices, plan values, credit grants, or commercial rules. Continue the already-authorized technical phases without treating a pricing change as a prerequisite. Any commercial value not actually present in the live catalog must not be guessed or invented; this does not block unrelated technical work.

## Validation status

- The first corrected Security Scans run (#8) reported Gitleaks and Semgrep successful.
- The frontend dependency audit still fails: `npm audit --audit-level=high` found high-severity advisories in transitive `brace-expansion` and `source-map-js` dependencies. The lockfile has not yet been safely regenerated and committed, so this remains an open remediation item.
- The corrected OSV scanner ran and uploaded SARIF; its reporter step failed, so the overall OSV gate is not green.
- Python dependency audit and the general CI run were still in progress at the last inspection; no success is claimed for them.
- Tests were not executed locally in this environment.

## Remaining security gates

- **SSRF DNS rebinding:** DNS is checked before the HTTP client resolves/connects independently. IP pinning at the actual socket connection is not yet implemented; the residual risk remains open.
- **Response memory limits:** the response text is sliced after the HTTP client has buffered it. A hard streaming byte cap still needs implementation and tests.
- **Cross-tenant isolation:** the repository's existing route sweep and context fitness tests are documented, but this follow-up did not rerun the full sweep against a live or disposable PostgreSQL instance.
- **AI usage ledger failure:** gateway code logs persistence failure but does not make a provider call reversible. Explicit failure-mode tests and a reliable reconciliation/outbox strategy remain required.
- **Security scanners:** workflow execution is now verified, but dependency findings and the OSV reporter failure must be resolved before declaring the scan gate green.
- **Dependency reproducibility:** Python dependency locking remains open (TD-031).

## Deployment rule

Do not merge this PR to `staging` until the remaining gates have been implemented or explicitly documented as accepted residual risk and the relevant CI has passed. Do not promote to `master` until the user has tested the staged build and explicitly authorizes promotion.
