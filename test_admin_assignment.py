#!/usr/bin/env python3

import requests
import sys
from datetime import datetime

def test_admin_assignment():
    """Test that first user gets admin role and active membership"""
    base_url = "https://sparklab-2.preview.emergentagent.com/api"
    
    print("🔍 Testing admin assignment when no admin exists...")
    
    # Register first user
    timestamp = datetime.now().strftime('%H%M%S%f')
    admin_data = {
        "email": f"first_admin_{timestamp}@sparkpit.test",
        "handle": f"first_admin_{timestamp}",
        "password": "AdminPass123!"
    }
    
    try:
        response = requests.post(f"{base_url}/auth/register", json=admin_data)
        print(f"Registration response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            user = data.get('user', {})
            
            print(f"✅ User created successfully")
            print(f"   Email: {user.get('email')}")
            print(f"   Handle: {user.get('handle')}")
            print(f"   Role: {user.get('role')}")
            print(f"   Membership Status: {user.get('membership_status')}")
            
            # Check if user got admin role and active membership
            if user.get('role') == 'admin' and user.get('membership_status') == 'active':
                print("✅ PASS: First user correctly assigned admin role with active membership")
                return True
            else:
                print("❌ FAIL: First user did not get admin role or active membership")
                return False
        else:
            print(f"❌ Registration failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error during test: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_admin_assignment()
    sys.exit(0 if success else 1)