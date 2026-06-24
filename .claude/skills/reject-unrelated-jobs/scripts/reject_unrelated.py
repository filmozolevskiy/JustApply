#!/usr/bin/env python3
import sqlite3
import re
import argparse
import os

# Resolve DB path relative to project root (same location as src.db.connection.DB_PATH)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "..", ".."))
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "just_apply.db")

KEYWORDS = [
    # QA / Testing / Quality
    r'\bqa\b', r'\bquality\b', r'\bqualité\b', r'\btest\b', r'\btesting\b', r'\bsdet\b', r'\bautomation\b', r'\bautomatique\b',
    # PM / Project / Product / Program / Scrum
    r'\bproject\b', r'\bprojet\b', r'\bprojets\b', r'\bprogram\b', r'\bprogramme\b', r'\bdelivery\b', r'\bscrum\b', r'\bproduct\b', r'\bproduit\b', r'\bpm\b', r'\bchef\s+de\s+projet\b', r'\bgestionnaire\b',
    # Data / Analytics / Business Intelligence / DB
    r'\bdata\b', r'\bdonn[eé]es?\b', r'\banalyst\b', r'\banalyste\b', r'\banalytics\b', r'\banalytique\b', r'\bbi\b', r'\bbusiness\s+intelligence\b', r'\bsql\b', r'\bdatabase\b', r'\breporting\b',
    # AI / Machine Learning
    r'\bai\b', r'\bia\b', r'\bmachine\s+learning\b', r'\bml\b', r'\bllm\b', r'\bdeep\s+learning\b', r'\bnlp\b', r'\bgenerative\b', r'\bgénérative\b'
]

def get_unrelated_jobs(all_active=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if all_active:
        c.execute("SELECT id, title, company, status FROM jobs WHERE status != 'rejected'")
    else:
        c.execute("SELECT id, title, company, status FROM jobs WHERE status = 'found'")
        
    jobs = c.fetchall()
    conn.close()
    
    combined_regex = re.compile('|'.join(KEYWORDS), re.IGNORECASE)
    unrelated = []
    for j_id, title, company, status in jobs:
        if not combined_regex.search(title):
            unrelated.append((j_id, title, company, status))
            
    return unrelated

def reject_jobs(job_ids):
    if not job_ids:
        print("No job IDs provided to reject.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    placeholders = ','.join(['?'] * len(job_ids))
    c.execute(f"UPDATE jobs SET status = 'rejected' WHERE id IN ({placeholders})", job_ids)
    conn.commit()
    conn.close()
    print(f"Successfully rejected {len(job_ids)} job(s) in database.")

def main():
    parser = argparse.ArgumentParser(description="Find and reject unrelated jobs (not AI, Data, QA, or PM) in the database.")
    parser.add_argument("--list", action="store_true", help="List unrelated jobs (default action).")
    parser.add_argument("--reject-all", action="store_true", help="Reject all detected unrelated jobs.")
    parser.add_argument("--reject-ids", type=str, help="Comma-separated list of job IDs to reject.")
    parser.add_argument("--all-active", action="store_true", help="Scan all active (non-rejected) jobs instead of just 'sourced' jobs.")
    
    args = parser.parse_args()
    
    global DB_PATH
    if not os.path.exists(DB_PATH):
        cwd_path = os.path.join(os.getcwd(), "data", "job_tracker.db")
        if os.path.exists(cwd_path):
            DB_PATH = cwd_path
        else:
            print(f"Error: Database not found at {DB_PATH}")
            return
                
    unrelated = get_unrelated_jobs(all_active=args.all_active)
    
    if args.reject_all:
        if not unrelated:
            print("No unrelated jobs found to reject.")
            return
        ids = [j[0] for j in unrelated]
        reject_jobs(ids)
        
    elif args.reject_ids:
        ids = [int(i.strip()) for i in args.reject_ids.split(",") if i.strip().isdigit()]
        reject_jobs(ids)
        
    else:
        # Default: list jobs
        scope = "all active" if args.all_active else "'found'"
        print(f"Found {len(unrelated)} unrelated jobs in {scope} status:")
        print("-" * 80)
        print(f"{'ID':<6} | {'Title':<45} | {'Company':<25}")
        print("-" * 80)
        for j_id, title, company, _ in unrelated:
            # Truncate for formatting
            disp_title = title[:45] if len(title) <= 45 else title[:42] + "..."
            disp_company = company[:25] if len(company) <= 25 else company[:22] + "..."
            print(f"{j_id:<6} | {disp_title:<45} | {disp_company:<25}")
        print("-" * 80)
        print("To reject all these, run: python3 reject_unrelated.py --reject-all")
        print("To reject specific IDs, run: python3 reject_unrelated.py --reject-ids ID1,ID2,...")

if __name__ == "__main__":
    main()
