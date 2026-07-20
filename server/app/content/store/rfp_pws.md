# Performance Work Statement (PWS)

## Solicitation 47QF-CM-2026-0042: Case Management System Modernization

**Issuing agency:** Bureau of Benefits Administration (BBA)
**Contract type:** Firm-Fixed-Price with a 12-month base period and two 12-month option periods.
**Incumbent:** Meridian Systems Group, whose current contract expires 2026-12-31.

### 1. Background

BBA adjudicates roughly 1.2 million benefits cases per year through the Legacy
Case System (LCS), a mainframe application first fielded in 2004. LCS runs on
COBOL batch jobs with a thick-client front end. It cannot support the agency's
statutory move to a fully electronic case file by the end of the second option
period. This effort modernizes LCS into a web-based Case Management System (CMS)
without interrupting daily adjudication work.

### 2. Scope

The contractor shall design, build, migrate to, and operate the modernized CMS.
Work is limited to the CMS and its direct integrations. Modernization of the
separate Payments Engine or the public-facing Benefits Portal is explicitly out
of scope and shall not be performed under this contract.

### 3. Requirements

#### 3.1 Architecture and modernization

- The CMS shall be a cloud-native web application deployed in a FedRAMP-authorized
  environment. On-premises hosting is not acceptable.
- The contractor shall migrate 18 years of case data (approximately 42 million
  records) from LCS into the CMS with zero data loss and a documented reconciliation.
- The CMS shall expose a documented REST API for the three downstream systems that
  read case status today: the Payments Engine, the Benefits Portal, and the
  agency data warehouse.
- The contractor shall retire LCS only after 60 consecutive days of parallel
  operation with reconciled outputs.

#### 3.2 Key personnel

The following are designated key personnel. Each requires agency approval before
substitution:

- **Program Manager (PM).** Minimum 10 years managing federal software programs,
  including at least one system of comparable size (1M+ transactions per year).
  PMP certification required.
- **Lead Solutions Architect.** Minimum 8 years designing cloud-native systems;
  demonstrated experience migrating a legacy system of record.
- **Migration Lead.** Minimum 5 years in large-scale data migration.

Proposed key personnel shall meet or exceed the stated labor-category
qualifications. Substituting staff who do not meet these minimums is grounds for
rejection.

#### 3.3 Transition

- The contractor shall submit a Transition-In Plan within 10 business days of award.
- Transition-in from the incumbent shall complete within 90 calendar days of award.
- The contractor shall provide a Transition-Out Plan at least 90 days before the
  end of the final performance period.

#### 3.4 Security and ATO

- The CMS processes Controlled Unclassified Information (CUI) and Personally
  Identifiable Information (PII). It shall meet the NIST SP 800-53 moderate
  baseline.
- The contractor shall obtain an Authority to Operate (ATO) before processing any
  production case data. The government estimates 120 days for the ATO package review.
- The hosting environment shall hold, at minimum, a FedRAMP Moderate authorization.

#### 3.5 Operations and support

- After go-live, the contractor shall operate the CMS with 99.5% monthly
  availability during the 6am-8pm Eastern core hours.
- The contractor shall staff a help desk responding to Severity-1 incidents within
  30 minutes and resolving them within 4 hours.
- End-user training shall be delivered before cutover for all 2,400 adjudicators.

### 4. Pricing scope

Prices are firm-fixed for the base and each option period. The government will not
entertain price adjustments for work inside this PWS. Any proposed work outside the
scope in Section 2 shall be treated as non-responsive.
