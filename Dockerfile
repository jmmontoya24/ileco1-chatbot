FROM rasa/rasa:3.6.0-full

WORKDIR /app

COPY . /app

USER root

# Train model
RUN rasa train --fixed-model-name current

EXPOSE 5005

CMD ["run", \
     "--enable-api", \
     "--cors", "*", \
     "--port", "5005", \
     "--credentials", "credentials.yml", \
     "--endpoints", "endpoints.yml"]