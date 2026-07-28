#!/usr/bin/env node
/**
 * Creates every service-level `.env` from its `.env.example`, when missing.
 *
 * There is deliberately no root `.env`: each service owns its own config next
 * to the code that reads it, and docker-compose points `env_file` at it. Host
 * ports are the only thing left in docker-compose.yml, with inline defaults.
 *
 * Idempotent — an existing `.env` is never overwritten.
 */
import { copyFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

const targets = [
  "apps/api/.env",
  "apps/web/.env",
  "infra/postgres/.env",
  "infra/keycloak/.env",
  "infra/ollama/.env",
];

let created = 0;
let missingTemplates = 0;

for (const target of targets) {
  const dest = join(root, target);
  const src = `${dest}.example`;

  if (!existsSync(src)) {
    console.error(`  !  ${target}.example is missing — skipped`);
    missingTemplates += 1;
    continue;
  }
  if (existsSync(dest)) {
    console.log(`  =  ${target} already exists`);
    continue;
  }
  copyFileSync(src, dest);
  console.log(`  +  ${target} created from .env.example`);
  created += 1;
}

console.log(
  created > 0
    ? `\n${created} env file(s) created. Review the secrets before \`npm run up\`.`
    : "\nNothing to do — every env file is already in place.",
);

process.exit(missingTemplates > 0 ? 1 : 0);
