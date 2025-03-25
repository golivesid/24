# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Create Videos directory
RUN mkdir -p /app/Videos

# Expose the port the Flask app runs on
EXPOSE 8000

# Use a production WSGI server like Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app & python", "bot.py"]
