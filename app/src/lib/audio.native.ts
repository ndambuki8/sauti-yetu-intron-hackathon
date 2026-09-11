import * as DocumentPicker from "expo-document-picker";
import {
  AudioModule,
  RecordingPresets,
  createAudioPlayer,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
} from "expo-audio";
import type { Clip, RecordingHandle } from "./audioTypes";

export type { Clip, RecordingHandle };

function mimeFor(filename: string): string {
  const name = filename.toLowerCase();
  if (name.endsWith(".wav")) return "audio/wav";
  if (name.endsWith(".m4a") || name.endsWith(".mp4")) return "audio/mp4";
  if (name.endsWith(".mp3")) return "audio/mpeg";
  if (name.endsWith(".ogg")) return "audio/ogg";
  if (name.endsWith(".3gp")) return "audio/3gpp";
  if (name.endsWith(".caf")) return "audio/x-caf";
  if (name.endsWith(".webm")) return "audio/webm";
  return "audio/mp4";
}

function filenameFromUri(uri: string, fallback: string): string {
  const path = uri.split("?")[0];
  const base = path.split("/").pop() || fallback;
  return base.includes(".") ? decodeURIComponent(base) : fallback;
}

export async function startRecording(): Promise<RecordingHandle> {
  const permission = await requestRecordingPermissionsAsync();
  if (!permission.granted) {
    throw new Error("Microphone permission is required.");
  }
  await setAudioModeAsync({
    allowsRecording: true,
    playsInSilentMode: true,
  });
  const recorder = new AudioModule.AudioRecorder(RecordingPresets.HIGH_QUALITY);
  await recorder.prepareToRecordAsync();
  recorder.record();
  return {
    stop: async () => {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false });
      const uri = recorder.uri;
      if (!uri) throw new Error("Recording produced no audio.");
      const filename = filenameFromUri(uri, "recording.m4a");
      return { uri, filename, mime: mimeFor(filename) };
    },
  };
}

export async function pickAudio(): Promise<Clip | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: "audio/*",
    copyToCacheDirectory: true,
  });
  if (result.canceled || !result.assets?.[0]) return null;
  const asset = result.assets[0];
  const filename = asset.name || filenameFromUri(asset.uri, "upload.m4a");
  return { uri: asset.uri, filename, mime: mimeFor(filename) };
}

export async function playUri(uri: string): Promise<void> {
  const player = createAudioPlayer({ uri });
  player.play();
}
