FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Environment variable to define PORT
ENV PORT=8000

# Expose the API port
EXPOSE 8000

# Start the bot (which also starts the FastAPI server)
CMD ["python", "bot.py"]
