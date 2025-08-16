# distress_detection/detector.py - Production Version
import os
import asyncio
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI 
from pinecone import Pinecone

load_dotenv()

class DistressLevel(Enum):
    SAFE = 0
    CRITICAL = 1  # Red - immediate intervention required
    WARNING = 2   # Yellow - monitoring needed

@dataclass
class DistressResult:
    level: DistressLevel
    confidence: float
    matched_text: Optional[str] = None
    error: Optional[str] = None

class DistressDetector:
    """Production distress detection using OpenAI + Pinecone"""
    
    def __init__(self, red_threshold: float = 0.65, yellow_threshold: float = 0.55):
        self.red_threshold = red_threshold
        self.yellow_threshold = yellow_threshold
        self.logger = logging.getLogger(__name__)
        
        # Validate environment
        self._validate_env()
        
        # Initialize async OpenAI client
        self.openai_client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=10.0
        )
        
        # Initialize Pinecone (sync client, used with asyncio.to_thread)
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = self.pc.Index(os.getenv("PINECONE_INDEX"))
        self.namespace = os.getenv("PINECONE_NAMESPACE", "distress")
        self.model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    def _validate_env(self) -> None:
        """Validate required environment variables"""
        required = ["OPENAI_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX"]
        missing = [var for var in required if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    async def _get_embedding(self, text: str) -> list[float]:
        """Get text embedding from OpenAI"""
        try:
            response = await self.openai_client.embeddings.create(
                model=self.model,
                input=text.strip()
            )
            return response.data[0].embedding
        except Exception as e:
            self.logger.error(f"OpenAI embedding failed: {str(e)}")
            raise

    def _query_pinecone(self, embedding: list[float]):
        """Query Pinecone for similar distress patterns"""
        try:
            return self.index.query(
                vector=embedding,
                top_k=3,
                include_metadata=True,
                namespace=self.namespace
            )
        except Exception as e:
            self.logger.error(f"Pinecone query failed: {str(e)}")
            raise

    async def check(self, message: str) -> DistressResult:
        """
        Main distress detection method
        
        Args:
            message: User message to analyze
            
        Returns:
            DistressResult with level, confidence, and matched text
        """
        try:
            # Input validation
            if not message or not message.strip():
                return DistressResult(DistressLevel.SAFE, 0.0, error="Empty message")

            # Get embedding and query Pinecone
            embedding = await self._get_embedding(message)
            result = await asyncio.to_thread(self._query_pinecone, embedding)
            
            if not result or not result.matches:
                return DistressResult(DistressLevel.SAFE, 0.0)
            
            # Analyze best match
            match = result.matches[0]
            confidence = float(match.score)
            category = match.metadata.get("category", "")
            matched_text = match.metadata.get("text", "")
            
            # Determine distress level based on thresholds
            if category == "red" and confidence >= self.red_threshold:
                level = DistressLevel.CRITICAL
                self.logger.warning(f"Critical distress detected - confidence: {confidence:.3f}")
            elif category == "yellow" and confidence >= self.yellow_threshold:
                level = DistressLevel.WARNING
                self.logger.info(f"Warning distress detected - confidence: {confidence:.3f}")
            else:
                level = DistressLevel.SAFE
            
            return DistressResult(level, confidence, matched_text)
            
        except Exception as e:
            self.logger.error(f"Distress detection failed: {str(e)}")
            # Fail-safe: return SAFE on error to prevent blocking user flow
            return DistressResult(DistressLevel.SAFE, 0.0, error=str(e))

    async def close(self) -> None:
        """Cleanup async resources"""
        await self.openai_client.close()


# Singleton pattern for production use
_detector: Optional[DistressDetector] = None

async def get_detector() -> DistressDetector:
    """Get singleton detector instance"""
    global _detector
    if _detector is None:
        _detector = DistressDetector()
    return _detector

async def cleanup_detector() -> None:
    """Cleanup singleton detector"""
    global _detector
    if _detector:
        await _detector.close()
        _detector = None