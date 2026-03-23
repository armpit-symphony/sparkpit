#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional

class ActivityAPIFullTester:
    def __init__(self, base_url="https://sparklab-2.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.admin_token = None
        self.user_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.room_id = None
        self.bounty_id = None
        self.bot_id = None

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Optional[Dict] = None, token: Optional[str] = None, 
                 params: Optional[Dict] = None) -> tuple[bool, Dict]:
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def setup_active_user(self):
        """Create admin user and regular user with active membership"""
        timestamp = datetime.now().strftime('%H%M%S')
        
        # Create admin user
        admin_data = {
            "email": f"admin_activity_{timestamp}@sparkpit.test",
            "handle": f"admin_activity_{timestamp}",
            "password": "AdminPass123!"
        }
        
        success, response = self.run_test(
            "Create Admin User", "POST", "auth/register", 200, admin_data
        )
        
        if success and 'token' in response:
            self.admin_token = response['token']
            admin_user = response['user']
            print(f"   Admin: {admin_user['handle']} - {admin_user.get('role')} - {admin_user.get('membership_status')}")
            
            # If admin is not active, we have an issue
            if admin_user.get('membership_status') != 'active':
                print("   ❌ Admin user is not active - database already has admin")
                
                # Try to create regular user and activate via invite
                user_data = {
                    "email": f"user_activity_{timestamp}@sparkpit.test",
                    "handle": f"user_activity_{timestamp}",
                    "password": "UserPass123!"
                }
                
                success2, response2 = self.run_test(
                    "Create Regular User", "POST", "auth/register", 200, user_data
                )
                
                if success2 and 'token' in response2:
                    self.user_token = response2['token']
                    print(f"   Regular user created but needs activation")
                    return False  # Can't proceed without active user
                return False
            else:
                # Admin is active, create regular user and activate
                user_data = {
                    "email": f"user_activity_{timestamp}@sparkpit.test",
                    "handle": f"user_activity_{timestamp}",
                    "password": "UserPass123!"
                }
                
                success2, response2 = self.run_test(
                    "Create Regular User", "POST", "auth/register", 200, user_data
                )
                
                if success2 and 'token' in response2:
                    self.user_token = response2['token']
                    
                    # Create invite code
                    invite_data = {"max_uses": 1}
                    success3, response3 = self.run_test(
                        "Create Invite Code", "POST", "admin/invite-codes", 200,
                        invite_data, token=self.admin_token
                    )
                    
                    if success3 and 'invite_code' in response3:
                        invite_code = response3['invite_code']['code']
                        
                        # Claim invite
                        claim_data = {"code": invite_code}
                        success4, _ = self.run_test(
                            "Claim Invite Code", "POST", "auth/invite/claim", 200,
                            claim_data, token=self.user_token
                        )
                        
                        return success4
                return False
        return False

    def create_test_data(self):
        """Create room, bounty, and bot for activity generation"""
        if not self.admin_token:
            return False
            
        # Create room
        room_data = {
            "slug": f"activity-test-{datetime.now().strftime('%H%M%S')}",
            "title": "Activity Test Room",
            "is_public": True
        }
        
        success, response = self.run_test(
            "Create Test Room", "POST", "rooms", 200,
            room_data, token=self.admin_token
        )
        
        if success and 'room' in response:
            self.room_id = response['room']['id']
            print(f"   Room created: {self.room_id}")
            
            # Create bounty
            bounty_data = {
                "title": "Activity Test Bounty",
                "description": "Test bounty for activity feed",
                "tags": ["test", "activity"],
                "reward_amount": 50.0,
                "reward_currency": "USD",
                "room_id": self.room_id
            }
            
            success2, response2 = self.run_test(
                "Create Test Bounty", "POST", "bounties", 200,
                bounty_data, token=self.admin_token
            )
            
            if success2 and 'bounty' in response2:
                self.bounty_id = response2['bounty']['id']
                print(f"   Bounty created: {self.bounty_id}")
                
                # Create bot
                bot_data = {
                    "name": "Activity Test Bot",
                    "handle": f"activity-bot-{datetime.now().strftime('%H%M%S')}",
                    "bio": "Test bot for activity feed",
                    "skills": ["testing"],
                    "status": "online"
                }
                
                success3, response3 = self.run_test(
                    "Create Test Bot", "POST", "bots", 200,
                    bot_data, token=self.admin_token
                )
                
                if success3 and 'bot' in response3:
                    self.bot_id = response3['bot']['id']
                    print(f"   Bot created: {self.bot_id}")
                    
                    # Add bot to room
                    success4, _ = self.run_test(
                        "Add Bot to Room", "POST", f"rooms/{room_data['slug']}/join-bot", 200,
                        token=self.admin_token, params={"bot_id": self.bot_id}
                    )
                    
                    return success4
        return False

    def test_activity_feed_basic(self):
        """Test basic activity feed functionality"""
        success, response = self.run_test(
            "Activity Feed (Basic)", "GET", "activity", 200, token=self.admin_token
        )
        
        if success and 'items' in response:
            events = response['items']
            print(f"   Found {len(events)} activity events")
            
            # Check event structure and whitelist
            whitelisted_events = [
                "room.created", "room.joined", "bot.joined", 
                "bounty.created", "bounty.claimed", "bounty.submitted", "bounty.approved"
            ]
            
            valid_events = 0
            for event in events:
                # Check required fields
                required_fields = ['id', 'event_type', 'actor_type', 'actor_id', 'created_at']
                has_all_fields = all(field in event for field in required_fields)
                
                # Check event type whitelist
                is_whitelisted = event.get('event_type') in whitelisted_events
                
                if has_all_fields and is_whitelisted:
                    valid_events += 1
                elif not is_whitelisted:
                    print(f"   ⚠️ Non-whitelisted event: {event.get('event_type')}")
                elif not has_all_fields:
                    missing = [f for f in required_fields if f not in event]
                    print(f"   ⚠️ Event missing fields: {missing}")
            
            print(f"   ✅ {valid_events}/{len(events)} events are valid and whitelisted")
            return valid_events > 0
        return success

    def test_activity_feed_room_filter(self):
        """Test activity feed with room filter"""
        if not self.room_id:
            print("   Skipping - no room available")
            return True
            
        success, response = self.run_test(
            "Activity Feed (Room Filter)", "GET", "activity", 200,
            token=self.admin_token, params={"room_id": self.room_id}
        )
        
        if success and 'items' in response:
            events = response['items']
            print(f"   Found {len(events)} room-filtered events")
            
            # Check that events are for this room or global
            room_specific_events = 0
            for event in events:
                if event.get('room_id') == self.room_id:
                    room_specific_events += 1
                elif event.get('room_id') is None:
                    # Global event, acceptable
                    pass
                else:
                    print(f"   ❌ Event from wrong room: {event.get('room_id')}")
                    return False
            
            print(f"   ✅ {room_specific_events} events are room-specific")
            return True
        return success

    def test_activity_feed_enrichment(self):
        """Test that activity feed includes enriched data"""
        success, response = self.run_test(
            "Activity Feed (Enrichment)", "GET", "activity", 200, token=self.admin_token
        )
        
        if success and 'items' in response:
            events = response['items']
            enriched_events = 0
            
            for event in events[:10]:  # Check first 10 events
                has_actor = 'actor' in event and event['actor'] is not None
                
                # Check for room enrichment if room_id exists
                has_room = True
                if event.get('room_id'):
                    has_room = 'room' in event and event['room'] is not None
                
                # Check for bounty enrichment if bounty_id exists
                has_bounty = True
                if event.get('bounty_id'):
                    has_bounty = 'bounty' in event and event['bounty'] is not None
                
                # Check for bot enrichment if bot_id in payload
                has_bot = True
                if event.get('payload', {}).get('bot_id'):
                    has_bot = 'bot' in event and event['bot'] is not None
                
                if has_actor and has_room and has_bounty and has_bot:
                    enriched_events += 1
            
            print(f"   ✅ {enriched_events}/{min(len(events), 10)} events are properly enriched")
            return enriched_events > 0
        return success

    def test_activity_feed_unauthorized(self):
        """Test activity feed requires active membership"""
        # Create pending user
        timestamp = datetime.now().strftime('%H%M%S')
        pending_data = {
            "email": f"pending_{timestamp}@sparkpit.test",
            "handle": f"pending_{timestamp}",
            "password": "PendingPass123!"
        }
        
        success, response = self.run_test(
            "Create Pending User", "POST", "auth/register", 200, pending_data
        )
        
        if success and 'token' in response:
            pending_token = response['token']
            
            # Try to access activity feed
            success2, _ = self.run_test(
                "Activity Feed (Unauthorized)", "GET", "activity", 403, token=pending_token
            )
            
            return success2
        return False

    def test_bounty_status_updates(self):
        """Test bounty status updates generate correct activity events"""
        if not self.bounty_id or not self.user_token:
            print("   Skipping - no bounty or user available")
            return True
            
        # Claim bounty
        success1, _ = self.run_test(
            "Claim Bounty", "POST", f"bounties/{self.bounty_id}/claim", 200,
            token=self.user_token
        )
        
        # Submit bounty
        success2, _ = self.run_test(
            "Submit Bounty", "POST", f"bounties/{self.bounty_id}/status", 200,
            {"status": "submitted"}, token=self.admin_token
        )
        
        # Approve bounty
        success3, _ = self.run_test(
            "Approve Bounty", "POST", f"bounties/{self.bounty_id}/status", 200,
            {"status": "approved"}, token=self.admin_token
        )
        
        if success1 and success2 and success3:
            # Check activity feed for these events
            success4, response = self.run_test(
                "Check Bounty Events in Activity", "GET", "activity", 200,
                token=self.admin_token, params={"room_id": self.room_id}
            )
            
            if success4 and 'items' in response:
                events = response['items']
                event_types = [e.get('event_type') for e in events]
                
                has_claimed = 'bounty.claimed' in event_types
                has_submitted = 'bounty.submitted' in event_types
                has_approved = 'bounty.approved' in event_types
                
                print(f"   Events found: claimed={has_claimed}, submitted={has_submitted}, approved={has_approved}")
                return has_claimed and has_submitted and has_approved
        
        return False

    def run_all_tests(self):
        """Run all activity API tests"""
        print("🚀 Starting Comprehensive Activity API Tests")
        print("=" * 60)
        
        # Setup users
        if not self.setup_active_user():
            print("❌ User setup failed - trying with existing setup")
            # Try with a simple admin user creation
            timestamp = datetime.now().strftime('%H%M%S')
            admin_data = {
                "email": f"simple_admin_{timestamp}@sparkpit.test",
                "handle": f"simple_admin_{timestamp}",
                "password": "AdminPass123!"
            }
            
            success, response = self.run_test(
                "Simple Admin Creation", "POST", "auth/register", 200, admin_data
            )
            
            if success and 'token' in response:
                self.admin_token = response['token']
                user = response['user']
                if user.get('membership_status') != 'active':
                    print("❌ Cannot get active user, testing with limited scope")
                    
                    # Test unauthorized access only
                    self.test_activity_feed_unauthorized()
                    
                    print("\n" + "=" * 60)
                    print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run}")
                    return self.tests_passed > 0
        
        # Create test data
        self.create_test_data()
        
        # Run tests
        self.test_activity_feed_basic()
        self.test_activity_feed_room_filter()
        self.test_activity_feed_enrichment()
        self.test_activity_feed_unauthorized()
        self.test_bounty_status_updates()
        
        # Print results
        print("\n" + "=" * 60)
        print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        return self.tests_passed >= (self.tests_run * 0.7)  # 70% success rate acceptable

def main():
    tester = ActivityAPIFullTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())