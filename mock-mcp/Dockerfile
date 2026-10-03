FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mock_swiggy_mcp ./mock_swiggy_mcp
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8100
CMD ["uvicorn", "mock_swiggy_mcp.app:app", "--host", "0.0.0.0", "--port", "8100"]
