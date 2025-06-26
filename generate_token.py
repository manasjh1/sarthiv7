import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.auth import create_access_token
import uuid

# Use a test user ID (you can use any UUID from your database)
test_user_id = "12345678-1234-1234-1234-123456789012"

# Generate token
token = create_access_token(test_user_id)

print("=" * 50)
print("JWT TOKEN FOR TESTING:")
print("=" * 50)
print(token)
print("=" * 50)
print("Copy this token and use it in Postman Authorization")