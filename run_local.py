import os

import uvicorn

from expedition_service.back.app import create_app


app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv('SERVICE_PORT', '8080')))
