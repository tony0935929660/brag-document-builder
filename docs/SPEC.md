# Brag Document Builder Specification

## 1. Status

This document records the product decisions confirmed during requirements discovery.
It defines the first-version product scope and does not define an implementation plan.

## 2. Product Summary

Brag Document Builder is a single-user, local-first CLI tool for continuously collecting work activity, identifying material worth retaining, strengthening it with evidence, and turning confirmed achievements into reusable career content.

The product is intended to solve these problems, in priority order:

1. Work is forgotten before it is recorded.
2. It is unclear which work is worth retaining.
3. Raw activity is difficult to express as persuasive outcomes.
4. Resume and performance-review material must repeatedly be reconstructed from scratch.

Markdown files stored in an Obsidian vault are the authoritative source for achievement content.

## 3. Target User and Operating Model

- The first version serves one user.
- The product runs locally and is accessed through an independent CLI.
- The CLI uses explicit subcommands rather than a single menu-driven session.
- The user starts all collection and review operations manually.
- The first version does not provide scheduled reminders.

## 4. Product Goals

The product must:

- Make it possible to submit small, incomplete descriptions of current work with low friction.
- Preserve every raw input even when AI processing is unavailable.
- Explain why an activity may be worth retaining.
- Distinguish confirmed facts from generated wording.
- Help the user identify missing impact, evidence, scope, and contribution details.
- Accumulate achievements over time without requiring a separate achievement database.
- Generate STAR stories, resume bullets, and performance-review summaries from confirmed facts.
- Produce Markdown that can be managed directly in Obsidian.
- Give immediate value after confirmation by showing applicable resume themes, missing evidence, and the strongest current achievement statement.

## 5. Non-Goals for the First Version

The first version will not include:

- Automatic anonymization.
- Git commit-history ingestion.
- GitHub API integration.
- Voice input.
- A web UI.
- An Obsidian plugin.
- Scheduled reminders.
- Charts, timelines, skill-distribution visualizations, or other statistical dashboards.
- Multiple implemented AI providers.
- Job-specific or role-specific output optimization.
- Saved output profiles.

## 6. Core Workflow

### 6.1 Capture

The user can submit work through:

- Free-form text.
- Answers to fixed questions.
- Changelog content imported from registered local repositories.

Every submission is written to a daily Markdown inbox before AI analysis. Capture must succeed without network or AI availability.

### 6.2 Cloud-Processing Confirmation

Before content is sent to the cloud AI provider, the CLI must:

1. Display the exact content that will be transmitted.
2. Warn the user to check for confidential or sensitive information.
3. Require explicit confirmation for that transmission.

The first version does not anonymize content automatically. The user is responsible for approving only content that is safe to send.

### 6.3 Analysis and Grouping

The AI analyzes raw input and groups related activity by project or topic before proposing achievement candidates.

Input may become:

- A new achievement candidate.
- Supporting evidence for an existing achievement.
- Raw activity that may become valuable later.

All of these categories are retained. The system must not discard an activity merely because its value is not yet clear.

### 6.4 Value Assessment

The system evaluates each candidate across these dimensions:

- Impact.
- Difficulty.
- Leadership or ownership.
- Evidence strength.
- Reusability in future career material.

It also provides a concise explanation of why the item may be worth retaining.

Relevant sources of value include:

- Quantifiable business or technical impact.
- Solving a difficult problem.
- Leading, collaborating, or influencing others.
- Improving efficiency, quality, reliability, or security.
- Learning a new capability before measurable impact is available.
- Routine delivery that may later accumulate into a larger result.
- Positive feedback from managers, colleagues, or customers.

### 6.5 Follow-Up Questions

When information is insufficient, the system marks the item as needing detail instead of presenting unsupported wording as fact.

The user can choose between:

- Quick capture, which defers follow-up.
- Immediate review, which asks follow-up questions now.

An immediate review asks at most three questions at a time. Questions may be skipped, and unresolved questions remain available for a later review.

