FROM rasa/rasa:3.6.0-full

WORKDIR /app

# Copy project files
COPY . /app

# Train model as root
USER root
RUN rasa train --fixed-model-name current

# Expose port
EXPOSE 5005

# Run Rasa server
CMD ["run", \
     "--enable-api", \
     "--cors", "*", \
     "--port", "5005", \
     "--credentials", "credentials.yml", \
     "--endpoints", "endpoints.yml"]