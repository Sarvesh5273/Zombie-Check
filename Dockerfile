FROM node:22-bookworm-slim AS node
FROM python:3.12-slim
COPY --from=node /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY zombiecheck ./zombiecheck
COPY web ./web
COPY scripts/browser_signup.mjs ./scripts/browser_signup.mjs
RUN mkdir /app/data
EXPOSE 8765
CMD ["python", "-m", "zombiecheck", "serve", "--host", "0.0.0.0"]

