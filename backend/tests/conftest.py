import os
import tempfile

os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='chatbot-data-test-')
os.environ['QDRANT_LOCAL_PATH'] = tempfile.mkdtemp(prefix='chatbot-qdrant-test-')
os.environ['EMBEDDING_PROVIDER'] = 'openai'