Follow-up questions may seek:

- Context or problem background.
- The user's specific action and contribution.
- Scope or affected audience.
- Difficulty or constraints.
- Outcomes and impact.
- Supporting evidence.

### 6.6 Confirmation

The user remains the decision-maker. Confirmation occurs in stages for:

1. Grouping and splitting.
2. Whether an item is worth retaining.
3. Individual facts.
4. Generated wording.

The system cannot silently convert an inference into a confirmed fact.

### 6.7 Create or Update an Achievement

After confirmation, the system either:

- Creates a new achievement file.
- Suggests attaching the new material to an existing achievement.

The system may recommend a merge but cannot perform one without confirmation.

When potential duplicates or conflicting facts are found, the system displays the relevant sources and differences. The user chooses whether to merge, create a separate achievement, or ignore the material.

### 6.8 Immediate Feedback

After an achievement is confirmed, the CLI displays:

- Resume themes the achievement can support.
- Evidence that is still missing.
- The strongest currently supported achievement statement.

### 6.9 Generate Outputs

The first version generates:

- A STAR story.
- A resume bullet.
- A performance-review summary.

Outputs are generic rather than tailored to a target job, seniority level, industry, or saved profile.

Original input retains its original language. Structured achievement content defaults to Chinese. Resume and professional outputs can be generated in Chinese or English from the same confirmed facts.

If a metric is missing, generated text may contain a clearly marked placeholder such as `[X%]`. The system must not present an estimate or inference as a confirmed result.

## 7. Achievement Lifecycle

Each achievement supports these states:

- `inbox`: not yet analyzed.
- `needs-detail`: missing information or evidence.
- `candidate`: worth retaining and awaiting confirmation.
- `confirmed`: facts have been confirmed by the user.
- `archived`: retained but no longer actively used.

Rejected material is retained sufficiently to prevent the system from repeatedly proposing the same item. A rejection record contains the original source reference and rejection reason; generated wording does not need to be retained.

## 8. Markdown as the Source of Truth

### 8.1 Authority

- Markdown is the sole authoritative store for raw inputs, confirmed achievement facts, and generated achievement content.
- There is no separate achievement database.
- Direct user edits made in Obsidian take precedence.
- AI may propose changes to confirmed facts but cannot overwrite them.
- AI-generated sections may be regenerated.

### 8.2 Vault Layout

The product uses this layout within the configured Obsidian vault:

```text
Brag/
  Inbox/
  Achievements/
  Archive/
    Rejected/
  Outputs/
```

### 8.3 Achievement File Structure

Each achievement is stored in its own Markdown file and contains three conceptual layers:

1. YAML frontmatter for structured metadata.
2. Confirmed facts and source material.
3. Generated wording.

The frontmatter supports:

- An immutable achievement ID.
- Lifecycle state.
- Date or period.
- Company and role.
- Project.
- Skills.
- Collaborators.
- Source references.
- Affected audience.
- Value assessment.
- AI provider, model, and generation time for generated content.

Date or period and source references are required. Other contextual fields are optional so capture remains low friction.

Confirmed facts include:

- Context.
- The user's actions and contribution.
- Results.
- Evidence.

Generated STAR stories, resume bullets, and performance summaries are separated from confirmed facts. Generated content records its generation time and language so stale wording can be identified after facts change.

The immutable ID, rather than the file name or path, identifies an achievement after a user renames or moves its file.

### 8.4 Output Files

An individual achievement file stores its own generated variants. The product can also create aggregate documents in `Outputs/` using multiple confirmed achievements.

### 8.5 Local Operational State

The CLI may store rebuildable operational data outside the vault, including:

- The default vault path.
- Registered repository paths.
- Configured Changelog paths.
- Source-content hashes.
- Processing indexes.

Operational state must not contain achievement content. Deleting it must not destroy authoritative content, and indexes must be rebuildable from Markdown and registered sources.

