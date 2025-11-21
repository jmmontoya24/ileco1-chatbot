FROM rasa/rasa:3.6.0-full

WORKDIR /app

# Copy only necessary files
COPY config.yml domain.yml endpoints.yml credentials.yml ./
COPY data ./data

USER root

# Train the model during build
RUN rasa train --fixed-model-name current

# Expose port
EXPOSE 5005

# Run Rasa server - use shell form to allow environment variable expansion
CMD rasa run \
    --enable-api \
    --cors "*" \
    --port $PORT \
    --credentials credentials.yml \
    --endpoints endpoints.yml \
    --debug