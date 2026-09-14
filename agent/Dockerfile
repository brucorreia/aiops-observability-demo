FROM node:22-alpine AS console
WORKDIR /src
COPY apps/console/package.json apps/console/package-lock.json ./
RUN npm ci
COPY apps/console/ ./
RUN npm run build

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

COPY agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY agent/ /app/
COPY config/scoring.yaml /app/config/scoring.yaml
COPY --from=console /src/dist /app/console
ENV PYTHONPATH=/app
ENV CONSOLE_DIR=/app/console
USER 65532:65532
EXPOSE 8080
CMD ["python", "-u", "/app/api/server.py"]
