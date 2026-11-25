"""Start the local EduMind server. No credentials are embedded in the project."""
import os
import uvicorn
from dotenv import load_dotenv

if __name__ == '__main__':
    load_dotenv()
    uvicorn.run('edumind.app:app',host='127.0.0.1',port=int(os.getenv('PORT','8000')),reload=False)
