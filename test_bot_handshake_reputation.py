#!/usr/bin/env python3

import requests
import sys
import hmac
import hashlib
from datetime import datetime

def test_bot_handshake_and_reputation():
    """Test bot handshake flow and reputation updates"""
    base_url = "https://sparklab-2.preview.emergentagent.com/api"
    
    print("🔍 Testing bot handshake and reputation functionality...")
    
    # First, create an admin user
    timestamp = datetime.now().strftime('%H%M%S%f')
    admin_data = {
        "email": f"bot_test_admin_{timestamp}@sparkpit.test",
        "handle": f"bot_test_admin_{timestamp}",
        "password": "AdminPass123!"
    }
    
    try:
        # Register admin
        response = requests.post(f"{base_url}/auth/register", json=admin_data)
        if response.status_code != 200:
            print(f"❌ Admin registration failed: {response.status_code}")
            return False
        
        admin_token = response.json()['token']
        admin_user = response.json()['user']
        print(f"✅ Admin user created: {admin_user['handle']}")
        
        # Create a regular user for reputation testing
        user_data = {
            "email": f"rep_test_user_{timestamp}@sparkpit.test",
            "handle": f"rep_test_user_{timestamp}",
            "password": "UserPass123!"
        }
        
        response = requests.post(f"{base_url}/auth/register", json=user_data)
        if response.status_code != 200:
            print(f"❌ User registration failed: {response.status_code}")
            return False
        
        user_token = response.json()['token']
        user_id = response.json()['user']['id']
        print(f"✅ Regular user created for reputation testing")
        
        # Activate user membership with invite code
        invite_data = {"max_uses": 1}
        response = requests.post(f"{base_url}/admin/invite-codes", json=invite_data, 
                               headers={'Authorization': f'Bearer {admin_token}'})
        if response.status_code == 200:
            invite_code = response.json()['invite_code']['code']
            
            # Claim invite
            claim_data = {"code": invite_code}
            response = requests.post(f"{base_url}/auth/invite/claim", json=claim_data,
                                   headers={'Authorization': f'Bearer {user_token}'})
            if response.status_code == 200:
                print("✅ User membership activated")
            else:
                print(f"⚠️  Could not activate user membership: {response.status_code}")
        
        # Create a bot
        bot_data = {
            "name": "Test Handshake Bot",
            "handle": f"test-handshake-bot-{timestamp}",
            "bio": "A test bot for handshake verification",
            "skills": ["testing", "automation"],
            "model_stack": ["gpt-4"],
            "connect_url": "https://example.com/bot"
        }
        
        response = requests.post(f"{base_url}/bots", json=bot_data,
                               headers={'Authorization': f'Bearer {admin_token}'})
        if response.status_code != 200:
            print(f"❌ Bot creation failed: {response.status_code}")
            return False
        
        bot_data_response = response.json()
        bot_id = bot_data_response['bot']['id']
        bot_secret = bot_data_response['bot_secret']
        print(f"✅ Bot created: {bot_id}")
        print(f"✅ Bot secret received: {bot_secret[:16]}...")
        
        # Test bot handshake challenge creation
        response = requests.post(f"{base_url}/bots/{bot_id}/handshake/challenge",
                               headers={'Authorization': f'Bearer {admin_token}'})
        if response.status_code != 200:
            print(f"❌ Handshake challenge creation failed: {response.status_code}")
            return False
        
        challenge_data = response.json()
        challenge = challenge_data['challenge']
        print(f"✅ Handshake challenge created: {challenge[:16]}...")
        
        # Test bot handshake verification with correct signature
        signature = hmac.new(bot_secret.encode(), challenge.encode(), hashlib.sha256).hexdigest()
        
        verify_data = {
            "challenge": challenge,
            "signature": signature,
            "capabilities": {"skills": ["testing", "automation"]},
            "allowed_room_ids": [],
            "allowed_channel_ids": []
        }
        
        response = requests.post(f"{base_url}/bots/{bot_id}/handshake/verify", json=verify_data)
        if response.status_code != 200:
            print(f"❌ Bot handshake verification failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        verify_response = response.json()
        bot_token = verify_response['bot_token']
        print(f"✅ Bot handshake verified successfully")
        print(f"✅ Bot token received: {bot_token[:50]}...")
        
        # Test reputation updates with bounty workflow
        print("🔍 Testing reputation updates...")
        
        # Create a bounty
        bounty_data = {
            "title": "Test Bounty for Reputation",
            "description": "Testing reputation updates",
            "tags": ["test", "reputation"],
            "reward_amount": 100.0,
            "reward_currency": "USD"
        }
        
        response = requests.post(f"{base_url}/bounties", json=bounty_data,
                               headers={'Authorization': f'Bearer {admin_token}'})
        if response.status_code != 200:
            print(f"❌ Bounty creation failed: {response.status_code}")
            return False
        
        bounty_id = response.json()['bounty']['id']
        print(f"✅ Bounty created: {bounty_id}")
        
        # Get initial reputation
        response = requests.get(f"{base_url}/me", headers={'Authorization': f'Bearer {user_token}'})
        if response.status_code == 200:
            initial_rep = response.json()['user'].get('reputation', {})
            print(f"✅ Initial reputation: {initial_rep}")
        
        # Claim bounty (should update bounties_claimed)
        response = requests.post(f"{base_url}/bounties/{bounty_id}/claim",
                               headers={'Authorization': f'Bearer {user_token}'})
        if response.status_code == 200:
            print("✅ Bounty claimed successfully")
        else:
            print(f"⚠️  Bounty claim failed: {response.status_code}")
        
        # Update bounty status to submitted (should update bounties_submitted)
        status_data = {"status": "submitted"}
        response = requests.post(f"{base_url}/bounties/{bounty_id}/status", json=status_data,
                               headers={'Authorization': f'Bearer {admin_token}'})
        if response.status_code == 200:
            print("✅ Bounty status updated to submitted")
        else:
            print(f"⚠️  Bounty status update failed: {response.status_code}")
        
        # Update bounty status to approved (should update bounties_approved)
        status_data = {"status": "approved"}
        response = requests.post(f"{base_url}/bounties/{bounty_id}/status", json=status_data,
                               headers={'Authorization': f'Bearer {admin_token}'})
        if response.status_code == 200:
            print("✅ Bounty status updated to approved")
        else:
            print(f"⚠️  Bounty status update failed: {response.status_code}")
        
        # Get updated reputation
        response = requests.get(f"{base_url}/me", headers={'Authorization': f'Bearer {user_token}'})
        if response.status_code == 200:
            updated_rep = response.json()['user'].get('reputation', {})
            print(f"✅ Updated reputation: {updated_rep}")
            
            # Check if reputation was updated correctly
            if (updated_rep.get('bounties_claimed', 0) > initial_rep.get('bounties_claimed', 0) and
                updated_rep.get('bounties_submitted', 0) > initial_rep.get('bounties_submitted', 0) and
                updated_rep.get('bounties_approved', 0) > initial_rep.get('bounties_approved', 0)):
                print("✅ PASS: Reputation updates working correctly")
                return True
            else:
                print("❌ FAIL: Reputation not updated as expected")
                return False
        else:
            print(f"❌ Could not get updated reputation: {response.status_code}")
            return False
        
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_bot_handshake_and_reputation()
    sys.exit(0 if success else 1)