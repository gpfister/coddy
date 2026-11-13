# Recursive Task Decomposition (RTD)

## 1. The One-Shot Prompting Problem
Traditional LLM agents suffer from output compression. When prompted to write a specification or an execution plan for a non-trivial project, the model attempts to generate all components in a single output stream. Consequently:
- Use cases are reduced to single-sentence summaries.
- Architecture ignores non-functional requirements and edge cases.
- Execution plans become superficial bullet points ("Step 1: Write code, Step 2: Test").

## 2. The RTD Mechanism
Recursive Task Decomposition solves this through a strict two-stage process:

### Stage 1: Granular Enumeration
The agent analyzes the problem and generates an explicit, exhaustive list of entities:
- A list of target goals and measurable KPIs.
- A list of business and architecture rules.
- A list of use cases (`uc_01`, `uc_02`, ...).
- A list of validation test cases (`tc_01`, `tc_02`, ...).
- A list of target repositories and modules.

### Stage 2: Detailed Expansion Loop
Rather than attempting to write all details at once, the system expands items in the list:
1. The agent processes each item within a dedicated context.
2. The agent expands the item into complete technical documentation:
   - For use cases: Narrative, Preconditions, Trigger, Step-by-Step Flow, Edge Cases, and Postconditions.
   - For test cases: Test scenario description, input parameters, expected outcomes, and error assertions.
   - For plan tasks: Prerequisites, concrete implementation actions, unit testing requirements, and static analysis verification.
3. The expansion is validated for completeness. Rule R3 ensures an agentic loop cannot complete until 100% of items are expanded.

## 3. Human Gate Feedback Loops
If the human developer rejects an artifact during review:
- **Scope Change**: The agent rolls back to re-evaluate fundamental boundaries and requirements before rebuilding downstream artifacts.
