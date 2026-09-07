<!-- converted from System Requirements Document (1).docx -->

System Requirements Document
























Contents

# Executive Summary
This System Requirements Document defines the initial requirements for a bank-hosted pilot. The platform is designed to integrate workflow automation, data integration, reporting, CRM workflows, dashboards, decision engines, advisory Agentic AI, governance and auditability without replacing existing banking systems.
Based on the response received, the solution should be planned for deployment within Absa infrastructure using standard UAT, Production and Disaster Recovery environments. This document should be treated as a baseline for discussion.


# Business and Technical Context
- Uniplexity AI will not replace bank core systems; the platform will integrate with approved source systems and create an operational intelligence layer.
- The pilot should support one or more agreed use cases such as workflow reporting, merchant intelligence, CRM-driven actions, operational dashboards or digital transaction intelligence.
- The bank will provide standard UAT, Production and DR environments.
- The solution will operate in bank infrastructure and must comply with bank security, access, monitoring and release-management processes.
- Agentic AI will remain advisory unless Absa approves specific tools, data classes and controls.


# Proposed Solution Components




# Environment Requirements

- Environments should be logically separated with separate data, credentials, access permissions and configuration.
- UAT should be sufficiently representative of Production for test validity.
- Deployment to Production should follow Absa change and release management process.
- DR expectations, backup scope, restore procedure, RTO and RPO should be confirmed by Absa.


# Infrastructure and Platform Requirements




# Functional Requirements

# Data Requirements


# Integration Requirements

# Security, Compliance and Audit Requirements


# Non-Functional Requirements




# Initial Sizing Assumptions for Scoping




# Deployment, Monitoring, DR and Support Requirements

# Open Questions for Absa


# Pilot Acceptance Criteria

# Appendices
## Appendix A — Glossary


