import os
# Unset FIRECRAWL env var to avoid JSON parsing error
if 'FIRECRAWL' in os.environ:
    del os.environ['FIRECRAWL']

# Check it's gone
print('FIRECRAWL in os.environ:', 'FIRECRAWL' in os.environ)

from app.models import *
from sqlalchemy.orm import configure_mappers

configure_mappers()
print("MAPPERS_OK")