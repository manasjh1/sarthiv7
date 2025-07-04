import os
from dotenv import load_dotenv
from openai import OpenAI
try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    # Fallback for older versions
    import pinecone as pinecone_module
    from pinecone import ServerlessSpec
from keywords import red_list, yellow_list

load_dotenv()

# Load environment variables
pinecone_api_key = os.getenv("PINECONE_API_KEY")
pinecone_env = os.getenv("PINECONE_ENV")  
index_name = os.getenv("PINECONE_INDEX")
namespace = os.getenv("PINECONE_NAMESPACE", "distress")
openai_api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")

# Validate environment variables
if not all([pinecone_api_key, index_name, openai_api_key]):
    raise ValueError("Missing required environment variables: PINECONE_API_KEY, PINECONE_INDEX, OPENAI_API_KEY")

# Create OpenAI client
client = OpenAI(api_key=openai_api_key)

# Create Pinecone client - handle different versions
try:
    # New Pinecone client (v3.0+)
    pc = Pinecone(api_key=pinecone_api_key)
    
    # Create index if it doesn't exist
    existing_indexes = [index.name for index in pc.list_indexes()]
    if index_name not in existing_indexes:
        # Determine dimension based on model
        dimension = 3072 if "large" in model else 1536
        
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"  # Default region
            )
        )
        print(f"Created new index: {index_name}")
    
    index = pc.Index(index_name)
    
except Exception as e:
    try:
        # Older Pinecone client
        import pinecone
        pinecone.init(api_key=pinecone_api_key, environment=pinecone_env)
        
        # Create index if it doesn't exist
        if index_name not in pinecone.list_indexes():
            dimension = 3072 if "large" in model else 1536
            pinecone.create_index(
                name=index_name,
                dimension=dimension,
                metric="cosine"
            )
            print(f"Created new index: {index_name}")
        
        index = pinecone.Index(index_name)
        
    except Exception as e2:
        raise ValueError(f"Failed to initialize Pinecone: {str(e)} | {str(e2)}")

# Generate embeddings
def get_embeddings(text_list):
    response = client.embeddings.create(
        model=model,
        input=text_list
    )
    return [item.embedding for item in response.data]

print(f"Using model: {model}")
print(f"Uploading to index: {index_name}, namespace: {namespace}")

# Upload red list
print("Uploading red (critical) keywords...")
red_embeddings = get_embeddings(red_list)
red_ids = [f"red_{i}" for i in range(len(red_list))]
red_metadata = [{"category": "red", "text": t} for t in red_list]

vectors_to_upsert = list(zip(red_ids, red_embeddings, red_metadata))
index.upsert(vectors=vectors_to_upsert, namespace=namespace)

# Upload yellow list
print("Uploading yellow (warning) keywords...")
yellow_embeddings = get_embeddings(yellow_list)
yellow_ids = [f"yellow_{i}" for i in range(len(yellow_list))]
yellow_metadata = [{"category": "yellow", "text": t} for t in yellow_list]

vectors_to_upsert = list(zip(yellow_ids, yellow_embeddings, yellow_metadata))
index.upsert(vectors=vectors_to_upsert, namespace=namespace)

print(f"✅ Successfully uploaded vectors to Pinecone!")
print(f"   Index: {index_name}")
print(f"   Namespace: {namespace}")
print(f"   Model: {model}")
print(f"   Red keywords: {len(red_list)}")
print(f"   Yellow keywords: {len(yellow_list)}")