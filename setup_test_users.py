import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, CategoryDict
import uuid

def setup_test_data():
    """Setup test users and categories for testing reflection mode functionality"""
    db: Session = SessionLocal()
    
    try:
        # Create test users with different proficiency scores
        
        # User 1: Low proficiency user (will get guided reflections)
        user1 = User(
            user_id=uuid.uuid4(),
            name="John Doe",
            email="john@test.com",
            proficiency_score=0,  # Low proficiency = guided reflections
            status=1
        )
        
        # User 2: High proficiency user (will get collaborative reflections)
        user2 = User(
            user_id=uuid.uuid4(),
            name="Jane Smith", 
            email="jane@test.com",
            proficiency_score=1,  # High proficiency = collaborative reflections
            status=1
        )
        
        # Check if users already exist
        existing_user1 = db.query(User).filter(User.email == "john@test.com").first()
        existing_user2 = db.query(User).filter(User.email == "jane@test.com").first()
        
        if not existing_user1:
            db.add(user1)
            print(f"Created User: John Doe ({user1.user_id})")
        else:
            print(f"User John Doe already exists: {existing_user1.user_id}")
            
        if not existing_user2:
            db.add(user2)
            print(f"Created User: Jane Smith ({user2.user_id})")
        else:
            print(f"User Jane Smith already exists: {existing_user2.user_id}")
        
        # Create categories if they don't exist
        categories = [
            {"category_no": 1, "category_name": "feedback"},
            {"category_no": 2, "category_name": "apology"},
            {"category_no": 3, "category_name": "gratitude"}
        ]
        
        for cat_data in categories:
            existing_cat = db.query(CategoryDict).filter(
                CategoryDict.category_no == cat_data["category_no"]
            ).first()
            
            if not existing_cat:
                category = CategoryDict(
                    category_no=cat_data["category_no"],
                    category_name=cat_data["category_name"],
                    status=1
                )
                db.add(category)
                print(f"Created category: {cat_data['category_name']}")
            else:
                print(f"Category already exists: {cat_data['category_name']}")
        
        db.commit()
        print("\n=== TEST USERS CREATED ===")
        print("Login with these emails to test different reflection modes:")
        print("1. john@test.com - Will create GUIDED reflections (proficiency_score = 0)")
        print("2. jane@test.com - Will create COLLABORATIVE reflections (proficiency_score = 1)")
        print("\nUse the /api/login endpoint with these emails to get JWT tokens")
        print("When they start reflections, the system will set the reflection mode based on their proficiency score")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    setup_test_data()