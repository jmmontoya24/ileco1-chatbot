FROM rasa/rasa:3.6.0-full

WORKDIR /app

# Copy project files
COPY . /app

USER root

# Train model
RUN rasa train --fixed-model-name current

# Expose port (Render will override this with PORT env var)
EXPOSE 5005

# Run with PORT environment variable from Render
CMD rasa run \
    --enable-api \
    --cors "*" \
    --port ${PORT:-5005} \
    --credentials credentials.yml \
    --endpoints endpoints.yml \
    --log-file rasa.log \
    --debug