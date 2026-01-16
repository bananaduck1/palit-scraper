# Palit Scraper

A Python tool for scraping cinema websites to find special events (Q&As, 35mm screenings, premieres, etc.).

## Phase 1 Features

- Scrapes cinema calendar pages using Firecrawl
- Uses OpenAI GPT-4o-mini to extract structured event data
- Identifies special events (Q&As, 35mm, director appearances, etc.)
- Outputs clean JSON data

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Get API Keys

#### Firecrawl API Key (Free)

1. Go to [https://firecrawl.dev](https://firecrawl.dev)
2. Sign up for a free account
3. Navigate to your dashboard/API settings
4. Copy your API key

#### OpenAI API Key

1. Go to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign in with your OpenAI account
3. Click "Create new secret key"
4. Copy the generated key (starts with `sk-`)

### 3. Configure Environment

1. Copy the example environment file:
   ```bash
   cp env.example .env
   ```
   
   (Note: If you have `env.example`, rename it to `.env.example` if preferred)

2. Edit `.env` and add your API keys:
   ```
   FIRECRAWL_API_KEY=your_actual_firecrawl_key_here
   OPENAI_API_KEY=your_actual_openai_key_here
   ```

## Running the Script

```bash
python main.py
```

The script will:
1. Scrape the Metrograph calendar page
2. Analyze the content with OpenAI GPT-4o-mini
3. Extract structured event data using Pydantic models
4. Print JSON results to the console

## Output Format

Each event includes:
- `film_title`: The movie title
- `showtime`: Showtime in original format
- `is_special_event`: Boolean indicating if it's a special event
- `special_guest`: Optional guest name (e.g., "Sean Baker")
- `format`: Optional format (e.g., "35mm", "70mm")

## Next Steps (Future Phases)

- Add support for multiple cinema websites
- Store events in a database
- Set up automated daily scraping
- Add filtering and search capabilities
- Integrate with PalitV2 app
