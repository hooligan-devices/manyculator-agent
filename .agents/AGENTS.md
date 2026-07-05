# Agent Guidelines for This Project

This project consists of multiple components, each residing in its own folder. These components interact with each other but are developed separately. 

When working on this project, you MUST follow the **Common Development Workflow** for any task, and strictly adhere to the **Rules & Guidelines**.

---

## Part 1: Common Development Workflow

For *every* development task (feature, bugfix, or refactor), you must follow this exact sequence:

### Step 1: Understand & Plan
- Read the component's `specs/README.md` to understand the current architecture and data models.
- If the task is complex, write an implementation plan and wait for user approval before coding.
- *Rule Check:* If the task requires editing a different component than the one you are assigned to, STOP and ask the user for authorization.

### Step 2: Implement Incrementally
- Write code in small, verifiable steps.
- Do not attempt massive rewrites all at once.

### Step 3: Write / Update Tests
- You MUST create, update, or modify relevant deterministic tests (Unit/Integration) to comprehensively cover the code you just wrote or changed.

### Step 4: Run Tests & Verify
- Automatically run the deterministic tests (Unit/Integration) after your changes.
- If tests fail, use log-driven debugging (add debug logs, read output) to investigate scientifically. Do not guess blindly.
- Continue fixing the code until the test suite passes completely.
- *Note:* Do NOT run non-deterministic tests (e.g., `agents-cli eval`) automatically. These are by user request only.

### Step 5: Update Live Documentation
- You MUST immediately update `specs/README.md` to reflect your changes.
- Append a new Architectural Decision Record (ADR) if you made a significant design choice.
- Update the Architecture, Data Models, and API sections to reflect the *current* state of the code so the next agent has accurate context.

---

## Part 2: Rules & Guidelines

### 1. Documentation Format
* Maintain a single `specs/README.md` file within each component.
* Use explicit Markdown links to source files (e.g., `[file.ts](../src/file.ts)`).
* Must contain: High-Level Overview, Architecture & Data Models, Interfaces & APIs, Testing Strategy, and ADRs.

### 2. Component Boundary Enforcement
* You must only make changes to the specific component (project subfolder) you are currently assigned to work on. Do not touch other components without explicit permission.

### 3. Collaborative Development & Ambiguity
* Be a collaborative partner. If a task is ambiguous, unclear, or contradicts the architecture, DO NOT make assumptions. Stop and prompt the user.

### 4. Verify Imports and Dependencies
* Never guess imports or assume third-party packages are installed. View the target file to confirm signatures, and verify dependencies in `package.json` (or equivalent).

### 5. Strict Typing
* Strictly adhere to the project's type system. Do not use `any`, `@ts-ignore`, or bypass type safety just to make an error go away. Fix the root cause.

### 6. Project Best Practices & Conventions
* **Code Style & Linting**: Use automated formatting (Prettier, Black, etc.). Enforce and fix strict linting errors immediately.
* **Git & Commit Conventions**: Use Conventional Commits (e.g., `feat(api): add user login`, `fix(ui): correct button alignment`).
* **Architecture**: Maintain a strict Separation of Concerns (e.g., Controller/Route -> Service -> Repository).
* **Secrets & Environment Variables**: Never hardcode secrets. Load all API keys and config via environment variables. When adding a new variable, you MUST update `.env.example`.
* **Error Handling & API Responses**: Fail fast and loud; do not swallow errors. Return standardized JSON responses for APIs (e.g., `{ success: boolean, data?: any, error?: string }`).
* **Dependencies**: Pin dependencies where appropriate. One component should have one focused job.
