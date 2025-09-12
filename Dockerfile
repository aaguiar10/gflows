# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install bazel and other dependencies
RUN apt-get update && apt-get install -y bazel git

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the tff submodule
COPY tff/ /app/tff/

# Build and install tf_quant_finance from the submodule
# The submodule is a git repository, so we need to initialize it
RUN cd tff && \
    git init && \
    bazel build :build_pip_pkg && \
    ./bazel-bin/build_pip_pkg artifacts && \
    pip install artifacts/*.whl

# Copy the rest of the application code
COPY . .

# Set the command to run the job
CMD ["python", "job.py"]
