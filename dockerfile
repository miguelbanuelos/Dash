FROM python:3.11-slim

# Set the working directory
WORKDIR /usr/src/app

# 1. Install dependencies first (for faster builds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy the rest of the application
COPY . .

# 3. Expose the port
EXPOSE 8051

# 4. Bind to 0.0.0.0 so it's accessible outside the container
CMD ["gunicorn", "kdash:server", "--bind", "0.0.0.0:8051"]