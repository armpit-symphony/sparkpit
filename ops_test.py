import requests
import sys
from datetime import datetime

class OpsChecklistTester:
    def __init__(self, base_url="https://sparklab-2.preview.emergentagent.com"):
        self.base_url = base_url
        self.admin_token = None
        self.tests_run = 0
        self.tests_passed = 0

    def run_test(self, name, method, endpoint, expected_status, data=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.admin_token:
            headers['Authorization'] = f'Bearer {self.admin_token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)

            print(f"   Response Status: {response.status_code}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def setup_admin_user(self):
        """Setup admin user with proper permissions"""
        print("🔧 Setting up admin user...")
        
        # Try to register as first admin user
        timestamp = datetime.now().strftime('%H%M%S')
        admin_data = {
            "email": f"admin_{timestamp}@sparkpit.test",
            "handle": f"admin_{timestamp}",
            "password": "AdminPass123!"
        }
        
        success, response = self.run_test(
            "Register Admin User",
            "POST",
            "auth/register", 
            200,
            data=admin_data
        )
        
        if success and 'token' in response and 'user' in response:
            self.admin_token = response['token']
            user = response['user']
            print(f"   User registered: {user.get('email')}")
            print(f"   Role: {user.get('role')}")
            print(f"   Membership: {user.get('membership_status')}")
            
            # Check if user is admin and has active membership
            if user.get('role') == 'admin' and user.get('membership_status') == 'active':
                print("✅ Admin user ready")
                return True
            elif user.get('role') == 'admin':
                print("⚠️ Admin user created but membership is pending")
                return True
            else:
                print("⚠️ User created but not admin (database may have existing admin)")
                return True
        
        return False

    def test_ops_checklist_api(self):
        """Test the ops checklist API endpoint"""
        success, response = self.run_test(
            "Ops Checklist API",
            "GET",
            "admin/ops",
            200
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
            print(f"   Stripe webhook status: {response.get('stripe_webhook_status')}")
            print(f"   Redis connected: {response.get('redis_connected')}")
            print(f"   Worker healthy: {response.get('worker_healthy')}")
            print(f"   Worker heartbeat: {response.get('worker_heartbeat')}")
            
            # Check if Redis and worker are working
            if response.get('redis_connected'):
                print("✅ Redis is connected")
            else:
                print("⚠️ Redis is not connected")
                
            if response.get('worker_healthy'):
                print("✅ Worker heartbeat is healthy")
            else:
                print("⚠️ Worker heartbeat is stale or missing")
            
            return True
        return False

    def test_ops_auth_protection(self):
        """Test that ops endpoint requires admin auth"""
        # Test without token
        temp_token = self.admin_token
        self.admin_token = None
        
        success, _ = self.run_test(
            "Ops API (No Auth)",
            "GET",
            "admin/ops",
            401
        )
        
        self.admin_token = temp_token
        
        if success:
            print("✅ Ops endpoint properly protected (no auth)")
        else:
            print("❌ Ops endpoint should require authentication")
            
        return success

def main():
    print("🚀 Starting Ops Checklist Backend Tests")
    print("=" * 60)
    
    tester = OpsChecklistTester()
    
    # Setup admin user
    if not tester.setup_admin_user():
        print("❌ Failed to setup admin user")
        return 1
    
    # Test ops checklist functionality
    print(f"\n{'='*20} Testing Ops Checklist {'='*20}")
    
    # Test the main ops endpoint
    ops_success = tester.test_ops_checklist_api()
    
    # Test auth protection
    auth_success = tester.test_ops_auth_protection()
    
    # Print final results
    print(f"\n{'='*60}")
    print(f"📊 Final Results: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if ops_success:
        print("🎉 Ops Checklist API is working!")
    else:
        print("❌ Ops Checklist API has issues")
    
    if auth_success:
        print("🔒 Auth protection is working")
    else:
        print("⚠️ Auth protection may have issues")
    
    return 0 if (ops_success and auth_success) else 1

if __name__ == "__main__":
    sys.exit(main())