# codebase-gardener
Tool that takes care of the degradation of your codebase, while you just keep agents up and running, developing new features

> Current product truth lives in `docs/`, `GARDENER.md`, and `open-questions-and-clarifying-answers.md`.
> The long specification below is the original seed material and may be superseded by the newer docs.

## Current direction

Codebase Gardener is an autonomous codebase maintenance engineer, built first as a GitHub App for 5-100 engineer teams. It uses deterministic source truth from repository files, a Repowise-based intelligence layer, Repository Entropy Score, hosted gardening sessions, and focused maintenance PRs to prevent codebase degradation.

Start with:

- `docs/00-product-vision.md`
- `docs/04-feature-map.md`
- `docs/09-autonomy-and-automation-rules.md`
- `docs/14-roadmap.md`
- `docs/15-epics-and-tasks.md`
- `docs/16-constitution-and-memory-schema.md`
- `docs/17-entropy-signal-catalog.md`
- `docs/18-technical-architecture.md`
- `docs/19-shared-json-contracts.md`

---

Automatic Codebase Health‑Check & Maintenance System – Specification

Purpose & high‑level scope

* Goal: provide a unified system that continuously assesses the security and health of software projects across code, dependencies, infrastructure and container images.  The system should detect vulnerabilities early, assist in remediation, measure maintainability and complexity, and surface architectural context so that teams can maintain large codebases safely and efficiently.
* Supported assets: first‑party source code, open‑source dependencies, container images (e.g., Docker/Kubernetes workloads), infrastructure‑as‑code (IaC) templates, and Git history.  The system must work across multiple programming languages (tree‑sitter in repowise supports 14 languages ; Snyk’s SCA/SAST tools cover most popular languages ).
* Audience: developers, DevOps/SRE teams and security engineers.  It must integrate with their daily tools (IDEs, Git providers, CI/CD pipelines, container registries)  .

What the system should do

1. Vulnerability & dependency management

* Scan open‑source dependencies using Snyk’s software composition analysis (SCA) engine.  The system should identify known vulnerabilities and license issues in package manifests and transitive dependencies  .  It should highlight vulnerable packages, suggest upgrades/patches and optionally block builds to stop vulnerable versions from reaching production  .
* Provide risk‑based prioritization – Snyk Open Source calculates a risk score that considers severity, reachability, exploit maturity and business context , allowing the system to focus remediation on high‑impact vulnerabilities.
* Automate remediation by creating pull‑requests with the required upgrades/patches and customizable templates .  Continuous monitoring should detect newly disclosed vulnerabilities .

2. Static application security testing (SAST)

* Analyze first‑party code for issues such as SQL injection, cross‑site scripting and insecure authentication logic .  Snyk Code provides developer‑friendly, actionable findings and pre‑validated auto‑fixes  .  Real‑time scanning should occur within IDEs and pull‑requests .
* Fast & accurate scanning: Snyk Code delivers complete automatic scans with ~80 % accurate fixes and real‑time in‑line results .  The system should integrate these scans into CI/CD pipelines and gate merges on critical findings .

3. Container & workload security

* Scan container images to detect vulnerabilities in OS packages and insecure base images .  Provide developer‑ready base image recommendations and automate upgrades .  The system should monitor images continuously and prioritize remediation based on context and exploitability .
* Integrate with registries and Kubernetes: support scanning images stored in registries such as Docker Hub, ECR, ACR, GCR, etc., and monitor Kubernetes workloads for unsafe configurations .  Offer alerts via Slack/Jira/email when new vulnerabilities are discovered .

4. Infrastructure‑as‑code (IaC) security

* Scan IaC files (Terraform, CloudFormation, Kubernetes YAML, Helm charts and ARM templates) to detect misconfigurations such as open ports, insecure security groups or over‑permissive IAM roles .  Snyk IaC embeds scanning within IDE/CLI/SCM/CI/CD workflows  and provides fix suggestions in code .
* Prevent misconfigurations from reaching production by gating CI/CD pipelines on IaC scan results  and enforcing policies based on industry benchmarks and custom OPA rules .

5. Codebase intelligence & maintainability