## 9. Repository and Changelog Ingestion

### 9.1 Registration

The user maintains an explicit list of registered local repositories. Each registration identifies the repository and its Changelog path.

The product does not discover and scan all repositories beneath a parent directory.

### 9.2 Supported Input

The first version accepts arbitrary Markdown Changelog formats. It preserves the original imported text and uses AI to interpret and group it rather than requiring one fixed Changelog convention.

### 9.3 Initial Import

For the first import from a repository, the user selects a date range, version range, or section range. The product does not automatically submit the entire history.

### 9.4 Incremental Processing

The product hashes source sections to avoid repeatedly processing unchanged content.

If an imported Changelog section later changes, the product:

1. Updates the retained source material.
2. Identifies achievement candidates that may be affected.
3. Asks the user to review the differences.

It does not automatically alter confirmed facts.

## 10. AI Integration

- OpenAI API is the only AI provider implemented in the first version.
- The internal design keeps provider-specific integration separate from the product workflow so another provider can be added later.
- The API key is supplied through an environment variable.
- API keys must never appear in Markdown, logs, or error output.
- Achievement files record the provider, model, and generation time, but not the complete prompt or complete API response.
- Before an AI call, the CLI displays the approximate amount of content and enforces a per-request input limit.
- If an AI call fails or is unavailable, capture remains saved in the inbox for later processing.

## 11. Editing and File Safety

- File updates use atomic replacement so an interrupted write cannot leave a partial Markdown file.
- The product must not rely on direct overwriting of the only valid copy.
- Version history is delegated to the user's vault Git or synchronization tooling.
- If YAML or a required section is malformed, the CLI reports the problem and refuses to modify that file.
- The CLI provides repair guidance but does not guess and silently repair malformed authoritative content.

## 12. CLI Capabilities

The CLI provides separate subcommand-driven capabilities for:

- Configuring a default Obsidian vault.
- Registering and managing repositories and Changelog paths.
- Capturing free-form or prompted input.
- Importing selected Changelog content.
- Reviewing inbox items.
- Answering or deferring follow-up questions.
- Confirming, rejecting, merging, or separating candidates.
- Creating and updating achievement files.
- Generating individual and aggregate outputs.

The exact command names and argument syntax are not defined in this specification.

## 13. Success Criteria

The MVP will be evaluated against at least ten safe, realistic examples that include:

- Fragmented work notes.
- Commit or Changelog summaries.
- Clearly valuable achievements.
- Routine work that later accumulates into an achievement.
- Duplicate or conflicting records.

The MVP is successful when:

- No raw input is lost.
- The user accepts at least 80% of the proposed grouping.
- No more than 10% of worthwhile achievements are missed.
- At least 70% of generated wording requires only minor edits.
- Average processing time is no more than five minutes per input.

Avoiding missed achievements is more important than avoiding false positives because the user can reject a false positive, while a missed achievement may be lost permanently.

## 14. Open Questions

The following decisions were intentionally not made and must be resolved before or during implementation planning:

- Implementation language, runtime, and CLI framework.
- The specific OpenAI model used by the first version.
- The exact CLI command names, options, and argument syntax.
- The exact environment-variable name for the OpenAI API key.
- The exact local path and format for rebuildable operational configuration and indexes.
- The exact YAML field names and Markdown section headings.
- The exact human-readable achievement file-naming convention.
- How each value-assessment dimension is represented or scored.
- The numeric per-request input limit and how content size is estimated.
- The ten or more safe acceptance examples and their expected results.

## 15. Deferred Possibilities

The following were discussed as possible later additions but are not commitments:

- Automatic anonymization.
- Local-model processing.
- Additional cloud AI providers.
- Automated Git commit ingestion.
- GitHub, Jira, or calendar integrations.
- Voice capture.
- A web UI or Obsidian plugin.
- Reminder scheduling.
- Saved output profiles and job-specific generation.
- Timeline, skill, or category visualizations.