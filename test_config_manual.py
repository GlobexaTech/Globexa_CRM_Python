import os
os.environ['DATABASE_URL'] = 'postgresql://user:pass@localhost:5432/testdb'
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['FIRECRAWL_API_KEY'] = 'fc_test_key_123'
os.environ['SECRET_KEY'] = 'test-secret-key-min-32-chars-long'
os.environ['ENVIRONMENT'] = 'testing'

from app.core.config import Settings
settings = Settings()
print('DATABASE_URL:', settings.DATABASE_URL)
print('REDIS_URL:', settings.REDIS_URL)
print('FIRECRAWL_API_KEY:', settings.FIRECRAWL_API_KEY)
print('SECRET_KEY:', settings.SECRET_KEY)
print('ENVIRONMENT:', settings.ENVIRONMENT)