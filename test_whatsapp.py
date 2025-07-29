# test_whatsapp.py
import os
from dotenv import load_dotenv
from services.providers.whatsapp import WhatsAppProvider

# Load environment variables
load_dotenv()

def test_whatsapp_single():
    """Simple single OTP test"""
    try:
        print("=== Single WhatsApp OTP Test ===")
        
        # Environment check
        print("Environment Variables Check:")
        print(f"WHATSAPP_ACCESS_TOKEN: {'✓ Set' if os.getenv('WHATSAPP_ACCESS_TOKEN') else '✗ Missing'}")
        print(f"WHATSAPP_PHONE_NUMBER_ID: {'✓ Set' if os.getenv('WHATSAPP_PHONE_NUMBER_ID') else '✗ Missing'}")
        print("-" * 50)
        
        provider = WhatsAppProvider()
        
        result = provider.send(
            recipient="917428986796",  
            content="hi"  
        )
        
        print(f"\nResult:")
        print(f"Success: {result.success}")
        print(f"Message ID: {result.message_id}")
        print(f"Error: {result.error}")
        
        if result.success:
            print("✓ OTP sent successfully!")
        else:
            print("✗ Failed to send OTP")
        
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

def test_whatsapp_multiple():
    """Multiple OTP test cases"""
    try:
        print("=== Multiple WhatsApp OTP Tests ===")
        
        provider = WhatsAppProvider()
        
        # Different test cases
        test_cases = [
            {"recipient": "919142877324", "content": "112233", "description": "Simple 6-digit OTP"},
            {"recipient": "919142877324", "content": "445566", "description": "Another 6-digit OTP"},
            {"recipient": "919142877324", "content": "otp789012", "description": "OTP with prefix (should be cleaned)"},
            {"recipient": "919142877324", "content": "1234", "description": "4-digit OTP"},
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n--- Test Case {i}: {test_case['description']} ---")
            print(f"Recipient: {test_case['recipient']}")
            print(f"Content: {test_case['content']}")
            
            result = provider.send(
                recipient=test_case['recipient'],
                content=test_case['content']
            )
            
            print(f"Success: {result.success}")
            if result.success:
                print(f"Message ID: {result.message_id}")
                print("✓ OTP sent successfully!")
            else:
                print(f"Error: {result.error}")
                print("✗ Failed to send OTP")
            
            print("-" * 40)
            
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

def test_whatsapp_interactive():
    """Interactive test - input your own values"""
    try:
        print("=== Interactive WhatsApp OTP Test ===")
        
        provider = WhatsAppProvider()
        
        # Get user input
        recipient = input("Enter recipient phone number (with country code, e.g., 919142877324): ")
        if not recipient:
            recipient = "919142877324"  # Default
        
        otp_code = input("Enter OTP code to send (e.g., 112233): ")
        if not otp_code:
            otp_code = "112233"  # Default
        
        print(f"\nSending OTP '{otp_code}' to {recipient}...")
        
        result = provider.send(
            recipient=recipient,
            content=otp_code
        )
        
        print(f"\nResult:")
        print(f"Success: {result.success}")
        print(f"Message ID: {result.message_id}")
        print(f"Error: {result.error}")
        
        if result.success:
            print("✓ OTP sent successfully!")
        else:
            print("✗ Failed to send OTP")
        
    except Exception as e:
        print(f"Exception occurred: {str(e)}")

def main():
    """Main test function with menu"""
    print("=== WhatsApp OTP Testing Suite ===")
    print("1. Single OTP Test")
    print("2. Multiple OTP Tests")
    print("3. Interactive Test")
    print("4. Run All Tests")
    
    choice = input("\nSelect test type (1-4): ").strip()
    
    if choice == "1":
        test_whatsapp_single()
    elif choice == "2":
        test_whatsapp_multiple()
    elif choice == "3":
        test_whatsapp_interactive()
    elif choice == "4":
        print("Running all tests...\n")
        test_whatsapp_single()
        print("\n" + "="*60 + "\n")
        test_whatsapp_multiple()
    else:
        print("Invalid choice. Running single test...")
        test_whatsapp_single()

if __name__ == "__main__":
    main()
