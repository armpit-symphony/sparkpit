#!/usr/bin/env python3

import os
import sys
import subprocess
import requests
import json
from datetime import datetime
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

class SeedDemoTester:
    def __init__(self):
        self.base_url = "https://sparklab-2.preview.emergentagent.com"
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_email = None
        self.admin_user_id = None
        self.results = []
        
        # Load environment
        ROOT_DIR = Path(__file__).parent
        load_dotenv(ROOT_DIR / "backend" / ".env")
        
        # Get MongoDB connection
        self.mongo_url = os.environ.get("MONGO_URL")
        self.db_name = os.environ.get("DB_NAME")
        
    def log_result(self, test_name: str, success: bool, message: str):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}: {message}")
        else:
            print(f"❌ {test_name}: {message}")
        
        self.results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def find_admin_user(self):
        """Find existing admin user in database"""
        try:
            client = MongoClient(self.mongo_url)
            db = client[self.db_name]
            
            admin_user = db.users.find_one({"role": "admin"})
            if admin_user:
                self.admin_email = admin_user.get("email")
                self.admin_user_id = admin_user.get("id")
                self.log_result("Find Admin User", True, f"Found admin: {self.admin_email}")
                return True
            else:
                self.log_result("Find Admin User", False, "No admin user found in database")
                return False
        except Exception as e:
            self.log_result("Find Admin User", False, f"Database error: {str(e)}")
            return False
    
    def test_seed_cli_with_admin_email(self):
        """Test seed CLI using ADMIN_EMAIL"""
        if not self.admin_email:
            self.log_result("Seed CLI (ADMIN_EMAIL)", False, "No admin email available")
            return False
            
        try:
            env = os.environ.copy()
            env["ADMIN_EMAIL"] = self.admin_email
            env["BASE_URL"] = self.base_url
            
            # Run the seed CLI
            result = subprocess.run(
                [sys.executable, "-m", "sparkpit.seed_demo"],
                cwd="/app",
                env=env,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                output = result.stdout
                self.log_result("Seed CLI (ADMIN_EMAIL)", True, f"CLI executed successfully. Output: {output[:200]}...")
                return True
            else:
                self.log_result("Seed CLI (ADMIN_EMAIL)", False, f"CLI failed with code {result.returncode}. Error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_result("Seed CLI (ADMIN_EMAIL)", False, "CLI execution timed out")
            return False
        except Exception as e:
            self.log_result("Seed CLI (ADMIN_EMAIL)", False, f"CLI execution error: {str(e)}")
            return False
    
    def test_seed_cli_with_admin_user_id(self):
        """Test seed CLI using ADMIN_USER_ID"""
        if not self.admin_user_id:
            self.log_result("Seed CLI (ADMIN_USER_ID)", False, "No admin user ID available")
            return False
            
        try:
            env = os.environ.copy()
            env["ADMIN_USER_ID"] = self.admin_user_id
            env["BASE_URL"] = self.base_url
            
            # Run the seed CLI
            result = subprocess.run(
                [sys.executable, "-m", "sparkpit.seed_demo"],
                cwd="/app",
                env=env,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                output = result.stdout
                self.log_result("Seed CLI (ADMIN_USER_ID)", True, f"CLI executed successfully. Output: {output[:200]}...")
                return True
            else:
                self.log_result("Seed CLI (ADMIN_USER_ID)", False, f"CLI failed with code {result.returncode}. Error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_result("Seed CLI (ADMIN_USER_ID)", False, "CLI execution timed out")
            return False
        except Exception as e:
            self.log_result("Seed CLI (ADMIN_USER_ID)", False, f"CLI execution error: {str(e)}")
            return False
    
    def verify_seed_data_created(self):
        """Verify that seed data was actually created"""
        try:
            client = MongoClient(self.mongo_url)
            db = client[self.db_name]
            
            # Check for seed rooms
            seed_rooms = list(db.rooms.find({"slug": {"$in": ["sparkpit-lab", "agent-playground", "research-pit"]}}))
            rooms_created = len(seed_rooms) > 0
            
            # Check for seed bounties with seed_v0 tag
            seed_bounties = list(db.bounties.find({"tags": "seed_v0"}))
            bounties_created = len(seed_bounties) > 0
            
            # Check for seed bot
            seed_bot = db.bots.find_one({"handle": "@openclaw-scout"})
            bot_created = seed_bot is not None
            
            self.log_result("Verify Rooms Created", rooms_created, f"Found {len(seed_rooms)} seed rooms")
            self.log_result("Verify Bounties Created", bounties_created, f"Found {len(seed_bounties)} seed bounties")
            self.log_result("Verify Bot Created", bot_created, f"Seed bot exists: {bool(seed_bot)}")
            
            return rooms_created and bounties_created and bot_created
            
        except Exception as e:
            self.log_result("Verify Seed Data", False, f"Verification error: {str(e)}")
            return False
    
    def test_bounty_workflow(self):
        """Test that at least one bounty was claimed, submitted, and approved"""
        try:
            client = MongoClient(self.mongo_url)
            db = client[self.db_name]
            
            # Check for bounties with different statuses
            claimed_bounties = list(db.bounties.find({"tags": "seed_v0", "status": "claimed"}))
            submitted_bounties = list(db.bounties.find({"tags": "seed_v0", "status": "submitted"}))
            approved_bounties = list(db.bounties.find({"tags": "seed_v0", "status": "approved"}))
            
            claimed_success = len(claimed_bounties) > 0
            submitted_success = len(submitted_bounties) > 0 or len(approved_bounties) > 0
            approved_success = len(approved_bounties) > 0
            
            self.log_result("Bounty Claimed", claimed_success, f"Found {len(claimed_bounties)} claimed bounties")
            self.log_result("Bounty Submitted", submitted_success, f"Found {len(submitted_bounties)} submitted bounties")
            self.log_result("Bounty Approved", approved_success, f"Found {len(approved_bounties)} approved bounties")
            
            return claimed_success or submitted_success or approved_success
            
        except Exception as e:
            self.log_result("Test Bounty Workflow", False, f"Workflow test error: {str(e)}")
            return False
    
    def test_bot_room_membership(self):
        """Test that bot was added to a room"""
        try:
            client = MongoClient(self.mongo_url)
            db = client[self.db_name]
            
            # Find the seed bot
            seed_bot = db.bots.find_one({"handle": "@openclaw-scout"})
            if not seed_bot:
                self.log_result("Bot Room Membership", False, "Seed bot not found")
                return False
            
            bot_id = seed_bot.get("id")
            
            # Check room_memberships collection for bot memberships
            bot_memberships = list(db.room_memberships.find({"member_type": "bot", "member_id": bot_id}))
            
            if not bot_memberships:
                self.log_result("Bot Room Membership", False, "Bot not found in any room memberships")
                return False
            
            # Check if bot is member of any seed rooms
            seed_room_ids = []
            seed_rooms = list(db.rooms.find({"slug": {"$in": ["sparkpit-lab", "agent-playground", "research-pit"]}}))
            for room in seed_rooms:
                seed_room_ids.append(room.get("id"))
            
            bot_in_seed_room = False
            joined_rooms = []
            
            for membership in bot_memberships:
                room_id = membership.get("room_id")
                joined_rooms.append(room_id)
                if room_id in seed_room_ids:
                    bot_in_seed_room = True
            
            self.log_result("Bot Room Membership", bot_in_seed_room, 
                          f"Bot joined {len(bot_memberships)} rooms, including seed room: {bot_in_seed_room}")
            return bot_in_seed_room
            
        except Exception as e:
            self.log_result("Bot Room Membership", False, f"Bot membership test error: {str(e)}")
            return False
    
    def test_idempotency(self):
        """Test that running seed CLI multiple times is idempotent"""
        if not self.admin_email:
            self.log_result("Idempotency Test", False, "No admin email for idempotency test")
            return False
            
        try:
            # Get initial counts
            client = MongoClient(self.mongo_url)
            db = client[self.db_name]
            
            initial_rooms = db.rooms.count_documents({"slug": {"$in": ["sparkpit-lab", "agent-playground", "research-pit"]}})
            initial_bounties = db.bounties.count_documents({"tags": "seed_v0"})
            initial_bots = db.bots.count_documents({"handle": "@openclaw-scout"})
            
            # Run seed CLI again
            env = os.environ.copy()
            env["ADMIN_EMAIL"] = self.admin_email
            env["BASE_URL"] = self.base_url
            
            result = subprocess.run(
                [sys.executable, "-m", "sparkpit.seed_demo"],
                cwd="/app",
                env=env,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                self.log_result("Idempotency Test", False, f"Second run failed: {result.stderr}")
                return False
            
            # Check final counts
            final_rooms = db.rooms.count_documents({"slug": {"$in": ["sparkpit-lab", "agent-playground", "research-pit"]}})
            final_bounties = db.bounties.count_documents({"tags": "seed_v0"})
            final_bots = db.bots.count_documents({"handle": "@openclaw-scout"})
            
            idempotent = (initial_rooms == final_rooms and 
                         initial_bounties == final_bounties and 
                         initial_bots == final_bots)
            
            self.log_result("Idempotency Test", idempotent, 
                          f"Counts unchanged: rooms {initial_rooms}→{final_rooms}, "
                          f"bounties {initial_bounties}→{final_bounties}, "
                          f"bots {initial_bots}→{final_bots}")
            return idempotent
            
        except Exception as e:
            self.log_result("Idempotency Test", False, f"Idempotency test error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all seed demo tests"""
        print("🚀 Starting Seed Demo CLI Tests...")
        print(f"Base URL: {self.base_url}")
        
        # Test 1: Find admin user
        if not self.find_admin_user():
            print("❌ Cannot proceed without admin user")
            return False
        
        # Test 2: Run seed CLI with ADMIN_EMAIL
        self.test_seed_cli_with_admin_email()
        
        # Test 3: Run seed CLI with ADMIN_USER_ID  
        self.test_seed_cli_with_admin_user_id()
        
        # Test 4: Verify seed data was created
        self.verify_seed_data_created()
        
        # Test 5: Test bounty workflow
        self.test_bounty_workflow()
        
        # Test 6: Test bot room membership
        self.test_bot_room_membership()
        
        # Test 7: Test idempotency
        self.test_idempotency()
        
        # Print summary
        print(f"\n📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return True
        else:
            print("❌ Some tests failed")
            return False

def main():
    tester = SeedDemoTester()
    success = tester.run_all_tests()
    
    # Save results to file
    results_file = "/app/seed_demo_test_results.json"
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "tests_run": tester.tests_run,
            "tests_passed": tester.tests_passed,
            "success_rate": tester.tests_passed / tester.tests_run if tester.tests_run > 0 else 0,
            "results": tester.results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())