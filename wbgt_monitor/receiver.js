'use strict';

const express = require('express');
const { spawn } = require('child_process');
const path = require('path');

const app = express();
app.use(express.json());

const MAIN_PY = path.join(__dirname, 'main.py');

/**
 * Spawns a Python subprocess running main.py, writes JSON to its stdin,
 * reads the result JSON from stdout, and returns it as a parsed object.
 *
 * @param {object} payload - The sensor reading object.
 * @returns {Promise<object>} - The result object from the Python pipeline.
 */
function callPythonPipeline(payload) {
  return new Promise((resolve, reject) => {
    const child = spawn('python', [MAIN_PY], {
      cwd: __dirname,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

    child.on('close', (code) => {
      if (code !== 0) {
        return reject(new Error(`Python process exited with code ${code}: ${stderr.trim()}`));
      }
      try {
        resolve(JSON.parse(stdout.trim()));
      } catch (err) {
        reject(new Error(`Failed to parse Python output: ${stdout.trim()}`));
      }
    });

    child.on('error', (err) => {
      reject(new Error(`Failed to spawn Python process: ${err.message}`));
    });

    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

// POST /ingest — accepts sensor JSON, runs the Python pipeline, returns result.
app.post('/ingest', async (req, res) => {
  const reading = req.body;

  if (!reading || typeof reading !== 'object') {
    return res.status(400).json({ error: 'Request body must be a JSON object.' });
  }

  try {
    const result = await callPythonPipeline(reading);
    return res.status(200).json(result);
  } catch (err) {
    console.error('[/ingest] Pipeline error:', err.message);
    return res.status(500).json({ error: err.message });
  }
});

// GET /health — simple liveness check.
app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`WBGT receiver listening on port ${PORT}`);
});
