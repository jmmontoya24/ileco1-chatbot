FROM rasa/rasa:3.6.0-full

WORKDIR /app

# Copy project files
COPY . /app

USER root

# Train model
RUN rasa train --fixed-model-name current

# Expose port
EXPOSE 5005

# Run with explicit host binding
CMD ["run", \
     "--enable-api", \
     "--cors", "*", \
     "--port", "5005", \
     "--credentials", "credentials.yml", \
     "--endpoints", "endpoints.yml", \
     "--log-file", "rasa.log", \
     "--debug"]