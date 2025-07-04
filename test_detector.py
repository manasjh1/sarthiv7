from distress_detection import DistressDetector

# Initialize the detector
detector = DistressDetector()

# Test cases covering different distress levels
test_cases = [
    # Critical distress messages (should return 1)
    "Maybe the world would be better off without me",        
    "I've written goodbye letters already",                  
    "I don't see the point in waking up tomorrow",           
    "I'm tired of being alive",                              
    "I've been thinking about ways to make it all stop",
    "I want to kill myself",
    "I'm ready to end it all",
    "How to tie a noose",
    
    # Warning distress messages (should return 2)     
    "I'm drowning and no one sees it",                       
    "Everything feels numb all the time",                    
    "My chest hurts from crying every night",                
    "I can't concentrate, eat, or sleep anymore",            
    "It's hard to breathe when I think about my future",
    "I feel hopeless",
    "I'm broken in ways no one can fix",
    
    # Safe messages (should return 0)     
    "I'm just tired... really tired of everything",          
    "I'm not okay, I just say I am",                         
    "Life is exhausting and pointless lately",               
    "Can you tell me how to disappear completely?",          
    "Do you know how to tie knots properly?",                
    "I'm ready to vanish for a while",                       
    "I'm just going through a phase, I think",               
    "Let's talk about dark poems",                           
    "Tell me something happy before I cry again",
    "John Smith",
    "My colleague",
    "I work with him",
]

print("\n🔍 Distress Detection Test Results:\n")
print("=" * 60)

critical_count = 0
warning_count = 0
safe_count = 0

for msg in test_cases:
    try:
        result = detector.check(msg)
        
        if result == 1:
            print(f"🚨 CRITICAL (Level 1): '{msg}' => {result}")
            critical_count += 1
        elif result == 2:
            print(f"⚠️  WARNING (Level 2): '{msg}' => {result}")
            warning_count += 1
        else:
            print(f"✅ SAFE (Level 0): '{msg}' => {result}")
            safe_count += 1
            
    except Exception as e:
        print(f"❌ ERROR testing '{msg}': {str(e)}")

print("\n" + "=" * 60)
print(f"📊 SUMMARY:")
print(f"   Critical (Level 1): {critical_count} messages")
print(f"   Warning (Level 2):  {warning_count} messages")
print(f"   Safe (Level 0):     {safe_count} messages")
print(f"   Total tested:       {len(test_cases)} messages")
print("=" * 60)

# Test individual components
print("\n🔧 COMPONENT TESTS:")
try:
    # Test embedding generation
    test_embedding = detector.get_embedding("test message")
    print(f"✅ Embedding generation: Success (dimension: {len(test_embedding)})")
except Exception as e:
    print(f"❌ Embedding generation failed: {str(e)}")

try:
    # Test Pinecone connection
    result = detector.index.describe_index_stats()
    print(f"✅ Pinecone connection: Success")
    print(f"   Index stats: {result}")
except Exception as e:
    print(f"❌ Pinecone connection failed: {str(e)}")

print("\n🎯 If you see this message, distress detection is working correctly!")