* Build multi‑layer intelligence using repowise.  It indexes the codebase once and keeps it in sync on every commit .  Five intelligence layers are produced: (1) dependency graph; (2) git history; (3) auto‑generated documentation; (4) architectural decisions; and (5) code health .
* Graph intelligence: tree‑sitter parses files into a two‑tier dependency graph.  It resolves imports, handles aliasing and identifies logical modules via Leiden community detection.  Metrics such as PageRank and betweenness centrality identify the most central and coupled code .
* Git intelligence: convert git history into signals—hotspot files (high churn × complexity), ownership percentages per author, co‑change pairs and significant commit messages.  These signals roll up into contributor profiles, module health scorecards and reviewer suggestions .
* Documentation intelligence: auto‑generate a wiki for each module and file.  Track coverage and freshness with semantic search and confidence scores .
* Decision intelligence: mine architectural decisions from ADR files, CHANGELOGs, PR bodies, code comments and git archaeology.  Record evidence, classify decisions as verified/fuzzy/unverified and maintain a decision graph showing how decisions supersede or refine each other .
* Code health intelligence: compute a 1–10 health score per file using fifteen deterministic biomarkers—McCabe complexity, deep nesting, brain methods, duplication detection, untested hotspots, primitive obsession, developer congestion, knowledge loss, blame‑based function hotspots, code‑age volatility and more .  Ingest coverage reports to light up test‑coverage biomarkers and produce refactoring suggestions .  Snapshots track declining or predicted health trends .
* Dead‑code detection: identify unreachable code with confidence tiers; cross‑repo consumer detection lowers confidence when other repos import the code .
* Risk & blast‑radius analysis: the get_risk tool provides hotspot scores, dependencies, co‑change partners, ownership, test gaps and governance risks .  The dashboard’s risk view shows hotspots, heatmaps, module health, dead code and blast radius .

6. Local dashboard & developer experience

* Web UI: repowise serve starts a local web dashboard with chat, documentation, interactive dependency graph, C4 architecture diagrams, semantic search, symbol index, coverage and risk pages .  Graph view handles >2 000 nodes and provides metrics like PageRank percentiles .
* Contributor & module analytics: dashboards show paginated contributor directories, per‑author profiles, module health rollups, hotspots and bus‑factor risks .
* Security scanning: local regex‑based scans flag dangerous patterns (e.g., eval, exec, pickle.loads, shell=True, hard‑coded secrets, insecure SQL and weak hashes) with severity grouping .  This complements Snyk’s deeper vulnerability analysis.
* Hooks & auto‑sync: pre‑tool and post‑tool hooks enrich search queries with related files and detect stale documentation automatically .  Auto‑sync offers multiple methods—post‑commit hooks, file watchers, GitHub/GitLab webhooks and polling—to keep the intelligence layers updated .

7. Multi‑repository & cross‑project intelligence

* Workspaces: repowise workspaces let the system index multiple repositories and provide cross‑repo co‑change detection, API contract extraction, package dependency mapping and federated queries .  The workspace dashboard aggregates statistics across repos and shows cross‑repo blast radius .

8. Integration & reporting

* Developer integrations: plug into GitHub/GitLab/Bitbucket, IDEs (VS Code, IntelliJ, WebStorm), CI/CD tools (GitHub Actions, Jenkins, GitLab CI), container registries and Kubernetes clusters  .  The system should automatically scan PRs, block merges when critical issues are found and provide inline fix advice  .
* Alerts & notifications: send security alerts and health decline notifications via Slack, Jira, email or other webhooks.  Provide dashboards for vulnerability counts, health scores, trends and remediation status.
* Reporting & governance: generate reports (e.g., SBOMs, compliance reports) and expose APIs for auditing vulnerability history, health trends and architectural decisions.  Snyk supports continuous monitoring and compliance reporting .

What the system should not do

* No black‑box AI for core analysis: repowise’s graph, git, dead‑code and health layers are deterministic and make zero large‑language‑model calls .  The system must avoid hallucinating answers and instead rely on reproducible analyses and verified vulnerability databases.
* No uncontrolled auto‑fixing in production: Snyk suggests automated fixes but does not replace human review; advanced features may require paid plans and large projects may need tuning .  The system must ensure that generated patches or refactoring suggestions are reviewed and tested before being merged.
* Not a replacement for penetration testing: Snyk is not a complete substitute for manual security testing .  The system should complement, not replace, other security practices such as fuzzing or red‑team exercises.
* Do not scan unauthorized code or leak sensitive data: the system must respect licensing and intellectual property.  Scanning should occur within controlled environments and never transmit code to third parties without consent.
* Avoid performance degradation: scanning and indexing should not slow developers’ workflows.  Repowise builds health/graph/git layers in minutes and updates in under 30 seconds ; similar efficiency should be maintained for Snyk scans.
* No scope creep: the system should not manage unrelated aspects like project management, feature development or deployment orchestration; its focus is security and maintainability.

How the system should operate (implementation approach)

* Architecture: build a modular pipeline where each scanner runs as an independent module.  A scheduler triggers scans on events (commit, pull‑request, nightly build) and persists results in a central database.  A service layer aggregates findings and exposes them via APIs and dashboards.
* Setup & indexing: on first run, execute repowise init to build the five intelligence layers and repowise serve to host the MCP server and web UI .  Use Snyk CLI/API to bootstrap vulnerability scanning for dependencies, code, containers and IaC.  For multi‑repo setups, initialize a workspace and index all repositories .
* Continuous updates: install post‑commit hooks or file watchers to trigger incremental updates for repowise and schedule periodic Snyk scans.  Use GitHub/GitLab webhooks for remote repositories .
* Data storage: store graph structures, metrics and vulnerability data in a local database (SQLite/PostgreSQL).  Persist snapshots for health trend analysis and maintain an audit trail of vulnerabilities and fixes.
* Enrich developer workflows: integrate with IDE extensions so that developers see inline vulnerability alerts and health suggestions.  Provide CLI commands (e.g., repowise health, repowise dead-code, repowise get_risk) and Snyk commands to query the current state and run targeted scans  .
* Reporting & dashboards: use repowise’s web UI for deep codebase intelligence; add custom panels for Snyk vulnerability metrics.  Provide export capabilities (JSON, CSV, SBOM) for compliance.
* Security & access control: limit dashboard and API access via authentication and RBAC.  Use encrypted storage and follow least‑privilege principles.

