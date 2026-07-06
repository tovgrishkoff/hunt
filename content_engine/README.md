# Content Engine - Autonomous AI Content Agent

Production-ready, modular automated content engine that acts as an autonomous AI agent for multi-platform content creation.

## Features

- **Analytics Integration**: Metricool API integration for cross-platform performance analysis
- **Knowledge Base (RAG)**: ChromaDB-powered semantic search over brand guidelines and content
- **AI Content Generation**: Claude-powered context-aware content with platform optimization
- **Image Generation**: Flux/Stability AI via Replicate for photorealistic visuals
- **Auto-Scheduling**: Metricool content calendar integration for cross-posting

## Architecture

```
content_engine/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── config.py             # Centralized pydantic-settings configuration
│   ├── models.py             # Pydantic models for data validation
│   ├── logger.py             # Loguru logging configuration
│   ├── analytics_engine.py   # Metricool analytics integration
│   ├── knowledge_base.py     # ChromaDB RAG implementation
│   ├── content_generator.py  # Claude/Anthropic content generation
│   ├── image_generator.py    # Replicate image generation
│   ├── publisher.py          # Metricool publishing/scheduling
│   └── main.py               # Pipeline orchestrator
├── knowledge/                # Knowledge base files (brand guidelines, etc.)
├── logs/                     # Application logs
├── data/                     # ChromaDB storage (auto-created)
├── generated_images/         # Generated images (auto-created)
├── .env.example              # Environment variables template
├── requirements.txt          # Python dependencies
└── README.md
```

## Installation

### 1. Clone and Setup

```bash
cd content_engine
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

Required API keys:
- `ANTHROPIC_API_KEY`: Claude API key from Anthropic
- `METRICOOL_API_TOKEN`: Metricool API token
- `METRICOOL_USER_ID`: Your Metricool user ID
- `REPLICATE_API_TOKEN`: Replicate API token for image generation

### 3. Add Knowledge Base Content

Place your brand guidelines, tone-of-voice documents, and reference materials in the `knowledge/` directory:

```
knowledge/
├── brand_guidelines.md
├── content_topics.md
├── tone_of_voice.md
└── product_info.md
```

## Usage

### CLI Usage

```bash
# Full pipeline: analyze, generate content, create images, schedule
python -m src.main "5 productivity tips for remote workers"

# Specific platforms only
python -m src.main "Morning routine tips" --platforms "instagram,telegram"

# Generate content without scheduling
python -m src.main "Mindset for success" --no-schedule

# Generate content without images
python -m src.main "Business tips" --no-images

# Analytics only
python -m src.main "" --analytics-only
```

### Python API

```python
import asyncio
from src.main import ContentEngine
from src.models import Platform

async def main():
    # Initialize the engine
    engine = ContentEngine()
    
    # Run full pipeline
    result = await engine.run_pipeline(
        topic="5 habits of successful entrepreneurs",
        platforms=[Platform.INSTAGRAM, Platform.PINTEREST],
        schedule=True,
        generate_images=True,
    )
    
    # Check results
    if result.success:
        print(f"Generated {len(result.generated_contents)} posts")
        print(f"Scheduled {len(result.publish_results)} posts")
    else:
        print(f"Errors: {result.errors}")

    # Or generate content only
    contents = await engine.generate_content_only(
        topic="Morning productivity tips",
        platforms=[Platform.INSTAGRAM],
    )
    
    for content in contents:
        print(f"[{content.platform}] {content.text[:100]}...")

asyncio.run(main())
```

### Adding Custom Knowledge

```python
from src.main import ContentEngine

engine = ContentEngine()

# Add text directly
engine.add_knowledge(
    text="Our brand voice is professional yet approachable...",
    source="brand_guidelines_v2"
)

# Check knowledge base stats
stats = engine.get_knowledge_stats()
print(f"Documents indexed: {stats['document_count']}")
```

## Pipeline Flow

```
┌─────────────────┐
│  1. ANALYTICS   │ ─── Fetch 30-day metrics from Metricool
└────────┬────────┘     Rank top posts, identify patterns
         │
         ▼
┌─────────────────┐
│  2. KNOWLEDGE   │ ─── Retrieve brand guidelines
└────────┬────────┘     Get topic-specific context
         │
         ▼
┌─────────────────┐
│  3. GENERATE    │ ─── Claude creates platform-optimized text
└────────┬────────┘     Includes hooks, CTAs, hashtags
         │
         ▼
┌─────────────────┐
│  4. VISUALIZE   │ ─── Claude writes detailed image prompts
└────────┬────────┘     Flux generates photorealistic images
         │
         ▼
┌─────────────────┐
│  5. PUBLISH     │ ─── Upload media to Metricool
└─────────────────┘     Schedule with optimal timing
```

## Configuration

### Platform Constraints

The engine automatically enforces platform-specific constraints:

| Platform  | Max Caption | Max Hashtags | Aspect Ratio |
|-----------|-------------|--------------|--------------|
| Instagram | 2,200 chars | 30           | 4:5          |
| Pinterest | 500 chars   | 20           | 2:3          |
| Telegram  | 4,096 chars | N/A          | 1:1          |

### Image Generation Settings

```env
# In .env
IMAGE_MODEL=black-forest-labs/flux-1.1-pro
DEFAULT_IMAGE_STYLE=photorealistic, cinematic lighting, 8k quality
```

## Error Handling

The engine implements:
- **Retry Logic**: Exponential backoff for all API calls (tenacity)
- **Graceful Degradation**: Pipeline continues if individual steps fail
- **Comprehensive Logging**: All operations logged with loguru

## Logs

Logs are stored in `logs/content_engine.log` with automatic rotation:
- Max file size: 10 MB
- Retention: 7 days
- Compression: gzip

## Production Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "-m", "src.main", "--help"]
```

### Scheduled Execution (Cron)

```bash
# Generate daily content at 6 AM
0 6 * * * cd /path/to/content_engine && /path/to/venv/bin/python -m src.main "Daily motivation tips"
```

## License

MIT License
