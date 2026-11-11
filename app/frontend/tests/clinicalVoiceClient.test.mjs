import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'vite';

test('microphone sessions are transient, bounded and patient scoped', async (t) => {
  const server = await createServer({ configFile: false, appType: 'custom', server: { middlewareMode: true, hmr: false, ws: false, watch: null } });
  const original = Object.fromEntries(['window', 'localStorage', 'fetch', 'navigator', 'MediaRecorder', 'isSecureContext', 'AudioContext'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const set = (key, value) => Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const storage = new Map();
  set('window', { location: { hash: '#/case' }, dispatchEvent() {} });
  set('localStorage', { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) });
  set('isSecureContext', true);
  let mediaRequests = 0, trackStops = 0, permission, capability = true, response, fetchCalls = [], recorderInstances = [], pendingStops = [];
  const stream = () => ({ getTracks: () => [{ stop() { trackStops++; } }] });
  const mediaDevices = { async getUserMedia() { mediaRequests++; return permission ? permission.promise : stream(); } };
  set('navigator', { mediaDevices });
  class Recorder {
    static isTypeSupported(type) { return type.startsWith('audio/webm'); }
    constructor(stream, options) { this.state = 'inactive'; this.mimeType = options.mimeType; recorderInstances.push(this); }
    start() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; pendingStops.push(() => { this.ondataavailable?.({ data: new Blob(['synthetic audio'], { type: this.mimeType }) }); this.onstop?.(); }); }
  }
  set('MediaRecorder', Recorder);
  const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
  const json = (body) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
  set('fetch', async (url, options) => {
    fetchCalls.push({ url: String(url), ...options });
    if (String(url).endsWith('/capabilities')) return json({ ready: capability, language: 'tr', processing: 'medicore-server-offline', max_audio_seconds: 15 });
    return response ? response.promise : json({ text: 'Nabız 108.', language: 'tr', duration_seconds: 1, needs_review: false });
  });
  let session;
  try {
    const { ClinicalVoiceSession } = await server.ssrLoadModule('/src/services/clinicalVoiceClient.ts');
    const { API_BASE_URL } = await server.ssrLoadModule('/src/services/apiClient.ts');
    const scope = await server.ssrLoadModule('/src/services/patientScope.ts');
    const fresh = () => {
      session?.cancel(); scope.selectPatientScope('patient-A');
      mediaRequests = 0; trackStops = 0; permission = null; capability = true; response = null; fetchCalls = []; recorderInstances = []; pendingStops = [];
      const events = { texts: [], errors: [], statuses: [] };
      session = new ClinicalVoiceSession({ onText: (...args) => events.texts.push(args), onError: (error) => events.errors.push(error), onStatus: (status) => events.statuses.push(status) });
      return events;
    };
    const flush = () => new Promise((resolve) => setImmediate(resolve));
    const deliver = async () => { pendingStops.shift()?.(); await flush(); };
    await t.test('unprepared offline model does not even request microphone access', async () => {
      const events = fresh(); capability = false; await session.start();
      assert.equal(mediaRequests, 0); assert.equal(recorderInstances.length, 0); assert.ok(events.errors[0].includes('Yerel Türkçe')); assert.equal(events.statuses.at(-1), 'idle');
    });
    await t.test('insecure/unsupported browsers fail closed without contacting speech providers', async () => {
      const events = fresh(); set('isSecureContext', false); await session.start(); set('isSecureContext', true);
      assert.equal(fetchCalls.length, 0); assert.equal(mediaRequests, 0); assert.ok(events.errors[0].includes('HTTPS'));
    });
    await t.test('permission denial is readable and does not upload audio', async () => {
      const events = fresh(); permission = { promise: Promise.reject(new DOMException('denied', 'NotAllowedError')) }; await session.start();
      assert.ok(events.errors[0].includes('Mikrofon izni')); assert.ok(fetchCalls.every((call) => call.method === 'GET'));
    });
    await t.test('live chunks use only the configured MediCore endpoint and never persist a patient', async () => {
      const events = fresh(); await session.start(); recorderInstances[0].stop(); await deliver();
      assert.deepEqual(events.texts, [['Nabız 108.', false]]);
      assert.equal(recorderInstances.length, 2);
      const post = fetchCalls.find((call) => call.method === 'POST');
      assert.ok(post.url.endsWith('/clinical-voice/transcribe')); assert.ok(post.body instanceof Blob); assert.ok(post.headers['Content-Type'].startsWith('audio/webm')); assert.equal(post.cache, 'no-store');
      assert.ok(fetchCalls.every((call) => call.url.startsWith(`${API_BASE_URL}/clinical-voice/`)));
    });
    await t.test('speech survives the old six-second boundary and flushes on a pause', async (t) => {
      let amplitude = .05, closes = 0;
      class Context {
        createAnalyser() { return { fftSize: 2048, getFloatTimeDomainData(values) { values.fill(amplitude); } }; }
        createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
        async resume() {}
        async close() { closes++; }
      }
      set('AudioContext', Context);
      session?.cancel(); // Clear real timers before installing the fake clock.
      t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] });
      try {
        fresh(); await session.start();
        t.mock.timers.tick(6000);
        assert.equal(recorderInstances[0].state, 'recording', 'continuous speech must not be cut at six seconds');
        amplitude = 0;
        t.mock.timers.tick(900);
        assert.equal(recorderInstances[0].state, 'inactive', 'a sentence pause should flush the chunk');
        await deliver();
        amplitude = .05;
        t.mock.timers.tick(12000);
        assert.equal(recorderInstances[1].state, 'inactive', 'even continuous speech remains bounded below the server limit');
        session.cancel();
        assert.equal(closes, 1);
      } finally {
        session.cancel();
        t.mock.timers.reset();
        set('AudioContext', undefined);
      }
    });
    await t.test('variable chunk durations still stop recording after three minutes', async (t) => {
      session?.cancel(); // Clear real timers before installing the fake clock.
      t.mock.timers.enable({ apis: ['setTimeout', 'setInterval', 'Date'] });
      try {
        const events = fresh(); await session.start();
        t.mock.timers.tick(180000);
        assert.ok(trackStops > 0);
        assert.equal(events.statuses.at(-1), 'stopping');
        await deliver();
        assert.equal(events.statuses.at(-1), 'idle');
      } finally { session.cancel(); t.mock.timers.reset(); }
    });
    await t.test('stop waits for final recorder data and recognition before idle/approval', async () => {
      const events = fresh(); response = deferred(); await session.start(); session.stop();
      assert.equal(events.statuses.at(-1), 'stopping'); assert.equal(events.texts.length, 0);
      await deliver(); assert.equal(events.statuses.at(-1), 'stopping'); assert.ok(trackStops > 0);
      response.resolve(json({ text: 'Son parça.', language: 'tr', duration_seconds: 1 })); await flush();
      assert.equal(events.statuses.at(-1), 'idle'); assert.deepEqual(events.texts[0], ['Son parça.', false]);
    });
    await t.test('patient changes stop microphone tracks and discard late text from A', async () => {
      const events = fresh(); response = deferred(); await session.start(); recorderInstances[0].stop(); await deliver();
      scope.selectPatientScope('patient-B');
      assert.ok(trackStops > 0); assert.equal(fetchCalls.at(-1).signal.aborted, true);
      response.resolve(json({ text: 'Old patient A.', language: 'tr', duration_seconds: 1 })); await flush();
      assert.deepEqual(events.texts, []);
    });
    await t.test('cancel during the permission prompt stops a stream returned afterwards', async () => {
      const events = fresh(); permission = deferred(); const starting = session.start(); await flush();
      session.stop(); permission.resolve(stream()); await starting;
      assert.ok(trackStops > 0); assert.equal(recorderInstances.length, 0); assert.equal(events.statuses.at(-1), 'idle');
    });
    await t.test('backpressure is bounded and reports a gap instead of silently dropping speech', async () => {
      const events = fresh(); response = deferred(); await session.start();
      for (let index = 0; index < 4; index++) { recorderInstances.at(-1).stop(); await deliver(); }
      assert.ok(events.errors.some((message) => message.includes('yetişemedi'))); assert.ok(trackStops > 0);
      response.resolve(json({ text: 'Cancelled text', language: 'tr', duration_seconds: 1 })); await flush(); assert.deepEqual(events.texts, []);
    });
  } finally {
    session?.cancel();
    for (const [key, descriptor] of Object.entries(original)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
    await server.close();
  }
});
