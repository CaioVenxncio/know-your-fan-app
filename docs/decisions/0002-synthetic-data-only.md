# ADR 0002: Synthetic-data-only public demo

- **Status:** Accepted (Phase 1; enforcement strengthened in Phase 2)
- **Date:** 2026-10-13

## Context

The original application collected CPF numbers, addresses, and identity-document images. It
stored them in plain text behind a password that was hardcoded and published. A public portfolio demo
should not process real personal data at all. Doing so would create legal (LGPD), ethical, and
security obligations that a demo cannot meet.

## Decision

The public application works **only with synthetic data**:

- There is no registration form, no file upload, and no field for CPF, documents, addresses, or
  passwords.
- Profiles come from a seeded generator. Demo IDs (`KYF-DEMO-XXXX-XXXX`) cannot be mistaken for
  CPF numbers, and links use the reserved `.example` TLD.
- OCR runs only on specimen cards that the app renders itself.
- Since Phase 2, persistence is guarded by an **allowlist** (`synthetic_violations`). Every stored
  value must come from the generator's vocabulary, so even a programming error cannot store free
  text through `SyntheticProfileRepository.add`.
- Text matching is always described as "not identity verification, document authentication, or
  fraud detection".

## Consequences

- No authentication is needed, because nothing private exists.
- UI tests assert that no page contains upload, password, or CPF/RG/CNH/address inputs or
  validity claims.
- The demo cannot show behaviour on real documents. Research on document processing must use
  synthetic or properly licensed data (planned for Phase 4).

## Alternatives considered

- **Accept real data with consent and encryption:** this requires a legal basis, retention
  policies, access control, and incident handling that are disproportionate for a demo. Rejected.
- **A blocklist (reject CPF-shaped strings):** this is incomplete by nature, since addresses and
  names are not detectable by pattern. An allowlist was chosen instead.
