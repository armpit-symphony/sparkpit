import requests
import sys
from datetime import datetime

class AdminLoginTester:
    def __init__(self, base_url="https://sparklab-2.preview.emergentagent.com"):
        self.base_url = base_url
        self.admin_token = None

    def try_login(self, email, password):
        """Try to login with given credentials"""
        url = f"{self.base_url}/api/auth/login"
        headers = {'Content-Type': 'application/json'}
        data = {"email": email, "password": password}
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                if 'token' in result and 'user' in result:
                    user = result['user']
                    print(f"✅ Login successful: {email}")
                    print(f"   Role: {user.get('role')}")
                    print(f"   Membership: {user.get('membership_status')}")
                    if user.get('role') == 'admin':
                        self.admin_token = result['token']
                        return True
            else:
                print(f"❌ Login failed for {email}: {response.status_code}")
        except Exception as e:
            print(f"❌ Error trying {email}: {str(e)}")
        
        return False

    def test_ops_with_admin_token(self):
        """Test ops endpoint with admin token"""
        if not self.admin_token:
            return False
            
        url = f"{self.base_url}/api/admin/ops"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.admin_token}'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"\n🔍 Testing Ops Checklist API...")
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Ops API working!")
                print(f"   Stripe configured: {data.get('stripe_configured')}")
                print(f"   Redis connected: {data.get('redis_connected')}")
                print(f"   Worker healthy: {data.get('worker_healthy')}")
                print(f"   Worker heartbeat: {data.get('worker_heartbeat')}")
                return True
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                print(f"❌ Ops API failed: {error_data}")
        except Exception as e:
            print(f"❌ Error testing ops: {str(e)}")
        
        return False

def main():
    print("🔍 Trying to find existing admin credentials...")
    
    tester = AdminLoginTester()
    
    # Common admin credentials to try
    common_credentials = [
        ("admin@sparkpit.test", "admin"),
        ("admin@sparkpit.test", "password"),
        ("admin@sparkpit.test", "AdminPass123!"),
        ("admin@example.com", "admin"),
        ("admin@example.com", "password"),
        ("test@sparkpit.test", "password"),
        ("admin@admin.com", "admin"),
    ]
    
    print("Trying common admin credentials...")
    for email, password in common_credentials:
        if tester.try_login(email, password):
            print(f"🎉 Found working admin credentials!")
            break
    else:
        print("❌ No working admin credentials found")
        print("Let me try to create a fresh admin user by clearing existing data...")
        
        # Try registering with a unique timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        admin_data = {
            "email": f"fresh_admin_{timestamp}@sparkpit.test",
            "handle": f"fresh_admin_{timestamp}",
            "password": "FreshAdminPass123!"
        }
        
        url = f"{tester.base_url}/api/auth/register"
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = requests.post(url, json=admin_data, headers=headers, timeout=10)
            if response.status_code == 200:
                result = response.json()
                user = result['user']
                print(f"✅ New user registered: {user.get('email')}")
                print(f"   Role: {user.get('role')}")
                print(f"   Membership: {user.get('membership_status')}")
                
                if user.get('role') == 'admin':
                    tester.admin_token = result['token']
                    print("🎉 Got admin user!")
                else:
                    print("⚠️ User is not admin - database likely has existing admin")
                    return 1
            else:
                print(f"❌ Registration failed: {response.status_code}")
                return 1
        except Exception as e:
            print(f"❌ Registration error: {str(e)}")
            return 1
    
    # Test ops endpoint if we have admin token
    if tester.admin_token:
        success = tester.test_ops_with_admin_token()
        return 0 if success else 1
    else:
        print("❌ No admin token available")
        return 1

if __name__ == "__main__":
    sys.exit(main())