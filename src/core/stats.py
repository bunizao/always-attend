"""
 █████╗ ██╗     ██╗    ██╗ █████╗ ██╗   ██╗███████╗
██╔══██╗██║     ██║    ██║██╔══██╗╚██╗ ██╔╝██╔════╝
███████║██║     ██║ █╗ ██║███████║ ╚████╔╝ ███████╗
██╔══██║██║     ██║███╗██║██╔══██║  ╚██╔╝  ╚════██║
██║  ██║███████╗╚███╔███╔╝██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝

 █████╗ ████████╗████████╗███████╗███╗   ██╗██████╗ 
██╔══██╗╚══██╔══╝╚══██╔══╝██╔════╝████╗  ██║██╔══██╗
███████║   ██║      ██║   █████╗  ██╔██╗ ██║██║  ██║
██╔══██║   ██║      ██║   ██╔══╝  ██║╚██╗██║██║  ██║
██║  ██║   ██║      ██║   ███████╗██║ ╚████║██████╔╝
╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚══════╝╚═╝  ╚═══╝╚═════╝ 
src/core/stats.py
Attendance statistics reporting utilities.
"""

import os
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from utils.logger import logger
from utils.env_utils import load_env

class StatsManager:
    def __init__(self, stats_file: str = "attendance_stats.json"):
        self.stats_file = stats_file
        self.stats_data = self._load_stats()

    def _load_stats(self) -> Dict[str, Any]:
        """Load existing stats from file."""
        if not os.path.exists(self.stats_file):
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "courses": {},
                "daily_stats": {},
                "weekly_stats": {},
                "last_run": None,
                "first_run": None,
                "total_code_attempts": 0,
                "total_successful_codes": 0,
            }
        
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load stats file: {e}")
            # Return default stats instead of calling recursively
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "courses": {},
                "daily_stats": {},
                "weekly_stats": {},
                "last_run": None,
                "first_run": None,
                "total_code_attempts": 0,
                "total_successful_codes": 0,
            }

    def _save_stats(self) -> None:
        """Save stats to file."""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def record_run(
        self,
        success: bool,
        courses_processed: List[str],
        codes_submitted: Dict[str, int],
        errors: List[str] = None,
        attempts: Optional[Dict[str, int]] = None,
        success_codes: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Record a run's statistics."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week = now.strftime("%Y-W%U")

        attempts = attempts or {}
        success_codes = success_codes or {}
        total_attempts_run = sum(attempts.values())
        total_success_codes = sum(len(v) for v in success_codes.values())

        self.stats_data.setdefault("total_code_attempts", 0)
        self.stats_data.setdefault("total_successful_codes", 0)
        self.stats_data["total_code_attempts"] += total_attempts_run
        self.stats_data["total_successful_codes"] += total_success_codes

        # Update basic counters
        self.stats_data["total_runs"] += 1
        if success:
            self.stats_data["successful_runs"] += 1
        else:
            self.stats_data["failed_runs"] += 1
        
        # Update timestamps
        self.stats_data["last_run"] = now.isoformat()
        if not self.stats_data["first_run"]:
            self.stats_data["first_run"] = now.isoformat()
        
        # Update daily stats
        if today not in self.stats_data["daily_stats"]:
            self.stats_data["daily_stats"][today] = {
                "runs": 0,
                "successful": 0,
                "codes_submitted": 0,
                "courses": [],
                "code_attempts": 0,
                "codes_successful": 0,
            }

        daily = self.stats_data["daily_stats"][today]
        daily.setdefault("code_attempts", 0)
        daily.setdefault("codes_successful", 0)
        daily["runs"] += 1
        if success:
            daily["successful"] += 1
        daily["codes_submitted"] += sum(codes_submitted.values())
        daily["courses"].extend(courses_processed)
        daily["courses"] = list(set(daily["courses"]))
        daily["code_attempts"] += total_attempts_run
        daily["codes_successful"] += total_success_codes

        # Update weekly stats
        if week not in self.stats_data["weekly_stats"]:
            self.stats_data["weekly_stats"][week] = {
                "runs": 0,
                "successful": 0,
                "codes_submitted": 0,
                "courses": [],
                "code_attempts": 0,
                "codes_successful": 0,
            }

        weekly = self.stats_data["weekly_stats"][week]
        weekly.setdefault("code_attempts", 0)
        weekly.setdefault("codes_successful", 0)
        weekly["runs"] += 1
        if success:
            weekly["successful"] += 1
        weekly["codes_submitted"] += sum(codes_submitted.values())
        weekly["courses"].extend(courses_processed)
        weekly["courses"] = list(set(weekly["courses"]))
        weekly["code_attempts"] += total_attempts_run
        weekly["codes_successful"] += total_success_codes

        # Update course-specific stats
        for course in courses_processed:
            if course not in self.stats_data["courses"]:
                self.stats_data["courses"][course] = {
                    "total_runs": 0,
                    "successful_runs": 0,
                    "codes_submitted": 0,
                    "last_processed": None,
                    "first_processed": None,
                    "total_attempts": 0,
                    "successful_codes": [],
                }

            course_stats = self.stats_data["courses"][course]
            course_stats["total_runs"] += 1
            if success:
                course_stats["successful_runs"] += 1
            course_stats["codes_submitted"] += codes_submitted.get(course, 0)
            course_stats["last_processed"] = now.isoformat()
            if not course_stats["first_processed"]:
                course_stats["first_processed"] = now.isoformat()
            course_stats.setdefault("total_attempts", 0)
            course_stats.setdefault("successful_codes", [])
            course_stats["total_attempts"] += attempts.get(course, 0)
            if course in success_codes:
                course_stats["successful_codes"].extend(success_codes[course])
                # De-duplicate while preserving order, keep last 20
                course_stats["successful_codes"] = list(dict.fromkeys(course_stats["successful_codes"]))[-20:]

        # Record errors if any
        if errors:
            if "recent_errors" not in self.stats_data:
                self.stats_data["recent_errors"] = []
            
            for error in errors:
                self.stats_data["recent_errors"].append({
                    "timestamp": now.isoformat(),
                    "error": error
                })
            
            # Keep only last 50 errors
            self.stats_data["recent_errors"] = self.stats_data["recent_errors"][-50:]
        
        self._save_stats()

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all statistics."""
        total_runs = self.stats_data["total_runs"]
        success_rate = (self.stats_data["successful_runs"] / total_runs * 100) if total_runs > 0 else 0
        
        # Calculate total codes submitted
        total_codes = sum(
            course_data["codes_submitted"] 
            for course_data in self.stats_data["courses"].values()
        )
        
        # Get recent activity (last 7 days)
        recent_days = []
        for i in range(7):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_data = self.stats_data["daily_stats"].get(date, {})
            recent_days.append({
                "date": date,
                "runs": daily_data.get("runs", 0),
                "codes": daily_data.get("codes_submitted", 0),
                "attempts": daily_data.get("code_attempts", 0),
                "hits": daily_data.get("codes_successful", 0),
            })
        
        return {
            "overview": {
                "total_runs": total_runs,
                "successful_runs": self.stats_data["successful_runs"],
                "failed_runs": self.stats_data["failed_runs"],
                "success_rate": round(success_rate, 2),
                "total_codes_submitted": total_codes,
                "total_code_attempts": self.stats_data.get("total_code_attempts", 0),
                "total_successful_codes": self.stats_data.get("total_successful_codes", total_codes),
            },
            "timeline": {
                "first_run": self.stats_data["first_run"],
                "last_run": self.stats_data["last_run"]
            },
            "courses": self.stats_data["courses"],
            "recent_activity": recent_days,
            "recent_errors": self.stats_data.get("recent_errors", [])[-10:]  # Last 10 errors
        }

    def print_stats(self) -> None:
        """Print formatted statistics to console."""
        summary = self.get_summary()
        overview = summary["overview"]
        
        print("\n" + "="*60)
        print("📊 ATTENDANCE STATISTICS")
        print("="*60)
        
        # Overview
        print("\n📈 OVERVIEW:")
        print(f"  Total Runs: {overview['total_runs']}")
        print(f"  Successful: {overview['successful_runs']}")
        print(f"  Failed: {overview['failed_runs']}")
        print(f"  Success Rate: {overview['success_rate']}%")
        print(f"  Total Codes Submitted: {overview['total_codes_submitted']}")
        print(f"  Code Attempts: {overview['total_code_attempts']}")
        print(f"  Successful Codes: {overview['total_successful_codes']}")
        
        # Timeline
        timeline = summary["timeline"]
        if timeline["first_run"]:
            first_run = datetime.fromisoformat(timeline["first_run"]).strftime("%Y-%m-%d %H:%M")
            print(f"  First Run: {first_run}")
        if timeline["last_run"]:
            last_run = datetime.fromisoformat(timeline["last_run"]).strftime("%Y-%m-%d %H:%M")
            print(f"  Last Run: {last_run}")
        
        # Course breakdown
        if summary["courses"]:
            print("\n📚 COURSES:")
            for course, data in summary["courses"].items():
                success_rate = (data["successful_runs"] / data["total_runs"] * 100) if data["total_runs"] > 0 else 0
                print(f"  {course}:")
                print(f"    Runs: {data['total_runs']} (Success: {success_rate:.1f}%)")
                print(f"    Codes Submitted: {data['codes_submitted']}")
        
        # Recent activity
        print("\n📅 RECENT ACTIVITY (Last 7 Days):")
        for day in summary["recent_activity"]:
            if day["runs"] > 0:
                print(f"  {day['date']}: {day['runs']} runs, {day['codes']} codes submitted")
        
        # Recent errors
        if summary["recent_errors"]:
            print("\n❌ RECENT ERRORS:")
            for error in summary["recent_errors"][-5:]:  # Show last 5 errors
                timestamp = datetime.fromisoformat(error["timestamp"]).strftime("%m-%d %H:%M")
                print(f"  [{timestamp}] {error['error']}")
        
        print("\n" + "="*60)

def main():
    load_env(os.getenv('ENV_FILE', '.env'))
    
    parser = argparse.ArgumentParser(description="View attendance statistics")
    parser.add_argument("--file", default="attendance_stats.json", help="Stats file path")
    parser.add_argument("--export", help="Export stats to JSON file")
    parser.add_argument("--clear", action="store_true", help="Clear all statistics")
    args = parser.parse_args()
    
    stats = StatsManager(args.file)
    
    if args.clear:
        if input("Are you sure you want to clear all statistics? (y/N): ").lower() == 'y':
            os.remove(args.file) if os.path.exists(args.file) else None
            print("Statistics cleared.")
        return
    
    if args.export:
        summary = stats.get_summary()
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"Statistics exported to {args.export}")
        return
    
    stats.print_stats()

if __name__ == "__main__":
    main()
