import json


def _seed_db(cursor):
    seed_data = [
        {
            "id": 1,
            "title": "Senior QA Automation Engineer",
            "company": "TechCorp",
            "size": "100-500",
            "link": "https://linkedin.com/jobs/123",
            "date": "2026-06-05",
            "location": "Remote",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$130k - $160k",
            "description": "We are looking for a Senior QA Automation Engineer to build and execute end-to-end testing strategies. You will design automation frameworks using Python and Pytest, integration into GitHub actions, and lead testing standards.",
            "matchScore": 94,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "found",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Highly proficient in Python & Pytest", "Extensive CI/CD pipeline automation", "Playwright & Selenium Frameworks"]),
            "gaps": json.dumps(["No direct experience with WebUSB", "AWS Cloud Practitioner certification preferred"]),
            "contacts": json.dumps([
                {"name": "Jane Doe", "role": "VP Engineering", "linkedin": "https://linkedin.com/in/janedoe", "contacted": False},
                {"name": "John Smith", "role": "Recruiting Coordinator", "linkedin": "https://linkedin.com/in/johnsmith", "contacted": False}
            ]),
            "outreachMessage": "Hi Jane,\n\nI saw your listing for a Senior QA Automation Engineer at TechCorp. With my deep background in building Python/Pytest framework architectures and setting up robust CI/CD pipelines, I believe I can hit the ground running. I'd love to learn more about TechCorp's engineering goals.\n\nBest,\nCandidate",
            "comment": "Excellent match. Framework matches 100%."
        },
        {
            "id": 2,
            "title": "Technical Project & Delivery Manager",
            "company": "InnovateHQ",
            "size": "50-200",
            "link": "https://linkedin.com/jobs/124",
            "date": "2026-06-04",
            "location": "New York, NY",
            "remoteType": "hybrid",
            "seniority": "senior",
            "salary": "$140k - $170k",
            "description": "InnovateHQ is seeking a Technical Project Manager to coordinate cross-functional agile sprints, manage stakeholder delivery milestones, and ensure tight integration of engineering and product roadmaps.",
            "matchScore": 88,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "found",
            "resumeUsed": "project_manager.md",
            "strengths": json.dumps(["Expert Scrum Master with 5+ years experience", "Strong technical background in Python systems", "Stakeholder communications"]),
            "gaps": json.dumps(["Prior experience at Series A startups is not documented"]),
            "contacts": json.dumps([
                {"name": "Marcus Vance", "role": "Director of Product", "linkedin": "https://linkedin.com/in/marcusvance", "contacted": False},
                {"name": "Alice Adams", "role": "Talent Lead", "linkedin": "https://linkedin.com/in/aliceadams", "contacted": False}
            ]),
            "outreachMessage": "Dear Marcus,\n\nI noticed InnovateHQ is hiring a Technical Project Manager. Given my extensive delivery management experience aligning engineering teams with product milestones, I'm excited about this opportunity. Let's connect!\n\nBest regards,\nCandidate",
            "comment": "Need to verify Series A startup history before applying."
        },
        {
            "id": 3,
            "title": "Data & BI Analyst",
            "company": "FinanceFlow",
            "size": "1000+",
            "link": "https://linkedin.com/jobs/125",
            "date": "2026-06-03",
            "location": "Charlotte, NC",
            "remoteType": "in office",
            "seniority": "mid",
            "salary": "$100k - $120k",
            "description": "FinanceFlow is hiring a Data Analyst to compile SQL reporting queries, construct Tableau dashboards, and deliver weekly metrics to financial compliance executives.",
            "matchScore": 75,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "contacted",
            "resumeUsed": "data_analyst.md",
            "strengths": json.dumps(["Excellent SQL database experience", "Experienced with Tableau and PowerBI", "Detail-oriented financial analysis"]),
            "gaps": json.dumps(["No direct experience with FinTech compliance frameworks"]),
            "contacts": json.dumps([
                {"name": "Sophia Patel", "role": "Data Analytics Lead", "linkedin": "https://linkedin.com/in/sophiapatel", "contacted": True},
                {"name": "Robert Miller", "role": "FinTech Recruiter", "linkedin": "https://linkedin.com/in/robertmiller", "contacted": False}
            ]),
            "outreachMessage": "Hi Sophia,\n\nI'm reaching out regarding the Data & BI Analyst vacancy. I have a proven track record creating high-impact SQL/Tableau dashboards. I'd love to help FinanceFlow drive metrics.\n\nThanks,\nCandidate",
            "comment": "Sophia responded! Phone screen scheduled next week."
        },
        {
            "id": 4,
            "title": "QA Automation Specialist",
            "company": "GameStudio",
            "size": "200-500",
            "link": "https://linkedin.com/jobs/126",
            "date": "2026-06-01",
            "location": "Austin, TX",
            "remoteType": "remote",
            "seniority": "mid",
            "salary": "$90k - $110k",
            "description": "Join our game build testing team. You will automate functional regression testing for web services and gameplay configurations using Python scripts.",
            "matchScore": 92,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "interviewing",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Automation framework expert", "Fast debugging of Python regression scripts"]),
            "gaps": json.dumps(["No experience with specific Game engines (Unreal/Unity)"]),
            "contacts": json.dumps([
                {"name": "Alex Mercer", "role": "QA Manager", "linkedin": "https://linkedin.com/in/alexmercer", "contacted": True},
                {"name": "Emma Stone", "role": "HR Business Partner", "linkedin": "https://linkedin.com/in/emmastone", "contacted": True}
            ]),
            "outreachMessage": "Hi Alex,\n\nI'd love to join GameStudio as a QA Automation Specialist. My scripting experience with Python makes me an excellent fit for your functional regression goals.\n\nBest,\nCandidate",
            "comment": "Completed round 1 interview. Focus was Python scripting."
        },
        {
            "id": 5,
            "title": "Agile Scrum Master",
            "company": "GlobalSystems",
            "size": "5000+",
            "link": "https://linkedin.com/jobs/127",
            "date": "2026-05-28",
            "location": "Remote",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$120k - $140k",
            "description": "Seeking a senior scrum master to facilitate agile practices across 4 distributed software teams. Enterprise scale delivery planning required.",
            "matchScore": 68,
            "matchType": "no-match",
            "shouldProceed": 0,
            "status": "rejected",
            "resumeUsed": "project_manager.md",
            "strengths": json.dumps(["Scrum Master Certified"]),
            "gaps": json.dumps(["No experience with SAFe framework at enterprise scale"]),
            "contacts": json.dumps([
                {"name": "Evelyn Ross", "role": "HR Partner", "linkedin": "https://linkedin.com/in/evelynross", "contacted": False}
            ]),
            "outreachMessage": "",
            "comment": "Enterprise SAFe requirement is a hard blocker."
        },
        {
            "id": 6,
            "title": "QA Lead",
            "company": "AppStart",
            "size": "10-50",
            "link": "https://linkedin.com/jobs/128",
            "date": "2026-06-06",
            "location": "San Francisco, CA",
            "remoteType": "remote",
            "seniority": "senior",
            "salary": "$150k - $180k",
            "description": "AppStart is seeking our first QA Lead to establish our test pipeline. You will be responsible for defining automation protocols, running manual exploratory testing, and implementing CI tools.",
            "matchScore": 91,
            "matchType": "match",
            "shouldProceed": 1,
            "status": "found",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Startup experience (first QA hire)", "Established full-suite testing protocols from scratch", "Fast API testing"]),
            "gaps": json.dumps(["No mobile testing experience mentioned"]),
            "contacts": json.dumps([
                {"name": "Tariq Mahmood", "role": "Co-Founder / CTO", "linkedin": "https://linkedin.com/in/tariqmahmood", "contacted": False},
                {"name": "Liam Neeson", "role": "Talent Specialist", "linkedin": "https://linkedin.com/in/liamneeson", "contacted": False}
            ]),
            "outreachMessage": "Hi Tariq,\n\nCongratulations on expanding your engineering team. As a QA Lead who has previously built testing infrastructures for early stage startups, I would love to help AppStart structure its automation strategy.\n\nBest,\nCandidate",
            "comment": "Tariq is active on LinkedIn posting engineering updates."
        },
        {
            "id": 7,
            "title": "QA Automation Contractor",
            "company": "Fuze HR Solutions",
            "size": "50-200",
            "link": "https://linkedin.com/jobs/129",
            "date": "2026-06-07",
            "location": "Toronto, ON",
            "remoteType": "hybrid",
            "seniority": "mid",
            "salary": "$70 - $80 / hr",
            "description": "Our client, a leading financial institution, is seeking a QA Automation Contractor to join their digital banking testing team. You will write automated test scripts in Python and execute regressions.",
            "matchScore": 65,
            "matchType": "no-match",
            "shouldProceed": 0,
            "status": "found",
            "resumeUsed": "qa.md",
            "strengths": json.dumps(["Python scripting background", "Experience with QA regression testing"]),
            "gaps": json.dumps(["Posted by a recruiting agency/staffing firm"]),
            "contacts": json.dumps([]),
            "outreachMessage": "",
            "comment": "Recruiter company. 15-point penalty applied.",
            "isRecruiter": 1
        }
    ]
    for job in seed_data:
        job.setdefault("isRecruiter", 0)
        cursor.execute("""
            INSERT INTO jobs (
                id, title, company, size, link, date, location, remoteType, seniority, salary,
                description, matchScore, matchType, shouldProceed, status, resumeUsed,
                strengths, gaps, contacts, outreachMessage, comment, isRecruiter
            ) VALUES (
                :id, :title, :company, :size, :link, :date, :location, :remoteType, :seniority, :salary,
                :description, :matchScore, :matchType, :shouldProceed, :status, :resumeUsed,
                :strengths, :gaps, :contacts, :outreachMessage, :comment, :isRecruiter
            )
        """, job)
