FROM public.ecr.aws/lambda/python:3.12 AS model

# Optional build arguments for the model ID and revision.
ARG LAYA_MODEL_ID
ARG LAYA_MODEL_REVISION

# Install the Hugging Face Hub Python package.
RUN python -m pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    huggingface-hub==1.32.0

# Copy the model download script into the Lambda task root.
COPY download_model.py ${LAMBDA_TASK_ROOT}/download_model.py

# Download the model using the provided ID and revision.
RUN LAYA_MODEL_ID="${LAYA_MODEL_ID}" \
    LAYA_MODEL_REVISION="${LAYA_MODEL_REVISION}" \
    python "${LAMBDA_TASK_ROOT}/download_model.py"

# Start of the final Lambda image stage.
FROM public.ecr.aws/lambda/python:3.12

LABEL org.opencontainers.image.title="Laymbda"
LABEL org.opencontainers.image.description="Laya inference on AWS Lambda"

# HF environment variables.
ENV HF_HOME=/opt/huggingface \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    HF_HUB_OFFLINE=1 \
    HOME=/tmp \
    LAYA_MODEL_PATH=/opt/laya-model \
    TOKENIZERS_PARALLELISM=false \
    TRANSFORMERS_VERBOSITY=error

# Install Python dependencies.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt

# Install the PyTorch CPU wheel first, then install the remaining Python dependencies.
RUN python -m pip install \
        --disable-pip-version-check \
        --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.14.0 \
    && python -m pip install \
        --disable-pip-version-check \
        --no-cache-dir \
        --requirement "${LAMBDA_TASK_ROOT}/requirements.txt"

COPY --from=model /opt/laya-model /opt/laya-model
COPY handler.py inference.py observability.py protocol.py ${LAMBDA_TASK_ROOT}/

# Run the Lambda runtime as an unprivileged user.
USER 10001:10001

CMD ["handler.handler"]
