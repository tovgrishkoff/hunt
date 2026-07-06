"""
Knowledge Base Module - RAG Implementation with ChromaDB.

Provides semantic search over local knowledge (brand guidelines,
tone-of-voice rules, core topics, and reference materials).
"""

import hashlib
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import get_settings
from .logger import get_logger
from .models import KnowledgeContext

logger = get_logger(__name__)


class KnowledgeBase:
    """
    Lightweight RAG implementation using ChromaDB.

    Ingests local documents and provides semantic retrieval
    for context-aware content generation.
    """

    COLLECTION_NAME = "content_knowledge"
    CHUNK_SIZE = 1000
    CHUNK_OVERLAP = 200

    def __init__(self) -> None:
        """Initialize the knowledge base with ChromaDB."""
        self.settings = get_settings()
        self._ensure_directories()
        self._init_chromadb()

    def _ensure_directories(self) -> None:
        """Ensure required directories exist."""
        self.settings.chromadb_path.mkdir(parents=True, exist_ok=True)
        self.settings.knowledge_dir.mkdir(parents=True, exist_ok=True)

    def _init_chromadb(self) -> None:
        """Initialize ChromaDB client and collection."""
        logger.info(f"Initializing ChromaDB at {self.settings.chromadb_path}")

        self.client = chromadb.PersistentClient(
            path=str(self.settings.chromadb_path),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Content engine knowledge base"},
        )

        logger.info(
            f"ChromaDB collection '{self.COLLECTION_NAME}' ready "
            f"with {self.collection.count()} documents"
        )

    def _generate_doc_id(self, content: str, source: str) -> str:
        """Generate unique document ID from content hash."""
        hash_input = f"{source}:{content[:200]}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks for better retrieval."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + self.CHUNK_SIZE

            if end < len(text):
                break_points = [
                    text.rfind("\n\n", start, end),
                    text.rfind(". ", start, end),
                    text.rfind("! ", start, end),
                    text.rfind("? ", start, end),
                ]

                best_break = max(bp for bp in break_points if bp > start)
                if best_break > start:
                    end = best_break + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - self.CHUNK_OVERLAP
            if start >= len(text):
                break

        return chunks

    def _parse_markdown_metadata(self, content: str) -> tuple[dict[str, str], str]:
        """Extract YAML frontmatter from markdown if present."""
        metadata: dict[str, str] = {}

        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            content = content[frontmatter_match.end() :]

            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    metadata[key.strip()] = value.strip()

        return metadata, content

    def ingest_file(self, file_path: Path) -> int:
        """Ingest a single file into the knowledge base."""
        logger.info(f"Ingesting file: {file_path}")

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return 0

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return 0

        metadata, content = self._parse_markdown_metadata(content)
        chunks = self._chunk_text(content)

        if not chunks:
            logger.warning(f"No chunks generated from {file_path}")
            return 0

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            doc_id = self._generate_doc_id(chunk, str(file_path))
            ids.append(f"{doc_id}_{i}")
            documents.append(chunk)
            metadatas.append(
                {
                    "source": str(file_path.name),
                    "source_path": str(file_path),
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "file_type": file_path.suffix,
                    **metadata,
                }
            )

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Ingested {len(chunks)} chunks from {file_path.name}")
        return len(chunks)

    def ingest_directory(self, directory: Path | None = None) -> int:
        """Ingest all supported files from a directory."""
        if directory is None:
            directory = self.settings.knowledge_dir

        supported_extensions = {".md", ".txt", ".rst", ".json"}
        total_chunks = 0

        logger.info(f"Scanning directory for knowledge files: {directory}")

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                total_chunks += self.ingest_file(file_path)

        logger.info(
            f"Directory ingestion complete: {total_chunks} total chunks indexed"
        )
        return total_chunks

    def ingest_text(
        self,
        text: str,
        source: str = "direct_input",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Ingest raw text directly into the knowledge base."""
        chunks = self._chunk_text(text)

        if not chunks:
            return 0

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            doc_id = self._generate_doc_id(chunk, source)
            ids.append(f"{doc_id}_{i}")
            documents.append(chunk)
            metadatas.append(
                {
                    "source": source,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    **(metadata or {}),
                }
            )

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Ingested {len(chunks)} chunks from '{source}'")
        return len(chunks)

    def get_relevant_context(
        self,
        query: str,
        top_k: int = 5,
        min_relevance: float = 0.3,
    ) -> KnowledgeContext:
        """
        Retrieve relevant context for a given query.

        Args:
            query: Search query string
            top_k: Maximum number of documents to retrieve
            min_relevance: Minimum relevance score (0-1) to include

        Returns:
            KnowledgeContext with relevant documents and metadata
        """
        logger.info(f"Retrieving context for query: '{query[:50]}...'")

        if self.collection.count() == 0:
            logger.warning("Knowledge base is empty, no context available")
            return KnowledgeContext(
                query=query,
                documents=[],
                sources=[],
                relevance_scores=[],
                metadata={"warning": "Knowledge base is empty"},
            )

        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        documents: list[str] = []
        sources: list[str] = []
        scores: list[float] = []

        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                distance = results["distances"][0][i] if results["distances"] else 1.0
                relevance = 1 - (distance / 2)

                if relevance >= min_relevance:
                    documents.append(doc)
                    sources.append(
                        results["metadatas"][0][i].get("source", "unknown")
                        if results["metadatas"]
                        else "unknown"
                    )
                    scores.append(round(relevance, 3))

        context = KnowledgeContext(
            query=query,
            documents=documents,
            sources=sources,
            relevance_scores=scores,
            metadata={
                "total_retrieved": len(documents),
                "top_k_requested": top_k,
                "collection_size": self.collection.count(),
            },
        )

        logger.info(f"Retrieved {len(documents)} relevant documents")
        return context

    def get_brand_guidelines(self) -> KnowledgeContext:
        """Retrieve brand-specific guidelines and tone-of-voice rules."""
        return self.get_relevant_context(
            query="brand guidelines tone of voice style rules personality",
            top_k=3,
        )

    def get_topic_context(self, topic: str) -> KnowledgeContext:
        """Retrieve context specific to a content topic."""
        return self.get_relevant_context(
            query=f"topic information about {topic}",
            top_k=5,
        )

    def clear(self) -> None:
        """Clear all documents from the knowledge base."""
        logger.warning("Clearing entire knowledge base")
        self.client.delete_collection(self.COLLECTION_NAME)
        self.collection = self.client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"description": "Content engine knowledge base"},
        )

    def stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        return {
            "collection_name": self.COLLECTION_NAME,
            "document_count": self.collection.count(),
            "storage_path": str(self.settings.chromadb_path),
        }


def create_sample_knowledge_files(knowledge_dir: Path) -> None:
    """Create sample knowledge base files for demonstration."""
    logger.info(f"Creating sample knowledge files in {knowledge_dir}")

    brand_guidelines = """---
title: Brand Guidelines
type: guidelines
priority: high
---

# Brand Voice & Tone Guidelines

## Core Brand Personality
- **Professional** yet approachable
- **Educational** without being condescending
- **Inspiring** and action-oriented
- **Authentic** and transparent

## Tone of Voice Rules
1. Use active voice whenever possible
2. Keep sentences concise (under 20 words preferred)
3. Avoid jargon unless explaining it
4. Use "you" to address the audience directly
5. Be confident but not arrogant

## Content Pillars
1. **Education**: Share knowledge and insights
2. **Inspiration**: Motivate action and growth
3. **Community**: Foster connection and belonging
4. **Expertise**: Demonstrate authority in our field

## Do's and Don'ts

### Do:
- Use storytelling to illustrate points
- Include actionable takeaways
- Ask questions to engage the audience
- Use emojis sparingly for warmth

### Don't:
- Use clickbait or misleading hooks
- Be overly promotional
- Use all caps (except for emphasis)
- Ignore negative feedback
"""

    content_topics = """---
title: Core Content Topics
type: topics
---

# Content Topic Framework

## Primary Topics
1. **Personal Development** - Growth mindset, productivity, habits
2. **Business Strategy** - Entrepreneurship, leadership, scaling
3. **Technology Trends** - AI, automation, digital tools
4. **Health & Wellness** - Work-life balance, mental health

## Content Angles That Perform Well
- "How I..." personal stories
- "X mistakes to avoid" lists
- Step-by-step guides
- Myth-busting posts
- Behind-the-scenes glimpses
- User success stories

## Hashtag Strategy
- Mix of broad and niche hashtags
- 10-15 hashtags per Instagram post
- Brand hashtag always included
- Rotate hashtag sets to avoid shadowban
"""

    knowledge_dir.mkdir(parents=True, exist_ok=True)

    (knowledge_dir / "brand_guidelines.md").write_text(brand_guidelines)
    (knowledge_dir / "content_topics.md").write_text(content_topics)

    logger.info("Sample knowledge files created successfully")
