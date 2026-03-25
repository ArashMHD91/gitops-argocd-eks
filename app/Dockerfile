# Use slim Python image — smaller = faster pulls, less attack surface
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first (Docker layer caching trick)
# If requirements don't change, Docker reuses this cached layer
# Only re-installs packages when requirements.txt actually changes
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the app code
COPY app.py .

# Tell Docker this container listens on port 5000
EXPOSE 5000

# Command to run when container starts
CMD ["python", "app.py"]
