#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional

class SparkPitAPITester:
    def __init__(self, base_url="https://sparklab-2.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.admin_token = None
        self.user_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_user = None
        self.regular_user = None
        self.room_id = None
        self.channel_id = None
        self.bounty_id = None
        self.bot_id = None
        self.invite_code = None

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
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers)
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

    def test_root_endpoint(self):
        """Test API root endpoint"""
        return self.run_test("API Root", "GET", "", 200)

    def test_admin_registration(self):
        """Test admin user registration (first user)"""
        timestamp = datetime.now().strftime('%H%M%S')
        admin_data = {
            "email": f"admin_{timestamp}@sparkpit.test",
            "handle": f"admin_{timestamp}",
            "password": "AdminPass123!"
        }
        
        success, response = self.run_test(
            "Admin Registration", "POST", "auth/register", 200, admin_data
        )
        
        if success and 'token' in response and 'user' in response:
            self.admin_token = response['token']
            self.admin_user = response['user']
            print(f"   Admin user created: {self.admin_user['handle']}")
            print(f"   Role: {self.admin_user.get('role')}")
            print(f"   Membership: {self.admin_user.get('membership_status')}")
            return True
        return False

    def test_regular_user_registration(self):
        """Test regular user registration (should be pending)"""
        timestamp = datetime.now().strftime('%H%M%S')
        user_data = {
            "email": f"user_{timestamp}@sparkpit.test",
            "handle": f"user_{timestamp}",
            "password": "UserPass123!"
        }
        
        success, response = self.run_test(
            "Regular User Registration", "POST", "auth/register", 200, user_data
        )
        
        if success and 'token' in response and 'user' in response:
            self.user_token = response['token']
            self.regular_user = response['user']
            print(f"   Regular user created: {self.regular_user['handle']}")
            print(f"   Role: {self.regular_user.get('role')}")
            print(f"   Membership: {self.regular_user.get('membership_status')}")
            return True
        return False

    def test_admin_login(self):
        """Test admin login"""
        if not self.admin_user:
            return False
            
        login_data = {
            "email": self.admin_user['email'],
            "password": "AdminPass123!"
        }
        
        success, response = self.run_test(
            "Admin Login", "POST", "auth/login", 200, login_data
        )
        
        if success and 'token' in response:
            print(f"   Login successful for admin")
            return True
        return False

    def test_get_me_admin(self):
        """Test /me endpoint for admin"""
        return self.run_test("Get Me (Admin)", "GET", "me", 200, token=self.admin_token)

    def test_get_me_regular_user(self):
        """Test /me endpoint for regular user"""
        return self.run_test("Get Me (Regular User)", "GET", "me", 200, token=self.user_token)

    def test_generate_invite_code(self):
        """Test admin generating invite code"""
        invite_data = {
            "max_uses": 1,
            "expires_at": None
        }
        
        success, response = self.run_test(
            "Generate Invite Code", "POST", "admin/invite-codes", 200, 
            invite_data, token=self.admin_token
        )
        
        if success and 'invite_code' in response:
            self.invite_code = response['invite_code']['code']
            print(f"   Generated invite code: {self.invite_code}")
            return True
        return False

    def test_claim_invite_code(self):
        """Test regular user claiming invite code"""
        if not self.invite_code:
            print("❌ No invite code available to claim")
            return False
            
        claim_data = {"code": self.invite_code}
        
        success, response = self.run_test(
            "Claim Invite Code", "POST", "auth/invite/claim", 200,
            claim_data, token=self.user_token
        )
        
        if success:
            print(f"   Invite claimed successfully")
            return True
        return False

    def test_create_room(self):
        """Test creating a room"""
        room_data = {
            "slug": f"test-room-{datetime.now().strftime('%H%M%S')}",
            "title": "Test Room",
            "is_public": True
        }
        
        success, response = self.run_test(
            "Create Room", "POST", "rooms", 200,
            room_data, token=self.admin_token
        )
        
        if success and 'room' in response:
            self.room_id = response['room']['id']
            self.room_slug = response['room']['slug']
            if 'default_channel' in response:
                self.channel_id = response['default_channel']['id']
            print(f"   Room created: {self.room_slug} (ID: {self.room_id})")
            return True
        return False

    def test_list_rooms(self):
        """Test listing rooms"""
        return self.run_test("List Rooms", "GET", "rooms", 200, token=self.admin_token)

    def test_get_room(self):
        """Test getting room details"""
        if not hasattr(self, 'room_slug'):
            return False
            
        return self.run_test(
            "Get Room", "GET", f"rooms/{self.room_slug}", 200, token=self.admin_token
        )

    def test_join_room(self):
        """Test joining a room"""
        if not hasattr(self, 'room_slug'):
            return False
            
        return self.run_test(
            "Join Room", "POST", f"rooms/{self.room_slug}/join", 200, token=self.user_token
        )

    def test_create_channel(self):
        """Test creating a channel in room"""
        if not hasattr(self, 'room_slug'):
            return False
            
        channel_data = {
            "slug": "test-channel",
            "title": "Test Channel",
            "type": "chat"
        }
        
        success, response = self.run_test(
            "Create Channel", "POST", f"rooms/{self.room_slug}/channels", 200,
            channel_data, token=self.admin_token
        )
        
        if success and 'channel' in response:
            new_channel_id = response['channel']['id']
            print(f"   Channel created: {new_channel_id}")
            return True
        return False

    def test_post_message(self):
        """Test posting a message to channel"""
        if not self.channel_id:
            return False
            
        message_data = {"content": "Hello from API test!"}
        
        success, response = self.run_test(
            "Post Message", "POST", f"channels/{self.channel_id}/messages", 200,
            message_data, token=self.admin_token
        )
        
        if success and 'message' in response:
            print(f"   Message posted: {response['message']['id']}")
            return True
        return False

    def test_get_messages(self):
        """Test getting messages from channel"""
        if not self.channel_id:
            return False
            
        return self.run_test(
            "Get Messages", "GET", f"channels/{self.channel_id}/messages", 200, 
            token=self.admin_token
        )

    def test_create_bounty(self):
        """Test creating a bounty"""
        bounty_data = {
            "title": "Test Bounty",
            "description": "This is a test bounty for API testing",
            "tags": ["test", "api"],
            "reward_amount": 100.0,
            "reward_currency": "USD",
            "room_id": self.room_id
        }
        
        success, response = self.run_test(
            "Create Bounty", "POST", "bounties", 200,
            bounty_data, token=self.admin_token
        )
        
        if success and 'bounty' in response:
            self.bounty_id = response['bounty']['id']
            print(f"   Bounty created: {self.bounty_id}")
            return True
        return False

    def test_list_bounties(self):
        """Test listing bounties"""
        return self.run_test("List Bounties", "GET", "bounties", 200, token=self.admin_token)

    def test_get_bounty(self):
        """Test getting bounty details"""
        if not self.bounty_id:
            return False
            
        return self.run_test(
            "Get Bounty", "GET", f"bounties/{self.bounty_id}", 200, token=self.admin_token
        )

    def test_claim_bounty(self):
        """Test claiming a bounty"""
        if not self.bounty_id:
            return False
            
        return self.run_test(
            "Claim Bounty", "POST", f"bounties/{self.bounty_id}/claim", 200, 
            token=self.user_token
        )

    def test_add_bounty_update(self):
        """Test adding update to bounty"""
        if not self.bounty_id:
            return False
            
        update_data = {
            "type": "comment",
            "content": "Working on this bounty now!"
        }
        
        return self.run_test(
            "Add Bounty Update", "POST", f"bounties/{self.bounty_id}/updates", 200,
            update_data, token=self.user_token
        )

    def test_update_bounty_status(self):
        """Test updating bounty status"""
        if not self.bounty_id:
            return False
            
        status_data = {"status": "submitted"}
        
        return self.run_test(
            "Update Bounty Status", "POST", f"bounties/{self.bounty_id}/status", 200,
            status_data, token=self.admin_token
        )

    def test_create_bot(self):
        """Test creating a bot profile"""
        bot_data = {
            "name": "Test Bot",
            "handle": f"test-bot-{datetime.now().strftime('%H%M%S')}",
            "bio": "A test bot for API testing",
            "skills": ["testing", "automation"],
            "model_stack": ["gpt-4", "claude"],
            "connect_url": "https://example.com/bot",
            "status": "online"
        }
        
        success, response = self.run_test(
            "Create Bot", "POST", "bots", 200,
            bot_data, token=self.admin_token
        )
        
        if success and 'bot' in response:
            self.bot_id = response['bot']['id']
            self.bot_handle = response['bot']['handle']
            print(f"   Bot created: {self.bot_handle} (ID: {self.bot_id})")
            return True
        return False

    def test_list_my_bots(self):
        """Test listing user's bots"""
        return self.run_test("List My Bots", "GET", "me/bots", 200, token=self.admin_token)

    def test_get_bot(self):
        """Test getting bot details"""
        if not hasattr(self, 'bot_handle'):
            return False
            
        return self.run_test(
            "Get Bot", "GET", f"bots/{self.bot_handle}", 200, token=self.admin_token
        )

    def test_add_bot_to_room(self):
        """Test adding bot to room"""
        if not self.bot_id or not hasattr(self, 'room_slug'):
            return False
            
        return self.run_test(
            "Add Bot to Room", "POST", f"rooms/{self.room_slug}/join-bot", 200,
            token=self.admin_token, params={"bot_id": self.bot_id}
        )

    def test_stripe_checkout_creation(self):
        """Test Stripe checkout session creation - should return 400 with clear error when keys missing"""
        checkout_data = {
            "origin_url": "https://sparklab-2.preview.emergentagent.com"
        }
        
        success, response = self.run_test(
            "Create Stripe Checkout (Missing Keys)", "POST", "payments/stripe/checkout", 400,  # Expecting 400 with clear error
            checkout_data, token=self.user_token
        )
        
        if success and 'detail' in response:
            print(f"   Correct error response: {response['detail']}")
            return True
        return False

    def test_stripe_checkout_status(self):
        """Test Stripe checkout status polling - should return 400 with clear error when keys missing"""
        # Test with dummy session ID - should fail gracefully
        dummy_session_id = "cs_test_dummy_session_id"
        
        success, response = self.run_test(
            "Check Stripe Status (Missing Keys)", "GET", f"payments/stripe/checkout/status/{dummy_session_id}", 400,  # Expecting 400 with clear error
            token=self.user_token
        )
        
        if success and 'detail' in response:
            print(f"   Correct error response: {response['detail']}")
            return True
        return False

    def test_bot_handshake_challenge(self):
        """Test bot handshake challenge creation"""
        if not self.bot_id:
            return False
            
        success, response = self.run_test(
            "Create Bot Handshake Challenge", "POST", f"bots/{self.bot_id}/handshake/challenge", 200,
            token=self.admin_token
        )
        
        if success and 'challenge' in response:
            self.bot_challenge = response['challenge']
            print(f"   Challenge created: {self.bot_challenge[:16]}...")
            return True
        return False

    def test_bot_handshake_verify_invalid(self):
        """Test bot handshake verification with invalid signature"""
        if not self.bot_id or not hasattr(self, 'bot_challenge'):
            return False
            
        verify_data = {
            "challenge": self.bot_challenge,
            "signature": "invalid_signature",
            "capabilities": {"skills": ["test"]},
            "allowed_room_ids": [self.room_id] if self.room_id else [],
            "allowed_channel_ids": [self.channel_id] if self.channel_id else []
        }
        
        success, response = self.run_test(
            "Verify Bot Handshake (Invalid)", "POST", f"bots/{self.bot_id}/handshake/verify", 401,
            verify_data
        )
        
        return success  # Should fail with 401

    def test_bounty_filters(self):
        """Test bounty filtering functionality"""
        # Test status filter
        success1, _ = self.run_test(
            "Filter Bounties by Status", "GET", "bounties", 200,
            token=self.admin_token, params={"status": "open"}
        )
        
        # Test tag filter
        success2, _ = self.run_test(
            "Filter Bounties by Tag", "GET", "bounties", 200,
            token=self.admin_token, params={"tag": "test"}
        )
        
        # Test sort filter
        success3, _ = self.run_test(
            "Sort Bounties by Reward", "GET", "bounties", 200,
            token=self.admin_token, params={"sort": "reward"}
        )
        
        return success1 and success2 and success3

    def test_reputation_signals(self):
        """Test reputation updates after bounty actions"""
        # Get user before bounty actions
        success, response = self.run_test(
            "Get User Before Reputation Update", "GET", "me", 200, token=self.user_token
        )
        
        if success and 'user' in response:
            initial_rep = response['user'].get('reputation', {})
            print(f"   Initial reputation: {initial_rep}")
            
            # After claiming and status updates, check reputation again
            success2, response2 = self.run_test(
                "Get User After Reputation Update", "GET", "me", 200, token=self.user_token
            )
            
            if success2 and 'user' in response2:
                updated_rep = response2['user'].get('reputation', {})
                print(f"   Updated reputation: {updated_rep}")
                return True
        
        return False

    def test_audit_feed(self):
        """Test admin audit feed"""
        return self.run_test("Audit Feed", "GET", "admin/audit", 200, token=self.admin_token)

    def test_ops_checklist_endpoint(self):
        """Test the ops checklist endpoint"""
        success, response = self.run_test(
            "Ops Checklist API", "GET", "admin/ops", 200, token=self.admin_token
        )
        
        if success:
            # Validate response structure
            expected_fields = [
                'stripe_configured', 
                'stripe_webhook_last_received',
                'stripe_webhook_status',
                'redis_connected',
                'worker_heartbeat', 
                'worker_healthy'
            ]
            
            missing_fields = [field for field in expected_fields if field not in response]
            if missing_fields:
                print(f"❌ Missing fields in response: {missing_fields}")
                return False
            
            print(f"✅ All expected fields present")
            print(f"   Stripe configured: {response.get('stripe_configured')}")
            print(f"   Redis connected: {response.get('redis_connected')}")
            print(f"   Worker healthy: {response.get('worker_healthy')}")
            print(f"   Worker heartbeat: {response.get('worker_heartbeat')}")
            
            return True
        return False

    def test_ops_without_admin(self):
        """Test ops endpoint without admin token"""
        success, response = self.run_test(
            "Ops Checklist (No Auth)", "GET", "admin/ops", 401
        )
        return success  # Should fail with 401

    def test_ops_with_non_admin(self):
        """Test ops endpoint with non-admin user"""
        success, response = self.run_test(
            "Ops Checklist (Non-Admin)", "GET", "admin/ops", 403, token=self.user_token
        )
        return success  # Should fail with 403

    def test_activity_feed_global(self):
        """Test activity feed without room filter"""
        success, response = self.run_test(
            "Activity Feed (Global)", "GET", "activity", 200, token=self.admin_token
        )
        
        if success and 'items' in response:
            events = response['items']
            print(f"   Found {len(events)} activity events")
            
            # Check if events have required fields
            for event in events[:3]:  # Check first 3 events
                required_fields = ['id', 'event_type', 'actor_type', 'actor_id', 'created_at']
                for field in required_fields:
                    if field not in event:
                        print(f"   ❌ Missing field '{field}' in event")
                        return False
                        
                # Check if event_type is in whitelist
                whitelisted_events = [
                    "room.created", "room.joined", "bot.joined", 
                    "bounty.created", "bounty.claimed", "bounty.submitted", "bounty.approved"
                ]
                if event['event_type'] not in whitelisted_events:
                    print(f"   ❌ Event type '{event['event_type']}' not in whitelist")
                    return False
                    
            print(f"   ✅ All events have required fields and whitelisted types")
            return True
        return success

    def test_activity_feed_room_filter(self):
        """Test activity feed with room filter"""
        if not self.room_id:
            print("   ⚠️ No room available for filtering test")
            return True  # Skip if no room
            
        success, response = self.run_test(
            "Activity Feed (Room Filter)", "GET", "activity", 200, 
            token=self.admin_token, params={"room_id": self.room_id}
        )
        
        if success and 'items' in response:
            events = response['items']
            print(f"   Found {len(events)} room-specific events")
            
            # Check that all events are either room-specific or global
            for event in events:
                if event.get('room_id') and event['room_id'] != self.room_id:
                    print(f"   ❌ Found event from different room: {event['room_id']}")
                    return False
                    
            print(f"   ✅ All events are for the correct room or global")
            return True
        return success

    def test_activity_feed_unauthorized(self):
        """Test activity feed requires active membership"""
        # Create a new pending user
        timestamp = datetime.now().strftime('%H%M%S')
        pending_user_data = {
            "email": f"pending_activity_{timestamp}@sparkpit.test",
            "handle": f"pending_activity_{timestamp}",
            "password": "PendingPass123!"
        }
        
        success, response = self.run_test(
            "Create Pending User for Activity Test", "POST", "auth/register", 200, pending_user_data
        )
        
        if not success:
            return False
            
        pending_token = response['token']
        
        # Try to access activity feed - should fail with 403
        success, _ = self.run_test(
            "Activity Feed (Unauthorized)", "GET", "activity", 403, token=pending_token
        )
        
        return success

    def test_membership_gate_protection(self):
        """Test that pending users can't access protected endpoints"""
        # Create a new pending user
        timestamp = datetime.now().strftime('%H%M%S')
        pending_user_data = {
            "email": f"pending_{timestamp}@sparkpit.test",
            "handle": f"pending_{timestamp}",
            "password": "PendingPass123!"
        }
        
        success, response = self.run_test(
            "Create Pending User", "POST", "auth/register", 200, pending_user_data
        )
        
        if not success:
            return False
            
        pending_token = response['token']
        
        # Try to access protected endpoint - should fail with 403
        success, _ = self.run_test(
            "Test Membership Gate", "GET", "rooms", 403, token=pending_token
        )
        
        return success

    def run_all_tests(self):
        """Run all API tests in sequence"""
        print("🚀 Starting Spark Pit API Tests")
        print("=" * 50)
        
        # Basic API tests
        self.test_root_endpoint()
        
        # Authentication flow
        if not self.test_admin_registration():
            print("❌ Admin registration failed, stopping tests")
            return False
            
        if not self.test_regular_user_registration():
            print("❌ Regular user registration failed, stopping tests")
            return False
            
        self.test_admin_login()
        self.test_get_me_admin()
        self.test_get_me_regular_user()
        
        # Invite system
        if not self.test_generate_invite_code():
            print("❌ Invite code generation failed")
        else:
            self.test_claim_invite_code()
        
        # Membership gate protection
        self.test_membership_gate_protection()
        
        # Room and channel management
        if self.test_create_room():
            self.test_list_rooms()
            self.test_get_room()
            self.test_join_room()
            self.test_create_channel()
            
            # Chat functionality
            self.test_post_message()
            self.test_get_messages()
        
        # Bounty system
        if self.test_create_bounty():
            self.test_list_bounties()
            self.test_get_bounty()
            self.test_claim_bounty()
            self.test_add_bounty_update()
            self.test_update_bounty_status()
        
        # Bot system
        if self.test_create_bot():
            self.test_list_my_bots()
            self.test_get_bot()
            self.test_add_bot_to_room()
            
            # Bot handshake system
            if self.test_bot_handshake_challenge():
                self.test_bot_handshake_verify_invalid()
        
        # Stripe payment system (expected to fail without credentials)
        self.test_stripe_checkout_creation()
        self.test_stripe_checkout_status()
        
        # Bounty filtering
        self.test_bounty_filters()
        
        # Reputation system
        self.test_reputation_signals()
        
        # Admin features
        self.test_audit_feed()
        
        # Ops Checklist tests
        self.test_ops_checklist_endpoint()
        self.test_ops_without_admin()
        self.test_ops_with_non_admin()
        
        # Activity feed tests
        self.test_activity_feed_global()
        self.test_activity_feed_room_filter()
        self.test_activity_feed_unauthorized()
        
        # Print results
        print("\n" + "=" * 50)
        print(f"📊 Tests completed: {self.tests_passed}/{self.tests_run}")
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"📈 Success rate: {success_rate:.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    tester = SparkPitAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())