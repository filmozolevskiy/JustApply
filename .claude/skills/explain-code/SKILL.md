---
name: explain-code
description: Use this skill whenever the user asks to explain a file, explain code syntax, walk through code logic, analyze code behavior, understand a function, explain why code was written a certain way, or explain an abstract programming concept (e.g., DRY principle, Dependency Injection). Make sure to trigger this skill if the user asks "explain how X works", "what does this code do", "walk me through this file", or "what is the X principle/pattern".
---

# Explain Code Skill

This skill guides the agent in providing exceptionally detailed, interactive, and visually stunning code explanations. 

Instead of writing long plain-text explanations in chat (which are prone to truncation and hard to read), this skill compiles explanations into a side-by-side interactive HTML dashboard in the user's browser, complete with syntax highlighting, visual execution flows, and clickable code walkthrough cards.

---

## 1. Core Workflow

Follow these steps whenever a user requests an explanation of code, a file, or a programming concept:

### Step 0: Handle Abstract Concepts (If Applicable)
If the user asks to explain an abstract programming concept, design pattern, or principle (e.g., "explain Dependency Injection") without providing a specific code file:
1.  **Infer the Language:** Try to infer the programming language from the user's current project context or their prompt. If it's not clear, **ask the user** which language they prefer before proceeding.
2.  **Generate an Example:** Generate a highly readable, synthetic code snippet demonstrating the concept in the chosen language.
3.  **Save the Example:** Write this snippet to a temporary file (e.g., `/tmp/concept_example.ext`) and use it as the `--code-file` in the steps below. The walkthrough blocks will then map to this synthetic example.

### Step 1: Draft the Explanation Content
Analyze the code and prepare the following sections in Markdown. Your target audience is **junior developers** with little coding knowledge. Use **ESL (English as a Second Language) friendly language**—keep sentences short, straightforward, and very easy to understand. Use simple, everyday analogies, avoid dense jargon, and break complex ideas down into small steps.

1.  **Overview:** Provide a high-level, easy-to-understand explanation of what the entire file or code snippet does in general. What is its main purpose? Use simple analogies. When explaining concepts in simple words, make sure to introduce the common industry/market terminology for them (e.g., "In the industry, this is commonly known as...").
2.  **Walkthrough Blocks:** Identify key logical blocks of the code. Assign line ranges (e.g., `L12-L25` or `L15`). For each block, provide a highly detailed explanation that walks through the code. **Include syntax explanations here:** explain language-specific features (decorators, generators, async, what specific keywords mean) in simple terms within the context of the block, and link them back to their formal terminology.
3.  **Usage:** Build a complete, valid integration example showing inputs and outputs.
4.  **Rationale:** Explain why this pattern/algorithm was chosen in simple terms.
5.  **Alternatives & Trade-offs:** List 1–2 alternatives and score them on metrics (**Readability**, **Performance**, **Testability**, **Complexity**).
6.  **Diagram:** Draft a Mermaid diagram (e.g. sequence diagram or flowchart) visualising the execution flow. Ensure the diagram remains technical and detailed, accurately reflecting the true complexity and logic of the code rather than an oversimplified version.

### Step 2: Write Content to a JSON File
Write a temporary JSON file to `/tmp/explanation_input.json` containing the content structured precisely as follows:

```json
{
  "overview": "### What does this code do?\nAn easy-to-understand explanation using analogies. It acts like a...",
  "walkthrough": [
    {
      "title": "Block Title (e.g. Database Connection)",
      "lines": "L12-L18",
      "content": "Detailed explanation of what happens in this block. **Syntax explained:** `__init__` is a special method that..."
    }
  ],
  "usage": "### How to use\n```python\n# code example here...\n```\n- Inputs/outputs details...",
  "rationale": "### Architectural Rationale\n- Rationale details...",
  "alternatives": [
    {
      "name": "Alternative Name",
      "metrics": {
        "Readability": 4,
        "Performance": 5,
        "Testability": 3,
        "Complexity": 2
      },
      "pros": [
        "Pro 1",
        "Pro 2"
      ],
      "cons": [
        "Con 1"
      ],
      "details": "Explanation of alternative details..."
    }
  ],
  "diagram": "sequenceDiagram\n    Alice->>Bob: Hello"
}
```

### Step 3: Run the Compilation Script
Run the bundled report generator script. Determine a timestamped output file in the OS temp directory and pass the `--open` flag to automatically open the report in the user's default browser:

```bash
python3 .claude/skills/explain-code/scripts/generate_report.py \
  --code-file <path_to_source_file> \
  --explanation-file /tmp/explanation_input.json \
  --output-file /tmp/code-explanation-$(date +%s).html \
  --open
```

### Step 4: Respond to the User
Provide a brief, 2-3 sentence confirmation in the chat, stating that you generated and opened the interactive code explanation. Include the clickable absolute path of the generated HTML report for easy reference:
* E.g., *"I have generated and opened the interactive code explanation report at [code-explanation-1718021111.html](file:///tmp/code-explanation-1718021111.html). You can switch tabs on the right side of the report to review syntax, walkthroughs, usage guides, and alternative designs."*
