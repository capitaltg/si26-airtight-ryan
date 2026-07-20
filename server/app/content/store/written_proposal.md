# Written Proposal (SYNTHETIC — for evaluation use only)

> **This document is synthetic.** It was authored for the Airtight POC to give the
> evaluation a written record to fact-check answers against. It does not describe a
> real company, contract, or team. Any resemblance to real vendors is coincidental.

**Offeror:** Northwind Digital Services (NDS)
**In response to:** Solicitation 47QF-CM-2026-0042, Case Management System Modernization

## 1. Technical approach

Northwind proposes a cloud-native CMS built on a containerized microservices
architecture, deployed to AWS GovCloud (FedRAMP Moderate authorized). The system
uses a PostgreSQL system of record, an event-driven ingestion pipeline for the LCS
migration, and a React front end. We expose a versioned REST API for the Payments
Engine, Benefits Portal, and data warehouse, matching the three integrations named
in PWS 3.1.

We will migrate the 42 million case records in three waves, oldest-first, with an
automated reconciliation report after each wave. We commit to the 60-day parallel
run before LCS retirement.

## 2. Key personnel

- **Program Manager: Karen Holloway.** 12 years managing federal software programs,
  including the 1.8M-case-per-year modernization at the Veterans Claims Office. PMP
  certified since 2015.
- **Lead Solutions Architect: Samuel Ortiz.** 9 years in cloud-native design; led the
  legacy-mainframe migration for the State of Ohio tax system.
- **Migration Lead: Anil Kapoor.** 7 years in large-scale data migration, including a
  50-million-record financial-services migration.

All three are committed full-time to this effort for the base period.

## 3. Transition

We will deliver the Transition-In Plan within 10 business days of award and complete
transition-in within 90 calendar days, including knowledge transfer from Meridian
Systems Group and shadowing of adjudication workflows.

## 4. Past performance

- **Veterans Claims Office case modernization (2021-2024):** migrated a 1.8M-case
  system to a cloud-native platform, on schedule, with zero data loss. CPARS rating:
  Exceptional.
- **State of Ohio tax-system migration (2019-2021):** re-platformed a COBOL mainframe
  to a web application serving 900 users.

## 5. Cost realism

Our staffing plan is 28 full-time equivalents at steady state. Pricing is firm-fixed
for the base and both option periods, consistent with PWS Section 4. We hold no
assumptions of price adjustment.

## 6. Security and ATO

The CMS meets the NIST SP 800-53 moderate baseline. We host in AWS GovCloud, which
holds a FedRAMP Moderate authorization. We will deliver the ATO package for
government review and will not process production case data before ATO is granted.

## 7. Operations and support

We will meet the 99.5% monthly availability target during core hours and staff a
help desk with a 30-minute Severity-1 response. End-user training for all 2,400
adjudicators will be delivered before cutover.
