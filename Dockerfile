# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements file (we'll create this)
COPY requirements.txt .
COPY *.csv .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY templates/ templates/

# Create directories for images and output
RUN mkdir -p images output

# Expose port 5005
EXPOSE 443

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "443", "--image-paths", "ga_volumes_w_res.csv"]
