import { API_BASE_URL } from './apiClient';
import { getAccessToken } from './authClient';
import { capturePatientScope, isCurrentPatientScope } from './patientScope';

type Capabilities = { ready: boolean; language: string; processing: string; max_audio_seconds: number };
type Transcription = { text: string; language: string; duration_seconds: number; needs_review?: boolean };
export type VoiceStatus = 'preparing' | 'listening' | 'stopping' | 'idle';
export type VoiceCallbacks = { onText: (text: string, review: boolean) => void; onStatus: (status: VoiceStatus) => void; onError: (message: string) => void };
export const VOICE_CHUNK_MS = 6000;
const MAX_CHUNKS = 30;

async function voiceRequest<T>(path: string, signal: AbortSignal, blob?: Blob): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(`${API_BASE_URL}/clinical-voice/${path}`, {
    method: blob ? 'POST' : 'GET', signal, cache: 'no-store',
    headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(blob ? { 'Content-Type': blob.type } : {}) },
    ...(blob ? { body: blob } : {}),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Ses hizmetine ulaşılamadı. Metni elle girebilirsiniz.');
  return body as T;
}

/** Only the application's existing authenticated backend receives audio. */
export class ClinicalVoiceSession {
  private scope = capturePatientScope();
  private controller = new AbortController();
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private queue: Blob[] = [];
  private processing = false;
  private stopping = false;
  private started = false;
  private emittedIdle = false;
  private chunks = 0;
  private awaitingStop = false;
  private mime = '';
  private abortScope = () => this.cancel();

  constructor(private callbacks: VoiceCallbacks) {
    this.scope.signal.addEventListener('abort', this.abortScope, { once: true });
  }
  private current() { return !this.controller.signal.aborted && isCurrentPatientScope(this.scope); }

  async start() {
    if (this.started) return;
    this.started = true;
    this.callbacks.onStatus('preparing');
    try {
      if (!globalThis.isSecureContext || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('Bu tarayıcıda güvenli mikrofon kaydı desteklenmiyor. HTTPS üzerinden açın veya metni elle girin.');
      const capabilities = await voiceRequest<Capabilities>('capabilities', this.controller.signal);
      if (!this.current()) return;
      if (!capabilities.ready || capabilities.processing !== 'medicore-server-offline' || capabilities.language !== 'tr' || capabilities.max_audio_seconds < VOICE_CHUNK_MS / 1000) throw new Error('Yerel Türkçe ses modeli henüz hazırlanmadı. Metni elle girebilirsiniz.');
      this.mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find((type) => MediaRecorder.isTypeSupported(type)) ?? '';
      if (!this.mime) throw new Error('Tarayıcı desteklenen bir ses biçimi sağlayamıyor. Metni elle girin.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      if (!this.current() || this.stopping) { stream.getTracks().forEach((track) => track.stop()); return; }
      this.stream = stream;
      this.callbacks.onStatus('listening');
      this.recordChunk();
    } catch (failure) { this.fail(failure); }
  }

  private recordChunk() {
    if (!this.current() || this.stopping || !this.stream) return;
    const parts: Blob[] = [];
    const recorder = new MediaRecorder(this.stream, { mimeType: this.mime });
    this.recorder = recorder;
    this.awaitingStop = true;
    recorder.ondataavailable = (event) => { if (event.data.size) parts.push(event.data); };
    recorder.onerror = () => this.fail(new Error('Mikrofon kaydı kesildi. Okunan metin korunuyor; kalan kısmı tekrar söyleyin.'));
    recorder.onstop = () => {
      clearTimeout(this.timer);
      this.awaitingStop = false;
      if (!this.current()) return;
      if (parts.length) {
        if (this.queue.length >= 2) { this.fail(new Error('Ses işleme yetişemedi. Okunan metni inceleyin; kalan kısmı daha kısa parçalarla tekrar söyleyin.')); return; }
        this.queue.push(new Blob(parts, { type: recorder.mimeType || this.mime }));
        void this.drain();
      }
      this.chunks++;
      if (this.chunks >= MAX_CHUNKS && !this.stopping) this.stop();
      if (!this.stopping) { try { this.recordChunk(); } catch (failure) { this.fail(failure); } }
      else this.finish();
    };
    recorder.start();
    this.timer = setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); }, VOICE_CHUNK_MS);
  }

  private async drain() {
    if (this.processing) return;
    this.processing = true;
    try {
      while (this.queue.length && this.current()) {
        const blob = this.queue.shift()!;
        const timeout = setTimeout(() => this.fail(new Error('Ses okuma süresi aşıldı. Okunan metni inceleyip kalan kısmı tekrar söyleyin.')), 30000);
        try {
          const result = await voiceRequest<Transcription>('transcribe', this.controller.signal, blob);
          if (this.current()) {
            if (result.language !== 'tr' || typeof result.text !== 'string') throw new Error('Ses yanıtı doğrulanamadı. Metni elle kontrol edin.');
            if (result.text.trim()) this.callbacks.onText(result.text.trim(), result.needs_review === true);
          }
        } finally { clearTimeout(timeout); }
      }
    } catch (failure) { this.fail(failure); }
    finally { this.processing = false; this.finish(); }
  }

  stop() {
    if (!this.stream && !this.recorder) { this.cancel(); this.callbacks.onStatus('idle'); return; }
    this.stopping = true;
    clearTimeout(this.timer);
    if (!this.current()) return;
    this.callbacks.onStatus('stopping');
    if (this.recorder?.state === 'recording') this.recorder.stop();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.finish();
  }
  private finish() {
    if (this.stopping && !this.processing && !this.queue.length && !this.awaitingStop && this.recorder?.state !== 'recording' && this.current() && !this.emittedIdle) {
      this.emittedIdle = true;
      this.scope.signal.removeEventListener('abort', this.abortScope);
      this.callbacks.onStatus('idle');
    }
  }
  cancel() {
    this.controller.abort(); this.stopping = true; this.queue = [];
    clearTimeout(this.timer);
    if (this.recorder?.state === 'recording') this.recorder.stop();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.scope.signal.removeEventListener('abort', this.abortScope);
  }
  private fail(failure: unknown) {
    if (!this.current()) return;
    this.callbacks.onError(failure instanceof DOMException && failure.name === 'NotAllowedError' ? 'Mikrofon izni verilmedi. Metni elle girebilirsiniz.'
      : failure instanceof Error ? failure.message : 'Sesli giriş kesildi. Metni kontrol edip yeniden deneyin.');
    this.cancel(); this.callbacks.onStatus('idle');
  }
}
