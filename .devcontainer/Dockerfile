# Full dev box: Python 3.12 + Node 20 in one container so both backend and
# frontend toolchains are available for interactive development.
FROM python:3.12-slim

ARG NODE_MAJOR=20
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# System deps: git + curl + ca-certs (for nodesource), build tooling for any
# packages that need to compile, and libpq for psycopg if it falls back.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg build-essential libpq-dev sudo zsh \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Non-root user so files created in the mounted workspace are owned by you.
# Login shell is zsh; seed an empty .zshrc so first launch skips the new-user
# config wizard.
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m --shell /usr/bin/zsh $USERNAME \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME \
    && echo "# airtight dev shell" > /home/$USERNAME/.zshrc \
    && chown $USER_UID:$USER_GID /home/$USERNAME/.zshrc

# Put the dev command shims (frontend, server) on PATH. The dir is mounted
# from the workspace at runtime; this just registers the location.
ENV PATH="/workspaces/airtight/.devcontainer/bin:${PATH}"

USER $USERNAME
