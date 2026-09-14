FROM python:3.13-alpine
WORKDIR /app

ARG GIT_SHA=local
ARG SOURCE_URL=""
ARG BUILD_DATE=""
ARG VERSION=""

LABEL org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}"

COPY app.py /app/app.py
USER 65532:65532
EXPOSE 8080
CMD ["python", "-u", "/app/app.py"]
