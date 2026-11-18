FROM node:24-slim AS web
WORKDIR /app
RUN npm install -g pnpm@11
COPY web/ .
RUN pnpm install --frozen-lockfile && pnpm run build
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api.py planner.py ./
COPY --from=web /app/dist web/dist
CMD ["python","-m","uvicorn","api:app","--host","0.0.0.0","--port","8000"]
