// Regenerates the schema types in memory and fails when the committed file differs.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import openapiTS, { astToString } from 'openapi-typescript';

const spec = new URL('../openapi.json', import.meta.url);
const target = new URL('../src/api/schema.d.ts', import.meta.url);

const fresh = astToString(await openapiTS(spec));
const committed = readFileSync(target, 'utf8');

// `npm run gen` writes the CLI's output, which has a banner; compare the bodies.
const body = (text) => text.replace(/^\/\*\*[\s\S]*?\*\/\n+/, '').trim();
if (body(fresh) !== body(committed)) {
  console.error(`${fileURLToPath(target)} is out of date: run npm run gen and commit it.`);
  process.exit(1);
}
console.log('schema.d.ts matches openapi.json');
