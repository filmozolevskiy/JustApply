---
name: pdf-to-md-resume
description: Convert PDF resumes (CVs) into the standardized Markdown resume profiles used in this project. Use this skill whenever the user provides a PDF resume or CV and asks to convert it, parse it, or format it into a markdown file under the resumes/ folder.
---

# PDF to Markdown Resume Profile Converter

This skill guides the agent in converting raw candidate resumes in PDF format into standardized, high-impact Markdown profiles tailored for specific target roles (e.g. QA, Project Management, BI/Data Analyst) and stored inside the `resumes/` folder in the project root.

## 1. Input Extraction

Use the `view_file` tool to read the PDF resume file. The platform automatically performs OCR and returns text blocks along with screenshots for inspection.
- Thoroughly review the OCR text output.
- Verify contact details, summary, skills categories, job titles, companies, dates of employment, and descriptions of achievements or scope.

## 2. Formatting Guidelines

Each profile MUST conform to the clean, high-impact style used in existing profiles. 

Format the Markdown exactly as follows:

```markdown
# [Target Role] Profile

**SUMMARY**
[A concise 2-3 sentence summary highlighting years of experience, core domains, major methodologies, and top tooling. Focus on high-level value.]

**KEY SKILLS**
- [Skill Category 1]: [Comma-separated skills]
- [Skill Category 2]: [Comma-separated skills]
- [Skill Category 3]: [Comma-separated skills]

**EXPERIENCE**
- **[Job Title] @ [Company] ([Date Range])**: [Brief 1-2 sentence summary of achievements and technical scope. Keep bullets concise and high-impact. Avoid long paragraphs.]
- **[Job Title] @ [Company] ([Date Range])**: [Brief 1-2 sentence summary of achievements and technical scope.]
```

### Formatting Rules:
1. **Target Role in Title**: The Level 1 header must identify the target role, e.g., `# QA Engineer / Automation Specialist Profile`, `# Data & BI Analyst Profile`, `# Technical Project & Delivery Manager Profile`.
2. **Bold Section Headers**: Use `**SUMMARY**`, `**KEY SKILLS**`, and `**EXPERIENCE**`.
3. **Concise Experience**: Convert long lists of bullets into short, punchy summaries. Focus on the core technical scope and quantifiable achievements.

## 3. Output Placement

Save the resulting Markdown file to the `resumes/` directory at the project root:
- File name format: `<role_or_profile_name>.md` in snake_case (e.g., `resumes/bi_intelligence.md`).
