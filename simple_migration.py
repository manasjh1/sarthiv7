import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import engine, SessionLocal
from app.models import Base, User
import uuid

def run_migration():
    """Run database migration to add authentication features"""
    
    print("🔄 Setting up database for passwordless authentication...")
    
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully")
        
        db = SessionLocal()
        
        try:
            # Add is_verified column to users table if it doesn't exist
            result = db.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='is_verified'
            """))
            
            if not result.fetchone():
                print("➕ Adding is_verified column to users table...")
                db.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE"))
                db.commit()
                print("✅ is_verified column added")
            
            # Make email nullable since users can login with phone
            try:
                db.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
                db.commit()
                print("✅ Made email column nullable")
            except Exception as e:
                print(f"ℹ️  Email column already nullable or modification not needed: {str(e)}")
            
        except Exception as e:
            print(f"⚠️  Column modifications: {str(e)}")
            db.rollback()
        
        # Create demo user matching frontend mock data
        demo_user = db.query(User).filter(User.email == "welcome@example.com").first()
        
        if not demo_user:
            demo_user = User(
                name="Demo User",
                email="welcome@example.com",
                phone_number=17503523923,
                is_verified=True,
                status=1
            )
            db.add(demo_user)
            db.commit()
            print("✅ Demo user created: welcome@example.com")
        else:
            print("✅ Demo user already exists: welcome@example.com")
        
        db.close()
        
        print("\n🎉 Migration completed successfully!")
        print("\n📋 Available for testing:")
        print("📧 Demo email: welcome@example.com")
        print("📱 Demo phone: +17503523923")
        print("🔢 Development OTP: 141414")
        print("\n🚫 No invite codes required - Anyone can sign up!")
        print("\n🔗 Authentication endpoints available:")
        print("- POST /api/auth/check-user - Check if user exists")
        print("- POST /api/auth/send-otp - Send OTP (hardcoded)")
        print("- POST /api/auth/verify-otp - Verify OTP and authenticate")
        print("- POST /api/auth/resend-otp - Resend OTP")
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    success = run_migration()
    if not success:
        exit(1)