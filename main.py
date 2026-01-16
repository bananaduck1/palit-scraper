"""
Palit Scraper - Phase 1
Scrapes cinema websites for special events (Q&As, 35mm screenings, etc.)
"""

import os
import json
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from firecrawl import Firecrawl
from openai import OpenAI
from supabase import create_client, Client


# Load environment variables with smart path finding
def load_env_file():
    """Load .env file from current directory or parent directory."""
    current_dir = Path(__file__).parent
    parent_dir = current_dir.parent
    
    # Try current directory first
    current_env = current_dir / '.env'
    parent_env = parent_dir / '.env'
    
    env_path = None
    if current_env.exists():
        env_path = current_env
    elif parent_env.exists():
        env_path = parent_env
    
    if env_path:
        print(f"Looking for .env at: {env_path}")
        load_dotenv(dotenv_path=env_path)
        return True
    else:
        print(f"⚠️  No .env file found in:")
        print(f"   - {current_env}")
        print(f"   - {parent_env}")
        # Still try to load (might be in environment already)
        load_dotenv()
        return False

load_env_file()

# Theater name constant
THEATER_NAME = "Metrograph"


def get_api_key(key_name: str, fallback_key_name: Optional[str] = None) -> str:
    """
    Get API key from environment with fallback support.
    
    Args:
        key_name: Primary environment variable name
        fallback_key_name: Optional fallback environment variable name
        
    Returns:
        The API key value
        
    Raises:
        ValueError: If neither key is found
    """
    api_key = os.getenv(key_name)
    if api_key:
        return api_key
    
    if fallback_key_name:
        api_key = os.getenv(fallback_key_name)
        if api_key:
            print(f"⚠️  {key_name} not found, using {fallback_key_name} instead")
            return api_key
    
    raise ValueError(
        f"API key not found. Tried: {key_name}"
        + (f" and {fallback_key_name}" if fallback_key_name else "")
        + f". Please check your .env file."
    )


# Pydantic model for screening events
class ScreeningEvent(BaseModel):
    """Represents a cinema screening event."""
    film_title: str = Field(description="The title of the film being screened")
    showtime: str = Field(description="The showtime in its original format (e.g., 'Fri, Jan 15, 7:00 PM')")
    is_special_event: bool = Field(description="True if the event mentions Q&A, Director, 35mm, 70mm, or Premiere")
    special_guest: Optional[str] = Field(default=None, description="Name of special guest if present (e.g., 'Sean Baker')")
    format: Optional[str] = Field(default=None, description="Film format if special (e.g., '35mm', '70mm')")




def scrape_calendar(url: str) -> str:
    """
    Scrape a calendar URL using Firecrawl and return the markdown content.
    
    Args:
        url: The URL to scrape
        
    Returns:
        The scraped content as markdown text
    """
    # Get API key with fallback
    api_key = get_api_key("FIRECRAWL_API_KEY", "EXPO_PUBLIC_FIRECRAWL_API_KEY")
    
    app = Firecrawl(api_key=api_key)
    scrape_result = app.scrape(url, formats=['markdown'])
    
    # Debug: Print the response type
    print(f"\n🔍 Firecrawl Response Type: {type(scrape_result)}")
    
    # Handle Document object (Pydantic model) - can be a list or single object
    if isinstance(scrape_result, list):
        # Multiple documents returned
        if len(scrape_result) == 0:
            raise ValueError("Firecrawl returned an empty list of documents")
        markdown_content = scrape_result[0].markdown
    else:
        # Single Document object
        if hasattr(scrape_result, 'markdown'):
            markdown_content = scrape_result.markdown
        elif hasattr(scrape_result, 'content'):
            markdown_content = scrape_result.content
        else:
            raise ValueError(f"Document object has no 'markdown' or 'content' attribute. Available attributes: {dir(scrape_result)}")
    
    return markdown_content


