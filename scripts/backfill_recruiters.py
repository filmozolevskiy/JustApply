#!/usr/bin/env python3
import sys
import os
import json
import sqlite3

# Add project root to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import DB_PATH
from src.core.matcher import check_recruiter_by_name

def backfill_recruiters():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    print(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch all jobs
    cursor.execute("SELECT id, company, matchScore, matchType, shouldProceed, gaps, isRecruiter FROM jobs")
    jobs = cursor.fetchall()
    
    updated_count = 0
    print(f"Scanning {len(jobs)} existing jobs for recruiting agency patterns...")

    for job in jobs:
        company = job["company"] or ""
        job_id = job["id"]
        
        # Check if the company name matches our recruiter regex patterns
        if check_recruiter_by_name(company):
            # Apply recruiter rules
            current_is_recruiter = bool(job["isRecruiter"])
            current_match_score = job["matchScore"] or 0
            current_gaps_str = job["gaps"] or "[]"
            
            try:
                gaps = json.loads(current_gaps_str)
                if not isinstance(gaps, list):
                    gaps = []
            except Exception:
                gaps = []

            # If it's already marked as recruiter and the gaps/scores are already updated, skip
            has_gap_notice = "Posted by a recruiting agency/staffing firm" in gaps
            
            needs_update = False
            new_is_recruiter = 1
            new_should_proceed = 0
            new_match_type = "no-match"
            
            if not current_is_recruiter:
                needs_update = True
                
            # Compute new match score with penalty applied
            if current_match_score >= 75:
                new_match_score = min(70, current_match_score - 15)
                needs_update = True
            elif current_match_score > 0 and not current_is_recruiter:
                new_match_score = max(0, current_match_score - 15)
                needs_update = True
            else:
                new_match_score = current_match_score
                
            if not has_gap_notice:
                gaps.append("Posted by a recruiting agency/staffing firm")
                needs_update = True
                
            if job["shouldProceed"] != 0:
                needs_update = True

            if job["matchType"] != "no-match" and current_match_score >= 75:
                needs_update = True

            if needs_update:
                new_gaps_str = json.dumps(gaps)
                cursor.execute("""
                    UPDATE jobs 
                    SET isRecruiter = ?, 
                        matchScore = ?, 
                        shouldProceed = ?, 
                        matchType = ?, 
                        gaps = ? 
                    WHERE id = ?
                """, (new_is_recruiter, new_match_score, new_should_proceed, new_match_type, new_gaps_str, job_id))
                
                print(f"Updated job ID {job_id} ({company}):")
                print(f"  - isRecruiter: {current_is_recruiter} -> True")
                print(f"  - matchScore: {current_match_score} -> {new_match_score}")
                print(f"  - shouldProceed: {job['shouldProceed']} -> False")
                print(f"  - matchType: '{job['matchType']}' -> 'no-match'")
                print(f"  - Added agency notice to gaps")
                updated_count += 1

    if updated_count > 0:
        conn.commit()
        print(f"\nSuccessfully updated {updated_count} jobs in the database.")
    else:
        print("\nNo jobs required updates (all match existing recruiter filters).")
        
    conn.close()

if __name__ == "__main__":
    backfill_recruiters()
