# Job Hunter

A system to automate job search, resume matching, personalized outreach, and application tracking.

## Language

**Job Tracker Sheet**:
The Google Sheets spreadsheet stored in Google Drive folder \`11DdZR63ul4OushN3MOvNFdaQIE3y3uP-\` serving as the persistent database for jobs, applications, and status. It contains two primary tabs:
- **Jobs**: For scraped and evaluated listings. Columns: `Job title`, `Company + Company size`, `Posting link`, `Posting date`, `Location + Remote type (in office, hybrid, remote)`, `Seniority type (junior, mid, senior)`, `Salary type`, `Short description`, `match`, `no-match`, `Should proceed?`.
- **Applications**: For tracked active applications. Columns: `Job title`, `Company + Company size`, `Posting link`, `Posting date`, `Application date`, `Location + Remote type (in office, hybrid, remote)`, `Salary type`, `Short description`, `match`, `no-match`, `People contacted`, `Contact message`, `Comment`.
_Avoid_: Local database, Trello database

**Resume Profiles**:
Markdown files (.md) stored in a Google Drive subfolder within folder \`11DdZR63ul4OushN3MOvNFdaQIE3y3uP-\` representing the candidate's professional background tailored for specific target roles (e.g. QA, Project/Delivery Manager, Automation Specialist, Data/BI Analyst).
_Avoid_: Local CVs, resume database

**Resume Matcher**:
An LLM-based component that compares job descriptions with candidate resumes to compute compatibility scores and identify skill gaps. The target role is configured upfront per search run (e.g. running a search for "QA" positions using `qa.md`).
_Avoid_: Resume filter, CV checker

**Google Sheets MCP Server**:
A custom Model Context Protocol server developed in Python to perform CRUD operations on the Job Tracker Sheet.
_Avoid_: Third-party sheets server, spreadsheet-mcp

**OAuth 2.0 Credentials**:
User-authenticated Google API credentials allowing the Google Sheets MCP Server to securely access the user's personal Google Drive and Sheets on their behalf.
_Avoid_: Service account credentials, JSON key file

**Outreach Generator**:
An LLM-based component that creates customized cover letters and referral request messages on-demand when a job is marked for tracking under the Applications tab.
_Avoid_: Letter generator, email writer



