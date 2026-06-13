# HTML Report visual guidelines

The code explanation HTML report MUST be compiled into a single self-contained file. It should use a modern, premium dark UI with glassmorphism effects, a side-by-side split screen on desktop, and interactive tabbed/accordion navigation for the explanations.

## 1. CDNs & Third-Party Libraries

Use the following libraries via CDN (load inside the `<head>` of the report):

*   **Tailwind CSS (v3):** For rapid, responsive, premium layouts.
    ```html
    <script src="https://cdn.tailwindcss.com"></script>
    ```
*   **PrismJS:** For syntax highlighting of code blocks.
    *   JS: `https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/prism.min.js`
    *   Autoloader (for language support): `https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/plugins/autoloader/prism-autoloader.min.js`
    *   Okaidia Theme CSS: `https://cdnjs.cloudflare.com/ajax/libs/prism/1.29.0/themes/prism-okaidia.min.css`
*   **MermaidJS:** For visual diagrams/flowcharts.
    ```html
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({ startOnLoad: true, theme: 'dark' });
    </script>
    ```
*   **Google Fonts:** Outfit and JetBrains Mono (for code).
    ```html
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    ```

---

## 2. Layout Structure

The template uses a responsive desktop layout:

*   **Header:** Fixed top bar with file name, absolute path, size, and last modified info.
*   **Sidebar (Left):** Sticky/fixed vertical panel showing the code codeblock with line numbers and full PrismJS styling.
*   **Main content panel (Right):** A tab-controlled viewer showing:
    *   **Syntax:** Complex syntax explanation.
    *   **Walkthrough:** Interactive step-by-step logic explanation.
    *   **Usage:** Valid code examples and side effects.
    *   **Rationale:** Architecture context and safety parameters.
    *   **Alternatives:** Comparison matrix with score indicators and details accordion.

---

## 3. Interactive Mechanics

Include clean, zero-dependency inline JavaScript for:

1.  **Tab Switcher:** Switching between the explanation panels with smooth active transitions (e.g., adding/removing active border and opacity classes).
2.  **Accordion Cards:** Toggling alternative approaches' detail sections with smooth height or opacity changes.
3.  **Visual Elements:** Subtle micro-interactions, such as hover lifts on cards and table rows, and clean dark mode colors (e.g., deep charcoal `bg-[#0f172a]`, glassmorphism borders `border-white/10`, and glowing text accents).
