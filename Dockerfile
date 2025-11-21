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

# Expose default Rasa port
EXPOSE 5005

# Let Rasa use Render's injected PORT environment variable
ENV PORT=5005

# Run Rasa server with dynamic port
CMD ["sh", "-c", "rasa run --enable-api --cors '*' --port $PORT --credentials credentials.yml --endpoints endpoints.yml --debug"]
