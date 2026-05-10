FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Create a wrapper script so that running `query ...` works natively
RUN echo '#!/bin/sh\npython /app/query.py "$@"' > /usr/local/bin/query && chmod +x /usr/local/bin/query
# Keep container alive to run exec commands
CMD ["tail", "-f", "/dev/null"]
