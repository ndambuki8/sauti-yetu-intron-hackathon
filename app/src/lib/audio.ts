export type { Clip, RecordingHandle } from "./audioTypes";
import type { RecordingHandle } from "./audioTypes";

export async function startRecording(): Promise<RecordingHandle> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("This browser cannot record audio.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const recorder = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size) chunks.push(e.data);
  };
  recorder.start();
  return {
    stop: () =>
      new Promise((resolve, reject) => {
        recorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          resolve({
            uri: URL.createObjectURL(blob),
            blob,
            filename: "recording.webm",
            mime: blob.type || "audio/webm",
          });
        };
        recorder.onerror = () => reject(new Error("Recording failed"));
        recorder.stop();
      }),
  };
}

export async function pickAudio(): Promise<Clip | null> {
  if (typeof document === "undefined") return null;
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "audio/*";
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) {
        resolve(null);
        return;
      }
      resolve({
        uri: URL.createObjectURL(file),
        blob: file,
        filename: file.name || "upload.webm",
        mime: file.type || "audio/webm",
      });
    };
    input.click();
  });
}

export async function playUri(uri: string): Promise<void> {
  const el = new globalThis.Audio(uri);
  await el.play();
}
