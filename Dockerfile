# Use a lightweight Python base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install uv for rapid dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Copy pyproject.toml first to cache dependency installation
COPY pyproject.toml .

# Install dependencies directly to the system Python environment (safe inside Docker container)
RUN uv pip install --system -r pyproject.toml --no-cache

# Copy the source code
COPY src/ src/

# Install the project itself as an editable package or just let python find src/
ENV PYTHONPATH="/app/src"

# Command to run the MCP server over standard input/output (stdio)
ENTRYPOINT ["python", "-m", "thehive_mcp.server"]
