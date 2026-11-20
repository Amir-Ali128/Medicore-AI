# Sanal HBYS (synthetic hospital system). Build context: the app/ directory.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY hbys_sim/requirements.txt hbys_sim/requirements.txt
RUN pip install -r hbys_sim/requirements.txt
COPY hbys_sim hbys_sim
EXPOSE 8100
CMD ["uvicorn", "hbys_sim.main:app", "--host", "0.0.0.0", "--port", "8100"]
