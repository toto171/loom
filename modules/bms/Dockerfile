# Forward-looking artifact for the M1 ComposeOrchestrator. NOT used by the M0
# in-process orchestrator (M0 ticks this module in-process over the ShimBus).
# At M1 this image runs the BMS as a standalone service against a networked
# KUKSA broker; the container entrypoint lands with that milestone.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY loom /app/loom
COPY modules/bms /app/modules/bms
RUN pip install --no-cache-dir .

# Placeholder entrypoint until the KUKSA service loop exists (M1).
CMD ["python", "-c", "print('bms.default container entrypoint arrives at M1')"]