def analyze_with_openai(markdown_content: str) -> List[ScreeningEvent]:
    """
    Use OpenAI to extract ScreeningEvent objects from the scraped markdown.
    
    Args:
        markdown_content: The scraped markdown text from the calendar
        
    Returns:
        A list of ScreeningEvent objects
    """
    # Get API key (no fallback needed for OpenAI)
    api_key = get_api_key("EXPO_PUBLIC_OPENAI_API_KEY")
    
    # Initialize the OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Processing the full page content
    # Create the prompt
    prompt = f"""Analyze the following cinema calendar page and extract screening events.

For each event, determine:
- The film title
- The showtime (keep the original format)
- Whether it's a special event (true if it mentions: Q&A, Director, 35mm, 70mm, Premiere, or similar special programming)
- Any special guest name (if mentioned)
- The film format (if it's 35mm, 70mm, DCP, etc.)

Here is the calendar content:

{markdown_content}

Extract screening events and return them as a JSON array of ScreeningEvent objects."""

    # Use structured outputs with Pydantic model
    # Create a wrapper model for the list since parse expects a single model
    class EventsResponse(BaseModel):
        events: List[ScreeningEvent]
    
    print("⏳ Generating JSON (this may take a few seconds)...")
    
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a strict filter. ONLY extract events where `is_special_event` is TRUE. If a movie is just a standard screening, DO NOT include it in the JSON output at all. Ignore it completely. Return a JSON object with an 'events' array containing only special events."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format=EventsResponse,
        temperature=0.3,
        timeout=30.0,
    )
    
    # Parse the response
    try:
        parsed_content = response.choices[0].message.parsed
        
        # Extract events from the parsed response
        if isinstance(parsed_content, EventsResponse):
            events = parsed_content.events
        elif isinstance(parsed_content, dict) and "events" in parsed_content:
            events = [ScreeningEvent(**event) for event in parsed_content["events"]]
        else:
            # Fallback: try to parse from message content
            content_text = response.choices[0].message.content
            if content_text:
                cleaned = content_text.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                
                events_data = json.loads(cleaned)
                if isinstance(events_data, dict) and "events" in events_data:
                    events = [ScreeningEvent(**event) for event in events_data["events"]]
                elif isinstance(events_data, list):
                    events = [ScreeningEvent(**event) for event in events_data]
                else:
                    events = [ScreeningEvent(**events_data)]
            else:
                raise ValueError("No content in response")
        
        # Print the parsed response
        print("\n📊 Parsed Response:")
        print("=" * 50)
        for i, event in enumerate(events, 1):
            print(f"\nEvent {i}:")
            print(f"  Title: {event.film_title}")
            print(f"  Showtime: {event.showtime}")
            print(f"  Special Event: {event.is_special_event}")
            if event.special_guest:
                print(f"  Special Guest: {event.special_guest}")
            if event.format:
                print(f"  Format: {event.format}")
        
        return events
        
    except Exception as e:
        print(f"Error processing response: {e}")
        if hasattr(response, 'choices') and response.choices[0].message.content:
            print(f"Response content: {response.choices[0].message.content}")
        raise


def main():
    """Main execution function."""
    print("🎬 Palit Scraper - Phase 1")
    print("=" * 50)
    
    # Debug: Check API keys
    print("\n🔍 Environment Check:")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("EXPO_PUBLIC_FIRECRAWL_API_KEY")
    openai_key = os.getenv("EXPO_PUBLIC_OPENAI_API_KEY")
    print(f"   Firecrawl Key Found: {'Yes ✅' if firecrawl_key else 'No ❌'}")
    print(f"   OpenAI Key Found: {'Yes ✅' if openai_key else 'No ❌'}")
    
    if not firecrawl_key:
        print("\n⚠️  Warning: Firecrawl API key not found!")
        print("   Looking for: FIRECRAWL_API_KEY or EXPO_PUBLIC_FIRECRAWL_API_KEY")
    if not openai_key:
        print("\n⚠️  Warning: OpenAI API key not found!")
        print("   Looking for: EXPO_PUBLIC_OPENAI_API_KEY")
    
    # Step 1: Scrape the calendar
    print("\n📡 Scraping Metrograph calendar...")
    url = "https://metrograph.com/calendar"
    
    try:
        markdown_content = scrape_calendar(url)
        print(f"✅ Successfully scraped {len(markdown_content)} characters")
    except Exception as e:
        print(f"❌ Error scraping URL: {e}")
        return
    
    # Step 2: Analyze with OpenAI
    print("\n🤖 Analyzing content with OpenAI...")
    try:
        events = analyze_with_openai(markdown_content)
        print(f"✅ Extracted {len(events)} screening events")
    except Exception as e:
        print(f"❌ Error analyzing content: {e}")
        return
    
    # Step 3: Output results
    print("\n📋 Results:")
    print("=" * 50)
    
    # Convert to JSON for output
    events_json = [event.model_dump() for event in events]
    print(json.dumps(events_json, indent=2, ensure_ascii=False))
    
    # Summary
    special_events = [e for e in events if e.is_special_event]
    print(f"\n✨ Found {len(special_events)} special events out of {len(events)} total screenings")
    
    # Step 4: Save to Supabase
    print("\n💾 Saving to Supabase...")
    try:
        # Initialize Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            print("⚠️  Warning: Supabase credentials not found. Skipping database save.")
            print("   Looking for: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            return
        
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Prepare data for upsert
        events_data = []
        for event in events:
            event_dict = {
                "film_title": event.film_title,
                "showtime": event.showtime,
                "theater_name": THEATER_NAME,
                "is_special_event": event.is_special_event,
                "special_guest": event.special_guest,
                "format": event.format,
            }
            events_data.append(event_dict)
        
        # Upsert to Supabase
        result = supabase.table("scraping_events").upsert(
            events_data,
            on_conflict="film_title, showtime, theater_name"
        ).execute()
        
        print(f"✅ Successfully saved {len(events_data)} events to Supabase!")
        
    except Exception as e:
        print(f"❌ Error saving to Supabase: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