Functional requirements (detailed)

1. Project integration & onboarding
    * Connect to Git repositories (GitHub/GitLab/Bitbucket) and container registries; support multiple repositories in a workspace .
    * Parse codebase with tree‑sitter across at least 14 languages and build a dependency graph .
    * Register Snyk scanning projects for dependency, code, container and IaC scanning  .
2. Automated scanning
    * Run Snyk SCA scans on package manifests and transitive dependencies to detect vulnerabilities and license issues  .
    * Run Snyk Code SAST scans on first‑party code to detect injection, XSS, insecure auth and other vulnerabilities .
    * Run Snyk Container scans on container images; report OS package vulnerabilities, insecure base images and suggest safer alternatives .
    * Run Snyk IaC scans on Terraform/CloudFormation/Kubernetes/Helm/ARM templates to detect misconfigurations and provide fix suggestions  .
    * Run repowise code‑health computation to assign health scores and identify untested hotspots, complexity, duplication and other biomarkers .
    * Run repowise dead‑code detection to identify unreachable code and recommend safe removals .
    * Update intelligence layers and vulnerability databases regularly; monitor for new CVEs and newly added code changes .
3. Analysis & prioritization
    * Calculate risk scores for vulnerabilities based on severity, reachability, exploit maturity and business context .
    * Compute hotspots and churn metrics from git history and highlight files with high change/complexity .
    * Generate contributor profiles and module health scorecards to identify ownership concentrations and bus‑factor risks  .
    * Provide blast‑radius and impact analysis for proposed changes or detected vulnerabilities  .
    * Prioritize issues using combined vulnerability risk and code health metrics.
4. Remediation & automation
    * Generate remediation pull‑requests for vulnerable dependencies and container images with upgrade/patche instructions .
    * Offer in‑IDE fix advice and one‑click refactoring suggestions for code health issues  .
    * Provide API contract extraction and cross‑repo co‑change suggestions to ensure refactoring does not break dependent services .
    * Allow customizable policies (e.g., gating thresholds, allowable CVSS score, allowed health‑score drop) to control PR blocking.
5. Visualization & reporting
    * Expose dashboards summarizing vulnerability counts, health scores, hotspots, dead code, bus‑factor risk and decision graphs .
    * Enable filtering and drilling down (e.g., per file, module, author, repository, vulnerability type).
    * Provide exportable reports and SBOMs for compliance and audits .
6. Notifications & alerts
    * Send alerts when critical vulnerabilities or declining health trends are detected .
    * Notify stakeholders via preferred channels (Slack, Jira, email) when scans fail or require manual intervention .

Non‑functional requirements

* Performance: initial indexing of a repository should complete within minutes (repowise builds graph/git/dead‑code/health layers with zero LLM calls ).  Incremental updates after each commit should complete in under 30 seconds .  Snyk scans should run asynchronously so they don’t block developer workflows.
* Scalability: the system must support large monorepos and workspaces containing multiple repositories.  The graph view should handle at least 2 000 nodes interactively .  Data storage must scale with project size and number of scans.
* Security & privacy: all code and vulnerability data must be stored securely; transmissions to external services (e.g., Snyk API) should be encrypted.  The system must avoid leaking code or secrets and comply with privacy regulations.  Local scans (repowise regex checks) should run offline with no network calls .
* Reliability: scanning processes should be idempotent and recover gracefully from failures.  A retry mechanism should handle transient network errors.  Data corruption or partial indexing must not occur.
* Extensibility: the architecture should allow new languages, vulnerability sources or metrics to be added easily.  Custom policies and rulesets (e.g., OPA for IaC) should be supported .
* Usability: the dashboard must offer an intuitive, developer‑friendly experience with clear navigation.  CLI commands should have sensible defaults and help messages.  Integration setup should be straightforward.
* Modularity & maintainability: each scanner (SCA, SAST, container, IaC, repowise) must be decoupled so it can be updated independently.  Code should be well documented and tested.
* Compliance: generate and maintain SBOMs and vulnerability reports to support regulatory requirements.  Provide license compliance reporting for open‑source dependencies .
* Observability: emit logs and metrics for scan durations, error rates, vulnerability counts and health metrics.  Provide dashboards for operations teams to monitor system health.

⸻

This specification outlines the capabilities, constraints and requirements for an automated codebase health‑check and maintenance system inspired by Snyk’s security tools and repowise’s code‑intelligence platform.  The bullet points above form a concise yet comprehensive reference for subsequent architectural design and implementation planning.
