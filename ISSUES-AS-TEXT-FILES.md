# Prompt: Special Rule "Issues as Text Files"

Provide this prompt to the LLM once at the beginning so that the convention applies throughout the entire session.

This replaces real GitHub Issues with version-controlled text files in the repository.

## Prompt (ready to copy)

We are working on this project without GitHub Issues. Create Issues as text files instead and follow this convention strictly:

- One Issue equals one file under `src/docs/issues/`, named `issue-<NNNN>-<slug>.adoc` (a consecutive four-digit number, with the title converted to a lowercase slug).
- Each Issue file contains: ID, title, type (EPIC/Story/Bug), status (open/in-progress/closed), priority (MoSCoW), related Use Case and BR IDs, description, acceptance criteria (Gherkin), and dependencies (IDs of other Issues).
- For new work, create the Issue file first, then implement it. Reference the Issue ID in the code and tests.
- When an Issue is complete (all acceptance criteria are green), set its status to `closed` and move the file to `src/docs/issues/closed/`.
- `src/docs/issues/` therefore contains only open Issues, while `src/docs/issues/closed/` contains the archive of completed Issues.

Confirm the convention briefly and create the `src/docs/issues/` directory before we start with the first Issue.

## Issue File Template (Reference)

```asciidoc
= Issue 0001: Checkout an Item
:issue-id: 0001
:type: Story
:status: open
:priority: Must
:refs: UC-Checkout, BR-003, BR-004
== Description
An eligible member borrows an available item. A deposit is collected.
== Acceptance Criteria
[source,gherkin]
----
Given an available item and an eligible member
When the member borrows the item
Then the loan is created and the deposit is collected
----
== Dependencies
- 0000 (Catalog Management)
```
