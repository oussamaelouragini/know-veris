# Build context is the workspace root, not apps/web: npm workspaces hoist the
# dependency tree to /workspace/node_modules, which must sit *above* the
# bind-mounted source for Node resolution to find it.
FROM node:22-slim

WORKDIR /workspace

# Dependency layer: manifests only, cached until they change.
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci

# apps/web/tsconfig.json extends it — Vite resolves it at dev-server startup.
COPY tsconfig.base.json ./
COPY apps/web apps/web

WORKDIR /workspace/apps/web

EXPOSE 5173

CMD ["npm", "run", "dev"]
