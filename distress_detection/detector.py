import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI 
from pinecone import Pinecone

load_dotenv()

class DistressDetector:
    def __init__(self, threshold=0.65):
        self.threshold = threshold

        # Load environment variables
        self.index_name = os.getenv("PINECONE_INDEX")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "distress")
        self.model_name = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

        # Validate required environment variables
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY environment variable is required")
        if not os.getenv("PINECONE_API_KEY"):
            raise ValueError("PINECONE_API_KEY environment variable is required")
        if not self.index_name:
            raise ValueError("PINECONE_INDEX environment variable is required")

        # Async OpenAI setup
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Pinecone setup (synchronous client - we'll use asyncio.to_thread)
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = self.pc.Index(self.index_name)

    async def get_embedding(self, text: str):
        """Get embedding asynchronously"""
        response = await self.openai_client.embeddings.create(
            model=self.model_name,
            input=text
        )
        return response.data[0].embedding

    def _sync_pinecone_query(self, embedding):
        """Synchronous Pinecone query to be run in thread"""
        return self.index.query(
            vector=embedding,
            top_k=5,
            include_metadata=True,
            namespace=self.namespace
        )

    async def check(self, message: str) -> int:
        """Check for distress asynchronously"""
        try:
            # Run embedding and pinecone query concurrently
            embedding_task = self.get_embedding(message)
            
            # Get embedding first
            embedding = await embedding_task
            
            # Run Pinecone query in thread pool to avoid blocking
            result = await asyncio.to_thread(self._sync_pinecone_query, embedding)

            if result and result.matches:
                match = result.matches[0]
                score = match.score
                category = match.metadata.get("category", "")

                if category == "red" and score >= 0.65:
                    return 1
                elif category == "yellow" and score >= 0.55:
                    return 2

            return 0
        except Exception as e:
            print(f"Error in distress detection: {str(e)}")
            return 0

    async def close(self):
        """Close async client"""
        await self.openai_client.close()