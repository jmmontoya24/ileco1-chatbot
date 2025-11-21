# Use official Rasa full image
FROM rasa/rasa:3.6.0-full

# Set working directory
WORKDIR /app

# Copy required files
COPY config.yml domain.yml endpoints.yml credentials.yml ./
COPY data ./data

# Use root user to avoid permission issues
USER root

# Train the Rasa model at build time
RUN rasa train --fixed-model-name current

# Expose Rasa default port
EXPOSE 5005

# Set default port (Render injects $PORT automatically)
ENV PORT=5005

# Run Rasa server using exec form (avoids /bin/bash issue)
CMD ["rasa", "run", "--enable-api", "--cors", "*", "--port", "5005", "--credentials", "credentials.yml", "--endpoints", "endpoints.yml", "--debug"]