## Appendix B — Version History
| Item | Description |
| --- | --- |
| Version | 0.1 – Draft for technical review and resource scoping |
| Prepared by | Uniplexity AI |
| Client / environment owner | Absa Bank Zambia |
| Confirmed hosting direction | Bank infrastructure |
| Confirmed environments | Standard UAT, Production and DR environments will be made available |
| Purpose | Provide initial system requirements for environment planning, infrastructure scoping, tooling review, and pilot delivery. |
| Important note | Final sizing and detailed infrastructure requirements must be confirmed after pilot scope, data volumes, integration method and bank platform standards are agreed. |
| Component | Purpose |
| --- | --- |
| Web / Workflow Portal | User interface for workflows, submissions, dashboards, tasks, approvals and operational visibility. |
| Data Integration Layer | Ingest approved datasets from source systems using approved integration methods. |
| Data Validation Layer | Validate completeness, duplicates, schema, mandatory fields and business rules. |
| Curated Data Store | Store pilot data, metrics, workflow events, audit logs and reporting-ready datasets. |
| Workflow Orchestration Engine | Manage submissions, approvals, escalations, SLA tracking, status transitions and exceptions. |
| Decision Engine | Apply configurable rules and thresholds to route work or trigger CRM actions. |
| CRM Integration Layer | Create/update CRM leads, opportunities, cases, tasks or account records where in scope. |
| Reporting | Provide dashboards for executive, operational, risk, sales or merchant/customer intelligence views. |
| Agentic AI Advisory Layer | Provide optional summaries, recommendations, next-best-action suggestions and explanations, subject to bank approval. |
| Governance and Audit Layer | Log user actions, data changes, workflow events, outputs, rule triggers and overrides. |
| Environment | Requirement / Use |
| --- | --- |
| Development | bank-provided dev environment. |
| UAT | Bank-hosted UAT environment for integration testing, user acceptance testing, security validation and business sign-off. |
| Production | Bank-hosted production environment for controlled pilot deployment after UAT and approval. |
| DR | Bank-hosted disaster recovery environment aligned to Absa DR standards. RTO/RPO to be confirmed. |
| Sandbox / Demo | Optional safe demonstration environment using synthetic or masked data only. |
| Area | Requirement / Confirmation Needed |
| --- | --- |
| Application runtime | Confirm preferred hosting pattern: VM, container platform, internal cloud, application server, Kubernetes/OpenShift or another bank-approved runtime. |
| Operating system | Confirm bank standard OS and patching model for application hosting. |
| Database / data store | Confirm approved relational DB, warehouse, lakehouse or reporting database platform for pilot data. |
| File/object storage | Confirm approved storage for extracts, documents, logs, evidence files and temporary staging. |
| Integration services | Confirm approved API gateway, middleware, service bus, ETL/ELT platform or scheduler. |
| AI tooling | Confirm approved AI platforms and permitted data classes before enabling any AI feature. |
| Monitoring | Confirm bank monitoring/logging tools for application health, integrations, dashboards and workflows. |
| Secrets management | Confirm approved vault/secrets management approach for credentials, tokens and keys. |
| --- | --- |
| Backup and restore | Confirm backup tooling, frequency, retention and restore testing approach. |
| ID | Requirement | Description | Priority |
| --- | --- | --- | --- |
| APP-001 | Secure Web Access | Authorised users must access the pilot through bank-approved authentication. | Must Have |
| APP-002 | Role-Based Views | Users should see only the workflows, dashboards and data permitted by role. | Must Have |
| WF-001 | Workflow Capture | System must support digital
capture of selected pilot workflow data. | Must Have |
| WF-002 | Approval Routing | System must support review, approval, return and escalation flows. | Must Have |
| WF-003 | SLA Tracking | System should support due dates, reminders, breaches and escalations. | Should Have |
| WF-004 | Reason Codes | Returned/rejected/exception
items must capture structured reason codes. | Must Have |
| DEC-001 | Rules Engine | Systems must support
configurable rules and thresholds. | Must Have |
| DEC-002 | Action Triggers | Rules should trigger workflow
actions, dashboard flags or CRM actions where in scope. | Should Have |
| CRM-001 | CRM Account Update | System should update CRM fields where pilot scope requires. | Should Have |
| CRM-002 | CRM Action Creation | System should create leads, opportunities, cases or tasks where pilot scope requires. | Should Have |
| RPT-001 | Dashboards | System must provide dashboards for agreed pilot KPIs. | Must Have |
| AUD-001 | Audit Trail | System must log user actions, workflow events, rule triggers and integration events. | Must Have |
| AI-001 | Advisory AI | Optional AI output must be advisory, logged and reviewed
by humans. | Could Have |
| Data Domain | Indicative Data Needed | Notes |
| --- | --- | --- |
| Customer data | Customer ID, segment, relationship owner, status fields | Only if required and approved for pilot use case. |
| Account data | Account ID, account type, status, product linkage, branch/channel linkage | Use only approved fields required for pilot. |
| Transaction data | Transaction amount, date/time, status, channel, customer/merchant ID, optional
IP/device attributes | Used for digital transaction intelligence or merchant/customer insight use cases. |
| Sales / branch data | Daily submissions, performance metrics, targets, product sales, branch/user
mapping | Relevant for branch/sales reporting pilot. |
| Merchant/business data | Business ID, merchant profile, volume, success rate, segment, CRM ownership | Relevant for merchant intelligence and CRM action use cases. |
| Reference data | Branches, products, channels, status codes, reason codes, user/team
mapping | Needed for workflow, rules and dashboard consistency. |
| Audit/workflow data | System-generated events, approvals, comments, escalations, timestamps | Generated by the platform and required for auditability. |
| ID | Requirement | Description | Priority |
| --- | --- | --- | --- |
| INT-001 | Integration method confirmation | Absa to confirm whether integration will use APIs, files, database views, data warehouse feeds, middleware or event streams. | Must Have |
| INT-002 | Source system access | Access to approved pilot source data must be provisioned through bank process. | Must Have |
| INT-003 | Data refresh cadence | Agree daily batch, scheduled refresh, near-real-time or manual upload for pilot. | Must Have |
| INT-004 | Error handling | Integration failures must be logged and visible to support users. | Must Have |
| INT-005 | Data lineage | System should retain source-to-output lineage for pilot datasets, dashboards and actions. | Must Have |
| ID | Requirement | Description | Priority |
| --- | --- | --- | --- |
| SEC-001 | Authentication | Use bank-approved identity
mechanism / SSO where available. | Must Have |
| SEC-002 | RBAC | Apply role-based access control across portals,
dashboards, workflows and admin functions. | Must Have |
| SEC-003 | Least privilege | Users and service accounts should have minimum required permissions. | Must Have |
| SEC-004 | Encryption in transit | All communication must use
bank-approved secure protocols. | Must Have |
| SEC-005 | Encryption at rest | Sensitive stored data should
be encrypted according to bank standards. | Must Have |
| SEC-006 | Audit logging | Logins, data changes, workflow events, CRM actions,
AI outputs and admin actions must be logged. | Must Have |
| SEC-007 | Sensitive data handling | Mask, minimise or restrict
sensitive data in lower environments as required. | Must Have |
| SEC-008 | Retention | Retention period for pilot data and logs to be agreed with
Absa. | Must Have |
| SEC-009 | AI governance | Use only approved AI tools; outputs advisory;
prompts/outputs logged. | Must Have if AI used |
| SEC-010 | Security review | UAT and Production deployment subject to Absa
security review. | Must Have |
| SEC-011 | Secrets management | Credentials and keys must use bank-approved secrets management. | Must Have |
| ID | Area | Requirement / Target |
| --- | --- | --- |
| NFR-001 | Availability | Target to align with Absa pilot application standards; final SLA to be confirmed. |
| NFR-002 | Performance | Typical dashboard/workflow screens should load within acceptable user response times for pilot volumes; target
<5 seconds where feasible. |
| NFR-003 | Scalability | Architecture should support expansion from pilot to additional workflows, data sources and users. |
| NFR-004 | Maintainability | Rules, workflows, dashboards and configuration should be maintainable without major code rewrite. |
| NFR-005 | Usability | Pilot users should complete core tasks with minimal training. |
| NFR-006 | Observability | Application, workflow and integration health should be visible through
logs/monitoring. |
| NFR-007 | Auditability | All key actions and outputs should be traceable. |
| NFR-008 | Portability | Design should be adapted to Absa-approved hosting and tooling standards. |
| --- | --- | --- |
| Area | Initial Assumption / Confirmation Needed |
| --- | --- |
| Pilot users | Estimate 5-10 users |
| Concurrent users | Estimate 1–10 concurrent users. Confirm expected concurrency. |
| Data volume | TBD. Confirm number of records, history period and refreshing cadence. |
| Historical data | Recommended 1–12 months for pilot depending on use case. |
| Dashboards | Initial 3–6 dashboards: executive, operations, sales/merchant, risk, data quality. |
| Workflow volume | TBD. Confirm expected daily/weekly submissions, cases or tasks. |
| CRM actions | TBD. Confirm expected daily/weekly leads, opportunities, tasks or cases. |
| AI usage | TBD. Confirm approved platform, users, agent types and prompt limits if used. |
| Area | Requirement |
| --- | --- |
| Release process | Deployments to UAT/Production must follow Absa change and release process. |
| Deployment package | Provide application package, configuration, database scripts, integration settings, environment variables and release notes. |
| Rollback | Each deployment should include rollback steps. |
| Monitoring | Monitor application health, integration failures, dashboard refresh, workflow queues and SLA breaches. |
| Support model | Define support contacts, severity levels, incident process and escalation route. |
| Backup | Backup application configuration, database, rules, logs,
dashboards and critical pilot data as required. |
| DR | DR environment, restore procedure, RTO/RPO and continuity workaround to be agreed with Absa. |
| Production readiness | UAT sign-off, security approval, support model, monitoring and rollback plan required before Production pilot. |
| ID | Question |
| --- | --- |
| Q-001 | Will a separate Development environment be provided, or should development happen in Uniplexity environment using synthetic data only? |
| Q-002 | What is the preferred hosting pattern: VM, container platform, internal cloud, app server or other? |
| Q-003 | Which database/data store is approved for pilot applications? |
| Q-004 | What authentication/SSO approach should be used? |
| Q-005 | Which source systems and datasets can be provided for the initial pilot? |
| Q-006 | What data classification applies to the selected datasets? |
| Q-007 | What security review artefacts are required before UAT and Production? |
| Q-008 | What RTO/RPO targets apply to the pilot? |
| Q-009 | What monitoring/logging tools should the solution integrate with? |
| ID | Acceptance Criterion |
| --- | --- |
| AC-001 | UAT environment configured and accessible to authorised users. |
| AC-002 | Approved pilot data ingested and validated. |
| AC-003 | Workflow module supports agreed pilot workflow and status tracking. |
| AC-004 | Decision rules execute agreed action/routing logic. |
| AC-005 | Dashboards display agreed KPIs and pass business validation. |
| AC-006 | CRM actions work correctly where CRM integration is in scope. |
| AC-007 | RBAC, audit logging and security controls validated. |
| AC-008 | AI outputs are advisory, logged and reviewed if AI is included. |
| AC-009 | Deployment follows Absa change/release process. |
| AC-010 | Business impact and lessons learned documented for rollout decision. |
| Term | Definition |
| --- | --- |
| SRD | System Requirements Document. |
| UAT | User Acceptance Testing environment. |
| DR | Disaster Recovery environment. |
| RBAC | Role-Based Access Control. |
| CRM | Customer Relationship Management system. |
| ETL/ELT | Data extraction and transformation methods. |
| RTO | Recovery Time Objective. |
| RPO | Recovery Point Objective. |
| Agentic AI | Advisory AI agents that summarise, recommend, explain or monitor. |
| Decision Engine | Rules layer that routes actions based on business logic. |
| Data Lineage | Traceability from source data to output reports and actions. |
| Version | Description | Status | Author | Date |
| --- | --- | --- | --- | --- |
| 0.1 | Initial SRD prepared for Absa environment and tooling review. | Draft | Uniplexity AI | 02 Jul 2026 |