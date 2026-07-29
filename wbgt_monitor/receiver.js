'use strict';

const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, '../frontend')));

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

// GET /input-data — serves the input.json file to the frontend
app.get('/input-data', (_req, res) => {
  res.sendFile(path.join(__dirname, '../input.json'));
});

let schedulerProcess = null;

function startScheduler() {
  stopScheduler();

  const pythonBin = fs.existsSync(path.join(__dirname, '../.venv/Scripts/python.exe'))
    ? path.join(__dirname, '../.venv/Scripts/python.exe')
    : 'python';

  console.log(`[RECEIVER] Starting scheduler process using ${pythonBin}...`);

  schedulerProcess = spawn(pythonBin, [MAIN_PY, '--scheduler'], {
    cwd: __dirname,
    stdio: 'inherit',
  });

  schedulerProcess.on('close', (code) => {
    console.log(`[RECEIVER] Scheduler process exited with code ${code}`);
    schedulerProcess = null;
  });
}

function stopScheduler() {
  if (schedulerProcess) {
    console.log('[RECEIVER] Stopping running scheduler process...');
    schedulerProcess.kill('SIGINT');
    schedulerProcess = null;
  }
}


// GET /settings — get the current simulation settings
app.get('/settings', (_req, res) => {
  const settingsPath = path.join(__dirname, 'settings.json');
  if (fs.existsSync(settingsPath)) {
    try {
      const data = fs.readFileSync(settingsPath, 'utf-8');
      return res.status(200).json(JSON.parse(data));
    } catch (err) {
      return res.status(500).json({ error: 'Failed to read settings' });
    }
  }
  // Default fallback if settings.json does not exist
  res.json({
    location_type: 'default',
    rh_status: 'avail',
    tg_status: 'avail',
    twnb_status: 'avail'
  });
});

// POST /settings — save simulation settings from the frontend and start backend
app.post('/settings', (req, res) => {
  const settings = req.body;
  try {
    fs.writeFileSync(path.join(__dirname, 'settings.json'), JSON.stringify(settings, null, 2), 'utf-8');
    startScheduler();
    return res.status(200).json({ status: 'ok' });
  } catch (err) {
    return res.status(500).json({ error: 'Failed to save settings: ' + err.message });
  }
});

// POST /stop — stop backend simulation
app.post('/stop', (req, res) => {
  try {
    stopScheduler();
    return res.status(200).json({ status: 'ok' });
  } catch (err) {
    return res.status(500).json({ error: 'Failed to stop scheduler: ' + err.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`WBGT receiver listening on port ${PORT}`);
});
