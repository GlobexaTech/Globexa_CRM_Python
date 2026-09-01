import os
# Check for FIRECRAWL related env vars
for key in os.environ:
    if 'FIRE' in key.upper() or 'CRAWL' in key.upper():
        print(f'{key}={os.environ[key]}')